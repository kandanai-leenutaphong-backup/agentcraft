from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import webres
from selectolax.lexbor import LexborHTMLParser

from .models import ScrapeOptions
from .scraper import Scraper
from .storage import save_result, verify_result


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("Collection plan must have schema_version 1")
    families = plan.get("families", {})
    if not isinstance(families, dict) or any(
        not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name)
        or not isinstance(title, str) or not title.strip() for name, title in families.items()
    ):
        raise ValueError("Family IDs must be bounded lowercase names, never paths")
    seen = set()
    for repository in plan.get("repositories", []):
        name = repository.get("repository", "")
        if not re.fullmatch(r"(?:MicrosoftDocs|microsoft|microsoft-foundry|Azure|Azure-Samples)/[A-Za-z0-9_.-]+", name):
            raise ValueError("Only explicitly named official public GitHub repositories are supported")
        if name.casefold() in seen:
            raise ValueError("Duplicate repository in collection plan")
        seen.add(name.casefold())
        if repository.get("family") not in families:
            raise ValueError("Repository family must be declared in the collection plan")
    seen_urls = set()
    for page in plan.get("pages", []):
        if not isinstance(page, dict) or not isinstance(page.get("url"), str):
            raise ValueError("Pages must be URL/family objects")
        parsed = urlsplit(page["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Pages must use noncredentialed HTTP(S) URLs")
        if page.get("family") not in families:
            raise ValueError("Page family must be declared in the collection plan")
        if page["url"] in seen_urls:
            raise ValueError("Duplicate page URL in collection plan")
        seen_urls.add(page["url"])
    return plan


def git(arguments: list[str], *, timeout: int = 1800, raw: bool = False) -> str:
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    completed = subprocess.run(
        ["git", "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null",
         "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", *arguments],
        env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
    )
    if completed.returncode:
        message = completed.stderr.strip()[-1200:]
        raise RuntimeError(message or f"git exited {completed.returncode}")
    return completed.stdout if raw else completed.stdout.strip()


def repository_directory(root: Path, repository: str) -> Path:
    return root / "sources" / repository.replace("/", "__")


def verified_lfs_changes(directory: Path, status: str) -> bool:
    for record in status.split("\x00"):
        if not record:
            continue
        if record[:2] not in {"M ", " M", "MM"} or record[2:3] != " ":
            return False
        relative = record[3:]
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            return False
        reference = f"HEAD:{relative}"
        if int(git(["-C", str(directory), "cat-file", "-s", reference])) > 1024:
            return False
        pointer = lfs_pointer(git(["-C", str(directory), "cat-file", "blob", reference]).encode("utf-8") + b"\n")
        if not pointer:
            return False
        digest, size, _payload = file_payload(directory / relative)
        if digest != pointer["sha256"] or size != pointer["bytes"]:
            return False
    return True


def acquire_repositories(plan: dict, root: Path, *, select: str | None = None) -> dict:
    receipts = root / "receipts" / "repositories"
    receipts.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in plan.get("repositories", []):
        name = entry["repository"]
        if select and name.casefold() != select.casefold():
            continue
        destination = repository_directory(root, name)
        source_url = f"https://github.com/{name}.git"
        receipt_path = receipts / (name.replace("/", "__") + ".json")
        started = time.monotonic()
        receipt = {**entry, "source_url": source_url, "retrieved_at": webres.now_iso(),
                   "path": destination.relative_to(root).as_posix(), "ok": False}
        previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        try:
            if destination.is_symlink():
                raise ValueError("Repository destination must not be a symlink")
            if destination.exists():
                origin = git(["-C", str(destination), "remote", "get-url", "origin"])
                if origin.rstrip("/").removesuffix(".git").casefold() != source_url.removesuffix(".git").casefold():
                    raise ValueError("Existing repository has a different origin; preserved without changes")
            else:
                if shutil.disk_usage(root).free < 20 * 1024**3:
                    raise OSError("Less than 20 GiB free; stopped before another clone")
                destination.parent.mkdir(parents=True, exist_ok=True)
                git(["clone", "--quiet", "--depth", "1", "--single-branch", "--no-tags",
                     "--no-recurse-submodules", source_url, str(destination)])
            receipt["commit"] = git(["-C", str(destination), "rev-parse", "HEAD"])
            receipt["commit_date"] = git(["-C", str(destination), "show", "-s", "--format=%cI", "HEAD"])
            git(["-C", str(destination), "fsck", "--connectivity-only", "--no-reflogs"])
            status = git(["-C", str(destination), "status", "--porcelain", "-z", "--untracked-files=no"], raw=True)
            if status:
                if not verified_lfs_changes(destination, status):
                    raise ValueError("Snapshot worktree differs from its commit; preserved without changes")
                receipt["lfs_expanded"] = True
                receipt["warnings"] = ["Git index/worktree contains expanded upstream LFS pointers; file bytes verified against HEAD pointer SHA-256 and size"]
            receipt["ok"] = True
            if previous.get("commit") == receipt["commit"]:
                receipt["retrieved_at"] = previous["retrieved_at"]
                if previous.get("lfs_expanded"):
                    receipt["lfs_expanded"] = True
            receipt["verified_at"] = webres.now_iso()
            receipt["limits"] = ["Current default branch only; history and submodule content not expanded"
                                 if receipt.get("lfs_expanded") else
                                 "Current default branch only; history, submodule content and Git LFS objects not expanded"]
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            receipt["error"] = str(error)
        receipt["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        write_json(receipt_path, receipt)
        results.append(receipt)
        print(json.dumps({key: receipt[key] for key in ("repository", "ok", "elapsed_ms", "commit", "error") if key in receipt}), flush=True)
    summary = {"ok": all(result["ok"] for result in results), "repositories": len(results),
               "succeeded": sum(result["ok"] for result in results)}
    return summary


def page_metadata(html: str) -> dict:
    tree = LexborHTMLParser(html)
    metadata = {node.attributes["name"]: node.attributes.get("content", "")
                for node in tree.css("meta[name]")}
    main = tree.css_first("main") or tree.body or tree.root
    links = [{"title": node.text(strip=True), "href": node.attributes["href"]}
             for node in main.css("a[href]")]
    headings = [node.text(strip=True) for node in main.css("h1, h2, h3, h4")]
    for node in main.css("script, style, nav, noscript, template, svg"):
        node.decompose()
    text = main.text(separator="\n", strip=True)
    return {"metadata": metadata, "headings": headings, "links": links, "text": text}


def discover_pages(plan: dict, root: Path) -> dict:
    existing = {urlsplit(entry["url"])._replace(query="", fragment="").geturl() for entry in plan.get("pages", [])}
    added = 0
    for specification in plan.get("discovery", []):
        name = specification["repository"]
        repository = next(entry for entry in plan["repositories"] if entry["repository"] == name)
        directory = repository_directory(root, name).resolve()
        subtree = (directory / specification["source_prefix"]).resolve()
        if not subtree.is_relative_to(directory) or not subtree.is_dir():
            raise ValueError("Discovery prefix must identify an existing directory inside its source repository")
        base = specification["base_url"]
        parsed = urlsplit(base)
        if parsed.scheme != "https" or parsed.hostname != "learn.microsoft.com" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Source discovery supports public Microsoft Learn HTTPS roots only")
        for path in sorted(subtree.rglob("*.md")):
            relative = path.relative_to(subtree)
            if path.is_symlink() or any(part.casefold() in {"includes", "media", "images"} for part in relative.parts):
                continue
            url = base.rstrip("/") + "/" + quote(relative.with_suffix("").as_posix())
            if url in existing:
                continue
            plan.setdefault("pages", []).append({
                "url": url, "family": classify_family(repository, path.relative_to(directory).as_posix()),
                "discovered_from": path.relative_to(root.resolve()).as_posix(),
            })
            existing.add(url)
            added += 1
    return {"ok": True, "added": added, "pages": len(plan.get("pages", []))}


async def acquire_pages(plan: dict, root: Path, *, retry_failed: bool = False) -> dict:
    receipt_root = root / "receipts" / "pages"
    receipt_root.mkdir(parents=True, exist_ok=True)
    options = ScrapeOptions(timeout=90, concurrency=6, http_workers=8, browser_concurrency=2)
    pending = {}
    skipped = 0
    retained_failures = 0
    for entry in plan.get("pages", []):
        identity = hashlib.sha256(entry["url"].encode()).hexdigest()
        receipt_path = receipt_root / f"{identity}.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt.get("ok"):
                verification = verify_result(root / receipt["directory"])
                if verification["ok"] and verification["acquisition_ok"]:
                    derived_path = root / receipt["extracted"]
                    if not derived_path.is_file() or hashlib.sha256(derived_path.read_bytes()).hexdigest() != receipt["extracted_sha256"]:
                        html = (root / receipt["directory"] / "page.html").read_text(encoding="utf-8-sig")
                        write_json(derived_path, page_metadata(html))
                        receipt["extracted_sha256"] = hashlib.sha256(derived_path.read_bytes()).hexdigest()
                        write_json(receipt_path, receipt)
                    skipped += 1
                    continue
            elif not retry_failed:
                skipped += 1
                retained_failures += 1
                continue
        pending[entry["url"]] = (entry, identity)
    succeeded = 0
    failed = 0
    async with Scraper(options) as scraper:
        async for result in scraper.fetch_many(pending):
            entry, identity = pending[result.url]
            directory = await asyncio.to_thread(save_result, result, root / "pages" / entry["family"], options)
            receipt = {**entry, "ok": result.ok, "title": result.title, "final_url": result.final_url,
                       "status": result.status, "method": result.method, "retrieved_at": result.retrieved_at,
                       "elapsed_ms": result.elapsed_ms, "directory": directory.relative_to(root).as_posix(),
                       "error_code": result.error_code, "error": result.error, "warnings": result.warnings,
                       "verified": True}
            if result.ok:
                derived = page_metadata(result.html)
                derived_path = root / "extracted" / entry["family"] / f"{identity}.json"
                write_json(derived_path, derived)
                receipt["extracted"] = derived_path.relative_to(root).as_posix()
                receipt["extracted_sha256"] = hashlib.sha256(derived_path.read_bytes()).hexdigest()
                succeeded += 1
            else:
                failed += 1
            write_json(receipt_root / f"{identity}.json", receipt)
            print(json.dumps({key: receipt[key] for key in ("url", "ok", "method", "status", "elapsed_ms", "error_code")}), flush=True)
        return {"ok": failed + retained_failures == 0, "acquired": succeeded, "failed": failed,
            "retained_failures": retained_failures, "resumed": skipped}


_TEXT_SUFFIXES = {
    ".md", ".mdx", ".rst", ".txt", ".yml", ".yaml", ".json", ".jsonl", ".ipynb",
    ".py", ".cs", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css",
    ".bicep", ".tf", ".sh", ".ps1", ".xml", ".toml", ".sql", ".kql", ".http",
    ".csproj", ".props", ".targets", ".go", ".rs", ".c", ".cpp", ".h", ".proto",
}
_MAX_INDEX_BYTES = 2 * 1024 * 1024


def classify_family(repository: dict, path: str) -> str:
    lowered = path.casefold()
    if repository["repository"] != "MicrosoftDocs/azure-ai-docs":
        return repository["family"]
    if lowered.startswith("articles/foundry-local/"):
        return "11-foundry-local"
    if lowered.startswith(("articles/machine-learning/", "articles/open-datasets/")):
        return "10-machine-learning"
    if lowered.startswith("articles/search/"):
        return "05-iq-grounding"
    if lowered.startswith("articles/ai-services/content-safety/"):
        return "08-trustworthy-ai"
    if lowered.startswith("articles/ai-services/"):
        return "09-foundry-tools"
    if lowered.startswith("agent-framework/"):
        return "04-agents"
    for family, tokens in (
        ("08-trustworthy-ai", ("responsible-ai", "responsible-use", "content-filter", "data-privacy", "prompt-shield")),
        ("07-governance-security", ("control-plane", "rbac", "network", "private-link", "authentication", "managed-identity", "security", "encryption", "customer-managed")),
        ("06-observability", ("observability", "evaluat", "monitor", "trac", "red-team", "optimizer", "optimiz")),
        ("05-iq-grounding", ("foundry-iq", "fabric-iq", "knowledge", "grounding", "retrieval", "/rag")),
        ("04-agents", ("/agents/", "/mcp/")),
        ("03-models", ("foundry-models", "/openai/", "model-catalog", "models", "fine-tun")),
        ("02-developer-experience", ("/develop/", "sdk", "quickstart", "tutorial", "cli")),
    ):
        if any(token in lowered for token in tokens):
            return family
    return "01-master-indexes"


def file_payload(path: Path) -> tuple[str, int, bytes | None]:
    if path.is_symlink():
        payload = os.readlink(path).encode("utf-8")
        return hashlib.sha256(payload).hexdigest(), len(payload), None
    size = path.stat().st_size
    digest = hashlib.sha256()
    chunks = [] if size <= _MAX_INDEX_BYTES else None
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
    return digest.hexdigest(), size, b"".join(chunks) if chunks is not None else None


def indexed_text(path: Path, payload: bytes | None) -> tuple[str, str]:
    if payload is None:
        return "preserved-not-indexed", ""
    if payload.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        return "lfs-pointer", ""
    if path.suffix.casefold() not in _TEXT_SUFFIXES and path.name.casefold() not in {"license", "license-code", "notice", "dockerfile", "makefile"}:
        return "asset", ""
    if b"\x00" in payload:
        return "binary", ""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "non-utf8", ""
    if path.suffix == ".ipynb":
        try:
            notebook = json.loads(text)
            text = "\n\n".join("".join(cell.get("source", [])) for cell in notebook.get("cells", []))
        except (ValueError, AttributeError, TypeError):
            return "invalid-notebook", ""
    kind = "document" if path.suffix.casefold() in {".md", ".mdx", ".rst", ".txt"} else "source"
    return kind, text


def lfs_pointer(payload: bytes) -> dict | None:
    if not payload.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        return None
    fields = dict(line.split(" ", 1) for line in payload.decode("ascii").splitlines() if " " in line)
    identity = fields.get("oid", "")
    size = fields.get("size", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity) or not size.isdecimal():
        raise ValueError("Invalid Git LFS pointer")
    return {"sha256": identity.removeprefix("sha256:"), "bytes": int(size)}


def acquire_lfs(plan: dict, root: Path, executable: str | None) -> dict:
    executable = executable or shutil.which("git-lfs")
    if not executable or not Path(executable).is_file():
        raise ValueError("Git LFS client required; provide --lfs-executable or install git-lfs")
    executable = str(Path(executable).resolve())
    results = []
    for entry in plan["repositories"]:
        name = entry["repository"]
        directory = repository_directory(root, name)
        receipt_path = root / "receipts/lfs" / (name.replace("/", "__") + ".json")
        if receipt_path.exists():
            pointers = json.loads(receipt_path.read_text())["objects"]
        else:
            pointers = []
            tree = git(["-C", str(directory), "ls-tree", "-r", "-l", "-z", "HEAD"])
            for record in tree.split("\x00"):
                if not record:
                    continue
                attributes, relative = record.split("\t", 1)
                mode, kind, _blob, size = attributes.split()
                path = directory / relative
                if kind == "blob" and mode != "120000" and int(size) < 1024:
                    pointer = lfs_pointer(path.read_bytes())
                    if pointer:
                        pointers.append({"path": relative, **pointer})
        if not pointers:
            continue
        total_bytes = sum(pointer["bytes"] for pointer in pointers)
        receipt = {"repository": name, "objects": pointers, "declared_bytes": total_bytes,
                   "ok": False, "retrieved_at": webres.now_iso()}
        write_json(receipt_path, receipt)
        try:
            if shutil.disk_usage(root).free < total_bytes * 2 + 20 * 1024**3:
                raise OSError("Insufficient free disk for bounded LFS expansion")
            client = shlex.quote(executable)
            for key, value in {
                "filter.lfs.clean": f"{client} clean -- %f",
                "filter.lfs.smudge": f"{client} smudge --skip -- %f",
                "filter.lfs.process": f"{client} filter-process --skip",
                "filter.lfs.required": "true",
            }.items():
                git(["-C", str(directory), "config", "--local", key, value])
            environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
            for command in ("fetch", "checkout"):
                arguments = [executable, command]
                if command == "fetch":
                    arguments.extend(["origin", "HEAD"])
                environment.update({
                    "GIT_CONFIG_COUNT": "5", "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
                    "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": "/dev/null",
                    "GIT_CONFIG_KEY_2": "lfs.url", "GIT_CONFIG_VALUE_2": f"https://github.com/{name}.git/info/lfs",
                    "GIT_CONFIG_KEY_3": "lfs.concurrenttransfers", "GIT_CONFIG_VALUE_3": "3",
                    "GIT_CONFIG_KEY_4": "lfs.fetchinclude", "GIT_CONFIG_VALUE_4": "",
                })
                completed = subprocess.run(arguments, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                                           capture_output=True, timeout=1800)
                if completed.returncode:
                    raise RuntimeError("Git LFS operation failed; endpoint response details not logged")
            for pointer in pointers:
                digest, size, _payload = file_payload(directory / pointer["path"])
                if digest != pointer["sha256"] or size != pointer["bytes"]:
                    raise ValueError("LFS object failed declared SHA-256/size verification")
            receipt["ok"] = True
            receipt["verified_objects"] = len(pointers)
            source_path = root / "receipts/repositories" / (name.replace("/", "__") + ".json")
            source = json.loads(source_path.read_text())
            source["lfs_expanded"] = True
            source["limits"] = ["Current default branch only; history and submodule content not expanded"]
            write_json(source_path, source)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            receipt["error"] = str(error)
        write_json(receipt_path, receipt)
        results.append(receipt)
        print(json.dumps({key: receipt[key] for key in ("repository", "ok", "declared_bytes", "verified_objects", "error") if key in receipt}), flush=True)
    return {"ok": all(result["ok"] for result in results), "repositories": len(results),
            "verified_objects": sum(result.get("verified_objects", 0) for result in results)}


def build_index(plan: dict, root: Path) -> dict:
    descriptor, pending_name = tempfile.mkstemp(prefix=".index-", suffix=".sqlite3", dir=root)
    os.close(descriptor)
    pending = Path(pending_name)
    connection = sqlite3.connect(pending)
    connection.executescript("""
        CREATE TABLE files (
            id INTEGER PRIMARY KEY, repository TEXT, family TEXT, path TEXT UNIQUE,
            url TEXT, title TEXT, kind TEXT, bytes INTEGER, sha256 TEXT, git_blob TEXT,
            body TEXT, indexed INTEGER
        );
        CREATE TABLE sources (repository TEXT PRIMARY KEY, commit_sha TEXT, receipt TEXT);
        CREATE VIRTUAL TABLE text_index USING fts5(title, body, content='files', content_rowid='id');
    """)
    source_count = 0
    for entry in plan.get("repositories", []):
        name = entry["repository"]
        receipt_path = root / "receipts/repositories" / (name.replace("/", "__") + ".json")
        receipt = json.loads(receipt_path.read_text())
        if not receipt.get("ok"):
            continue
        directory = repository_directory(root, name)
        if git(["-C", str(directory), "rev-parse", "HEAD"]) != receipt["commit"]:
            raise ValueError("Repository commit changed since acquisition")
        tree = git(["-C", str(directory), "ls-tree", "-r", "-l", "-z", "HEAD"])
        files = 0
        for record in tree.split("\x00"):
            if not record:
                continue
            attributes, relative = record.split("\t", 1)
            mode, object_kind, blob, _size = attributes.split()
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Unsafe source tree path")
            path = directory / relative
            title = Path(relative).stem.replace("-", " ")
            body = ""
            if object_kind != "blob":
                digest, size, kind = "", 0, "submodule-not-expanded"
            else:
                digest, size, payload = file_payload(path)
                kind, body = indexed_text(path, payload)
                if mode == "120000":
                    kind = "symlink-not-followed"
                if kind == "document":
                    title = next((line[2:].strip() for line in body.splitlines()[:100] if line.startswith("# ")), title)
            url = f"https://github.com/{name}/blob/{receipt['commit']}/{quote(relative)}"
            connection.execute("INSERT INTO files VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)", (
                name, classify_family(entry, relative), path.relative_to(root).as_posix(), url,
                title, kind, size, digest, blob, body, int(bool(body)),
            ))
            files += 1
        connection.execute("INSERT INTO sources VALUES (?,?,?)", (name, receipt["commit"], json.dumps(receipt)))
        connection.commit()
        source_count += 1
        print(json.dumps({"indexed_repository": name, "files": files}), flush=True)
    page_count = 0
    page_failures = []
    for receipt_path in sorted((root / "receipts/pages").glob("*.json")):
        receipt = json.loads(receipt_path.read_text())
        if not receipt.get("ok"):
            page_failures.append({key: receipt.get(key) for key in ("url", "status", "error_code", "error", "directory")})
            continue
        directory = root / receipt["directory"]
        if not verify_result(directory)["ok"]:
            raise ValueError("Page failed verification before indexing")
        path = directory / "page.html"
        digest, size, _payload = file_payload(path)
        derived_path = root / receipt["extracted"]
        if hashlib.sha256(derived_path.read_bytes()).hexdigest() != receipt["extracted_sha256"]:
            raise ValueError("Extracted content hash mismatch")
        derived = json.loads(derived_path.read_text())
        connection.execute("INSERT INTO files VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)", (
            "live-web", receipt["family"], path.relative_to(root).as_posix(), receipt["final_url"],
            receipt["title"], "live-html", size, digest, "", derived["text"], 1,
        ))
        page_count += 1
    connection.executescript("""
        INSERT INTO text_index(text_index) VALUES('rebuild');
        CREATE INDEX by_family ON files(family);
        CREATE INDEX by_repository ON files(repository);
        CREATE INDEX by_kind ON files(kind);
    """)
    connection.commit()
    row = connection.execute("SELECT count(*), sum(bytes), sum(indexed) FROM files").fetchone()
    kinds = dict(connection.execute("SELECT kind, count(*) FROM files GROUP BY kind"))
    families = {family: {"files": count, "bytes": size, "searchable": searchable}
                for family, count, size, searchable in connection.execute(
                    "SELECT family,count(*),sum(bytes),sum(indexed) FROM files GROUP BY family")}
    summary = {"ok": True, "generated_at": webres.now_iso(), "repositories": source_count,
               "live_pages": page_count, "files": row[0], "source_bytes": row[1], "searchable_files": row[2],
               "kinds": kinds, "families": families, "max_indexed_file_bytes": _MAX_INDEX_BYTES,
               "planned_live_pages": len(plan.get("pages", [])), "failed_live_pages": page_failures,
               "unattempted_live_pages": len(plan.get("pages", [])) - page_count - len(page_failures)}
    connection.close()
    pending.replace(root / "index.sqlite3")
    write_json(root / "coverage.json", summary)
    write_reports(plan, root, summary)
    return summary


def read_index(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect((root / "index.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def search_index(root: Path, query: str, family: str | None = None, limit: int = 12) -> list[dict]:
    with read_index(root) as connection:
        rows = connection.execute("""
            SELECT files.repository,files.family,files.title,files.path,files.url,
                   snippet(text_index,1,'[',']',' ... ',28) AS excerpt
            FROM text_index JOIN files ON files.id=text_index.rowid
            WHERE text_index MATCH ? AND files.indexed=1 AND (? IS NULL OR files.family=?)
            ORDER BY bm25(text_index,5.0,1.0) LIMIT ?
        """, (query, family, family, max(1, min(limit, 100))))
        return [dict(row) for row in rows]


def write_reports(plan: dict, root: Path, summary: dict) -> None:
    with read_index(root) as connection:
        sources = [json.loads(row[0]) for row in connection.execute("SELECT receipt FROM sources ORDER BY repository")]
        source_lines = ["# Acquired sources", "", "Current public snapshots. Commit IDs pin content, not publisher signatures.", "",
                        "| Repository | Commit | Commit date | Local source |", "| --- | --- | --- | --- |"]
        for source in sources:
            source_lines.append(f"| [{source['repository']}]({source['source_url'].removesuffix('.git')}) | {source['commit']} | {source['commit_date']} | [Browse]({source['path']}/) |")
        (root / "SOURCES.md").write_text("\n".join(source_lines) + "\n", encoding="utf-8")
        contents = ["# Feature-family index", "", "Primary family assignments are navigation aids, not semantic proof of exclusive coverage.", "",
                    "| Family | Files | Searchable files |", "| --- | --- | --- |"]
        for family, title in plan["families"].items():
            directory = root / "features" / family
            directory.mkdir(parents=True, exist_ok=True)
            counts = summary["families"].get(family, {"files": 0, "searchable": 0})
            contents.append(f"| [{title}](features/{family}/README.md) | {counts['files']} | {counts['searchable']} |")
            lines = [f"# {title}", "", f"Files: {counts['files']}. Searchable: {counts['searchable']}.", "",
                     "Browse [all documents](documents.md) or use the [JSON Lines catalogue](documents.jsonl).",
                     "All source/assets are retained and queryable in the root SQLite index.", "",
                     "## Live controls", ""]
            for row in connection.execute("SELECT title,path,url FROM files WHERE family=? AND kind='live-html' ORDER BY title", (family,)):
                label = row["title"].replace("[", "").replace("]", "")
                lines.append(f"- [{label}](../../{quote(row['path'])}) | [Published source]({row['url']})")
            (directory / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            with (directory / "documents.jsonl").open("w", encoding="utf-8") as stream, (directory / "documents.md").open("w", encoding="utf-8") as markdown:
                markdown.write(f"# {title}: documents\n\n")
                current_repository = None
                for row in connection.execute("SELECT title,path,url,repository,sha256,kind FROM files WHERE family=? AND kind IN ('document','live-html') ORDER BY repository,path", (family,)):
                    stream.write(json.dumps(dict(row), ensure_ascii=True) + "\n")
                    if row["repository"] != current_repository:
                        current_repository = row["repository"]
                        markdown.write(f"\n## {current_repository}\n\n")
                    label = row["title"].replace("[", "").replace("]", "").replace("\n", " ")
                    markdown.write(f"- [{label}](../../{quote(row['path'])}) | [source]({row['url']})\n")
        (root / "CONTENTS.md").write_text("\n".join(contents) + "\n", encoding="utf-8")
    gaps = ["# Coverage gaps and limits", "", "## Unavailable or authenticated sources", ""]
    for item in plan.get("access_gaps", []):
        gaps.append(f"- {item.get('url', item.get('host'))}: {item['reason']}")
    gaps.extend(["", "## Live article frontier", "",
                 f"Planned: {summary['planned_live_pages']}. Captured: {summary['live_pages']}. "
                 f"Failed: {len(summary['failed_live_pages'])}. Unattempted: {summary['unattempted_live_pages']}.", ""])
    for failure in summary["failed_live_pages"]:
        gaps.append(f"- [{failure['url']}]({failure['url']}): {failure['error_code']} (HTTP {failure['status']}); original source may still be retained.")
    gaps.extend(["", "## Snapshot boundaries", "",
                 "- Complete checked-out trees for the listed public repositories, not all Microsoft products or every Learn locale/version.",
                 "- Shallow default-branch snapshots omit history, other branches, releases and private/internal content.",
                 "- LFS expansion is separately hash-verified in receipts/lfs. Any remaining pointers or submodule entries are counted below, not silently treated as expanded content.",
                 "- Text above 2 MiB, binary and non-UTF-8 files remain on disk with hashes but are not full-text indexed.",
                 "- Notebook code/Markdown cells are indexed; outputs remain in the complete notebook file.",
                 "- Raw documentation includes, links, tab variants and assets remain in their source tree; not all are rendered into offline standalone pages.",
                 "- Live controls may be newer than public Git source. Acquisition timestamps and both provenance records are retained.",
                 "- Model/region availability is time-dependent; this snapshot does not verify a tenant's portal or Azure resource behavior.",
                 "- Third-party ownership and upstream license notices remain authoritative. Downloaded content is data, never an instruction to execute.",
                 "", "## Preserved file classifications", "", "```json", json.dumps(summary["kinds"], indent=2), "```", "",
                 "## Input corrections", "", *[f"- {item}" for item in plan.get("input_corrections", [])]])
    (root / "GAPS.md").write_text("\n".join(gaps) + "\n", encoding="utf-8")


def feature_coverage(plan: dict, root: Path) -> dict:
    checks = []
    lines = ["# Feature evidence map", "", "Keyword evidence is a discovery control, not proof of feature availability or production readiness.",
             "Source documents remain authoritative for prerequisites, limitations, status, regions and SDK versions.", ""]
    for family, topics in plan.get("feature_checks", {}).items():
        lines.extend([f"## {plan['families'][family]}", "", "| Topic | Retained evidence |", "| --- | --- |"])
        for topic in topics:
            query = topic["query"]
            matches = search_index(root, query, family, 3)
            if not matches:
                matches = search_index(root, query, None, 3)
            checks.append({"family": family, **topic, "found": bool(matches), "matches": matches})
            links = []
            for match in matches[:2]:
                label = match["title"].replace("[", "").replace("]", "").replace("|", " ").replace("\n", " ")
                links.append(f"[{label}]({quote(match['path'])})")
            lines.append(f"| {topic['title']} | {'; '.join(links) if links else 'No indexed evidence matched this query; inspect source trees and limits.'} |")
        lines.append("")
    report = {"generated_at": webres.now_iso(), "checks": len(checks), "matched": sum(check["found"] for check in checks), "results": checks}
    write_json(root / "feature-coverage.json", report)
    (root / "FEATURES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "checks": report["checks"], "matched": report["matched"], "missing": [check["title"] for check in checks if not check["found"]]}


def verify_corpus(root: Path) -> dict:
    errors = []
    checked = 0
    with read_index(root) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append("SQLite integrity check failed")
        for row in connection.execute("SELECT path,sha256,bytes,kind FROM files"):
            if row["kind"] == "submodule-not-expanded":
                continue
            path = root / row["path"]
            try:
                digest, size, _payload = file_payload(path)
                if digest != row["sha256"] or size != row["bytes"]:
                    errors.append(f"Changed file: {row['path']}")
            except OSError:
                errors.append(f"Missing file: {row['path']}")
            checked += 1
        for source in connection.execute("SELECT repository,commit_sha FROM sources"):
            directory = repository_directory(root, source["repository"])
            if git(["-C", str(directory), "rev-parse", "HEAD"]) != source["commit_sha"]:
                errors.append(f"Changed commit: {source['repository']}")
    page_receipts = 0
    registered_directories = set()
    for path in (root / "receipts/pages").glob("*.json"):
        receipt = json.loads(path.read_text())
        directory = root / receipt["directory"]
        registered_directories.add(directory.resolve())
        if not verify_result(directory)["ok"]:
            errors.append(f"Page manifest mismatch: {receipt['url']}")
        if receipt.get("ok") and hashlib.sha256((root / receipt["extracted"]).read_bytes()).hexdigest() != receipt["extracted_sha256"]:
            errors.append(f"Extracted content mismatch: {receipt['url']}")
        page_receipts += 1
    supplementary = 0
    for manifest in (root / "pages").glob("*/*/manifest.json"):
        if manifest.parent.resolve() not in registered_directories:
            if not verify_result(manifest.parent)["ok"]:
                errors.append(f"Supplementary capture mismatch: {manifest.parent.relative_to(root)}")
            supplementary += 1
    result = {"ok": not errors, "verified_at": webres.now_iso(), "files_checked": checked,
              "page_receipts_checked": page_receipts, "supplementary_captures_checked": supplementary, "errors": errors}
    write_json(root / "verification.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire pinned public documentation/source collections without executing them.")
    parser.add_argument("command", choices=("repositories", "discover", "pages", "lfs", "index", "features", "search", "verify"))
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repository", help="acquire just this repository from the plan")
    parser.add_argument("--retry-failed", action="store_true", help="retry previously recorded page failures")
    parser.add_argument("--query", help="SQLite FTS5 query for local search")
    parser.add_argument("--family", help="restrict search to one feature-family ID")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--lfs-executable", help="path to an optional locally installed Git LFS client")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if arguments.command == "search":
        if not arguments.query:
            parser.error("search requires --query")
        print(json.dumps(search_index(root, arguments.query, arguments.family, arguments.limit), indent=2))
        return 0
    if arguments.command == "verify":
        summary = verify_corpus(root)
        print(json.dumps(summary), flush=True)
        return int(not summary["ok"])
    plan = load_plan(arguments.plan or root / "collection.json")
    if arguments.command == "repositories":
        summary = acquire_repositories(plan, root, select=arguments.repository)
    elif arguments.command == "discover":
        summary = discover_pages(plan, root)
        write_json(arguments.plan or root / "collection.json", plan)
    elif arguments.command == "lfs":
        summary = acquire_lfs(plan, root, arguments.lfs_executable)
    elif arguments.command == "index":
        summary = build_index(plan, root)
    elif arguments.command == "features":
        summary = feature_coverage(plan, root)
    else:
        summary = asyncio.run(acquire_pages(plan, root, retry_failed=arguments.retry_failed))
    print(json.dumps(summary), flush=True)
    return int(not summary["ok"])


if __name__ == "__main__":
    raise SystemExit(main())