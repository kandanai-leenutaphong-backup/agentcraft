#!/usr/bin/env python3
"""Federated repository retrieval: registry, contracts, source and notebook in one query.

Answers "what is this about, does it already exist, who owns it" before an agent starts
archaeology. Absence is reported as a finding, not an empty screen: proving a term is nowhere in
the repository is the single most expensive thing to establish by hand.

Usage:
    python3 .github/tools/find.py "collapse explorer"
    python3 .github/tools/find.py "agent canvas" --json

Standard library only. Run from anywhere; paths are resolved from this file.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load_harness_config(root: Path) -> dict[str, Any]:
    config_path = root / ".agent-harness.json"
    if not config_path.is_file():
        return {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


_CONFIG = _load_harness_config(ROOT)
_REGISTRY_REL = _CONFIG.get("component_registry")

# None means the project has no component registry; the registry section is then omitted
# rather than reported as a missing file.
REGISTRY_PATH = ROOT / str(_REGISTRY_REL) if _REGISTRY_REL else None
NOTEBOOK_ROOT = ROOT / str(_CONFIG.get("notebook_root") or "docs/notebook")
NOTEBOOK_MODULE = NOTEBOOK_ROOT / "notebook.py"
NOTES_DIR = NOTEBOOK_ROOT / "notes"
# Project-declared globs to leave out of the corpus, for a vendored or installed second copy
# of a tree that is already indexed at its source.
EXCLUDE: tuple[str, ...] = tuple(_CONFIG.get("exclude") or ())

# Generated, vendored, or installed trees. Indexing them buries authored code under bundles.
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages", ".next", ".vite",
    ".turbo", ".cache", "coverage", "playwright-report", "test-results", ".vocs",
    ".parcel-cache", "htmlcov", ".tox", "target", "out", "upstream", "output", "assets",
    "__snapshots__", ".ipynb_checkpoints",
}
SKIP_NAMES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock",
    "components.lock.json", ".harness-manifest.json",
}
INDEXED_SUFFIXES = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".md", ".mdx", ".sh",
    ".bicep", ".css", ".html", ".json", ".toml", ".yaml", ".yml", ".sql", ".bash", ".cfg",
    ".ini", ".txt",
}
MAX_FILE_BYTES = 250_000
SHORTLIST = 250
SELF_PATH = Path(__file__).resolve()

CONTRACT_NAME = "CONTRACT.md"
W_PATH, W_SYMBOL, W_DOC, W_BODY, W_LINE = 40.0, 26.0, 12.0, 4.0, 18.0
CAPS = {"registry": 5, "contracts": 6, "source": 12, "notebook": 6}

SYMBOL_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "py": (
        re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),
        re.compile(r"^\s*class\s+(\w+)"),
        re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?\s*="),
    ),
    "web": (
        re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)"),
        re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"),
        re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(\w+)"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)"),
    ),
    "sh": (
        re.compile(r"^(?:function\s+)?([A-Za-z_]\w*)\s*\(\)"),
        re.compile(r"^([A-Z][A-Z0-9_]*)="),
    ),
    "bicep": (re.compile(r"^\s*(?:resource|module|param|var|output)\s+(\w+)"),),
    "css": (re.compile(r"^\s*[.#]([A-Za-z][\w-]*)"),),
    "md": (re.compile(r"^#{1,6}\s+(.+?)\s*$"),),
}
SYMBOL_FAMILY = {
    ".py": "py", ".pyi": "py", ".ts": "web", ".tsx": "web", ".js": "web", ".jsx": "web",
    ".mjs": "web", ".cjs": "web", ".sh": "sh", ".bash": "sh", ".bicep": "bicep",
    ".css": "css", ".md": "md", ".mdx": "md",
}
LOWER_BOUND = re.compile(r">=\s*([0-9]+(?:\.[0-9]+)*)")
BACKTICKED = re.compile(r"`([^`]+)`")

# Ranked out of the term set, never out of the phrase: they match everything and rank nothing.
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "but", "by", "can", "do", "for",
    "from", "has", "have", "how", "if", "in", "into", "is", "it", "its", "not", "of", "on",
    "or", "our", "so", "than", "that", "the", "their", "then", "there", "these", "they",
    "this", "to", "was", "we", "what", "when", "where", "which", "who", "why", "will",
    "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def identifier_tokens(text: str) -> set[str]:
    """Split on separators and camel humps so `resourceExplorer` and `resource-explorer` meet."""
    parts = re.split(r"[^A-Za-z0-9]+", text)
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        tokens.add(part.lower())
        for hump in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", part):
            tokens.add(hump.lower())
    return tokens


class Query:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.phrase = raw.strip().lower()
        tokens = tokenize(raw)
        if not tokens:
            raise SystemExit("find: query must contain a word or number")
        self.terms = [t for t in tokens if t not in STOPWORDS] or tokens
        self.dropped = [t for t in tokens if t not in self.terms]
        self.variants = {
            self.phrase,
            "".join(tokens),
            "-".join(tokens),
            "_".join(tokens),
            "".join(self.terms),
            "-".join(self.terms),
            "_".join(self.terms),
        }
        self.word = {t: re.compile(rf"\b{re.escape(t)}\b") for t in self.terms}
        self.prefix = {t: re.compile(rf"\b{re.escape(t)}") for t in self.terms}

    def factors(self, low: str) -> dict[str, float]:
        """Whole word outranks word-prefix outranks substring. Input must already be lowercase."""
        found: dict[str, float] = {}
        if not low:
            return found
        for term in self.terms:
            if self.word[term].search(low):
                found[term] = 1.0
            elif self.prefix[term].search(low):
                found[term] = 0.6
            elif term in low:
                found[term] = 0.25
        return found

    def score(self, fields: list[tuple[str, float]]) -> tuple[int, float]:
        best: dict[str, float] = {}
        total = 0.0
        for low, weight in fields:
            for term, factor in self.factors(low).items():
                total += weight * factor
                best[term] = max(best.get(term, 0.0), factor)
        # A bare substring is evidence, not coverage; coverage drives the OR fallback tier.
        return sum(1 for factor in best.values() if factor >= 0.6), total

    def line_rank(self, line: str) -> int:
        low = line.lower()
        return sum(1 for term in self.terms if self.prefix[term].search(low))


def is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # Minified or machine-generated: long mean line length, no authored structure to rank.
    sample = text[:50_000]
    if len(sample) > 4_000 and len(sample) / (sample.count("\n") + 1) > 400:
        return None
    return text


def header_text(lines: list[str], suffix: str) -> str:
    """Module docblocks are the highest-signal prose in this repository; index them alone."""
    family = SYMBOL_FAMILY.get(suffix, "")
    if family == "md":
        return "\n".join(lines[:18])
    collected: list[str] = []
    index = 0
    while index < len(lines) and index < 8:
        stripped = lines[index].strip()
        if stripped.startswith("#!") or not stripped or stripped.startswith("from __future__"):
            index += 1
            continue
        break
    if family == "py" and index < len(lines):
        opener = lines[index].lstrip()
        for quote in ('"""', "'''"):
            if opener.startswith(quote):
                body = lines[index].split(quote, 1)[1]
                if quote in body:
                    return body.split(quote, 1)[0]
                collected.append(body)
                for line in lines[index + 1 : index + 60]:
                    if quote in line:
                        collected.append(line.split(quote, 1)[0])
                        return "\n".join(collected)
                    collected.append(line)
                return "\n".join(collected)
    for line in lines[index : index + 40]:
        stripped = line.strip()
        if stripped.startswith(("//", "#", "/*", "*", "<!--")):
            collected.append(stripped.lstrip("/#*<!- "))
        elif collected:
            break
        elif stripped:
            break
    return "\n".join(collected)


def symbols_of(lines: list[str], suffix: str) -> list[tuple[str, int]]:
    patterns = SYMBOL_PATTERNS.get(SYMBOL_FAMILY.get(suffix, ""), ())
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                name = match.group(1).strip()
                if name and name not in seen:
                    seen.add(name)
                    found.append((name, number))
                break
    return found


def snippet(line: str, width: int = 116) -> str:
    text = " ".join(line.split())
    return text if len(text) <= width else text[: width - 1] + "\u2026"


def load_registry() -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    if REGISTRY_PATH is None:
        return {"components": []}, problems
    if not REGISTRY_PATH.is_file():
        return {"components": []}, [f"registry missing at {_REGISTRY_REL}"]
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8")), problems
    except (OSError, json.JSONDecodeError) as error:
        return {"components": []}, [f"registry unreadable: {error}"]


def registry_components(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    components = manifest.get("components", [])
    if REGISTRY_PATH is None:
        return []
    consumers: dict[str, list[str]] = {c.get("id", ""): [] for c in components}
    for component in components:
        for dependency in component.get("dependencies", []):
            target = dependency.get("component", "")
            if target in consumers:
                consumers[target].append(component.get("id", ""))
    for component in components:
        # Derived, never stored: the manifest declares forward edges only.
        component["_consumers"] = sorted(consumers.get(component.get("id", ""), []))
        raw = component.get("path", "")
        component["_dir"] = (REGISTRY_PATH.parent / raw).resolve() if raw else None
    return components


def contract_claims(text: str) -> dict[str, Any]:
    claims: dict[str, Any] = {"id": None, "id_line": 0, "artifacts": {}, "depends": {}}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        lowered = stripped.lower()
        if claims["id"] is None and lowered.startswith("component id:"):
            names = BACKTICKED.findall(stripped)
            if names:
                claims["id"] = (names[0].strip(), number)
        if re.match(r"^(planned\s+)?artifacts?:", lowered):
            for token in BACKTICKED.findall(stripped):
                claims["artifacts"].setdefault(token.strip(), number)
        if lowered.startswith("depends:"):
            for token in BACKTICKED.findall(stripped):
                name = re.split(r"[<>=!~ ,]", token.strip(), maxsplit=1)[0]
                bound = LOWER_BOUND.search(token)
                if name and bound:
                    claims["depends"].setdefault(name, (bound.group(1), number))
        if '"artifact"' in stripped and '"constraint"' in stripped:
            artifact = re.search(r'"artifact"\s*:\s*"([^"]+)"', stripped)
            bound = re.search(r'"constraint"\s*:\s*"([^"]*)"', stripped)
            if artifact and bound:
                lower = LOWER_BOUND.search(bound.group(1))
                if lower:
                    claims["depends"].setdefault(artifact.group(1), (lower.group(1), number))
    return claims


def find_conflicts(components: list[dict[str, Any]], contracts: dict[Path, str]) -> list[dict]:
    """Registry versus contract disagreement on id, artifacts, or dependency lower bound."""
    conflicts: list[dict[str, Any]] = []
    for component in components:
        directory = component.get("_dir")
        if directory is None:
            continue
        path = directory / component.get("contract", CONTRACT_NAME)
        text = contracts.get(path)
        if text is None:
            conflicts.append({
                "component": component.get("id", "?"),
                "kind": "contract",
                "detail": "declared contract file is missing",
                "registry": component.get("contract", CONTRACT_NAME),
                "contract": "absent",
                "ref": _rel(path),
            })
            continue
        claims = contract_claims(text)
        reference = _rel(path)
        if claims["id"] and claims["id"][0] != component.get("id"):
            conflicts.append({
                "component": component.get("id", "?"),
                "kind": "id",
                "detail": "component id",
                "registry": component.get("id", "?"),
                "contract": claims["id"][0],
                "ref": f"{reference}:{claims['id'][1]}",
            })
        if claims["artifacts"]:
            for artifact in component.get("artifacts", []):
                name = artifact.get("name", "")
                if name and name not in claims["artifacts"]:
                    conflicts.append({
                        "component": component.get("id", "?"),
                        "kind": "artifact",
                        "detail": f"artifact {name}",
                        "registry": name,
                        "contract": "not declared",
                        "ref": f"{reference}:{min(claims['artifacts'].values())}",
                    })
        for dependency in component.get("dependencies", []):
            name = dependency.get("artifact", "")
            claimed = claims["depends"].get(name)
            declared = LOWER_BOUND.search(dependency.get("constraint", ""))
            if claimed and declared and claimed[0] != declared.group(1):
                conflicts.append({
                    "component": component.get("id", "?"),
                    "kind": "dependency",
                    "detail": f"{dependency.get('component', '?')}:{name} lower bound",
                    "registry": f">={declared.group(1)}",
                    "contract": f">={claimed[0]}",
                    "ref": f"{reference}:{claimed[1]}",
                })
    return conflicts


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _excluded(path: Path) -> bool:
    if not EXCLUDE:
        return False
    rel = _rel(path)
    return any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE)


def walk_corpus() -> tuple[list[Path], dict[Path, str]]:
    files: list[Path] = []
    contracts: dict[Path, str] = {}
    stack = [ROOT]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink() or _excluded(entry):
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.name not in SKIP_NAMES and entry.suffix.lower() in INDEXED_SUFFIXES:
                files.append(entry)
    for path in files:
        if path.name == CONTRACT_NAME:
            text = read_text(path)
            if text is not None:
                contracts[path.resolve()] = text
    return files, contracts


def search_notebook(query: Query, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    if not NOTEBOOK_MODULE.is_file():
        return [], "notebook module absent"
    try:
        spec = importlib.util.spec_from_file_location("_hc_notebook", NOTEBOOK_MODULE)
        if spec is None or spec.loader is None:
            return [], "notebook module not loadable"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        notebook = module.InvestigationNotebook(NOTEBOOK_ROOT)
        return notebook.search(" ".join(query.terms), limit), None
    except Exception as error:  # degraded retrieval beats no retrieval
        return [], f"notebook search failed: {type(error).__name__}: {error}"


def collect(query: Query, limit: int) -> dict[str, Any]:
    manifest, problems = load_registry()
    files, contracts = walk_corpus()
    components = registry_components(manifest)

    registry_hits: list[dict[str, Any]] = []
    for component in components:
        identifiers = identifier_tokens(component.get("id", ""))
        identifiers |= {component.get("id", "").lower()}
        directory = component.get("_dir")
        if directory is not None:
            identifiers |= identifier_tokens(directory.name)
            identifiers.add(directory.name.lower())
        artifacts = "; ".join(
            f"{a.get('name', '?')} {a.get('ecosystem', '?')} {a.get('version', '?')}"
            for a in component.get("artifacts", [])
        )
        depends = "; ".join(
            f"{d.get('component', '?')}:{d.get('artifact', '?')}{d.get('constraint', '')}"
            for d in component.get("dependencies", [])
        )
        contributions = "; ".join(
            f"{c.get('kind', '?')}={c.get('entry', '?')}" for c in component.get("contributions", [])
        )
        coverage, score = query.score([
            (component.get("id", "").lower(), 60.0),
            ((_rel(directory) if directory else "").lower(), W_PATH),
            (artifacts.lower(), 34.0),
            (contributions.lower(), 20.0),
            (depends.lower(), 14.0),
            (" ".join(component.get("_consumers", [])).lower(), 14.0),
        ])
        exact = 1 if query.variants & identifiers else 0
        if coverage or exact:
            registry_hits.append({
                "corpus": "registry",
                "id": component.get("id", "?"),
                "path": _rel(directory) if directory else "?",
                "contract": component.get("contract", CONTRACT_NAME),
                "artifacts": artifacts,
                "depends": depends or "none",
                "contributions": contributions,
                "consumers": component.get("_consumers", []),
                "exact": exact,
                "coverage": coverage,
                "score": score,
            })

    scanned = 0
    phrase_files: list[str] = []
    term_files = {term: 0 for term in query.terms}
    notes_dir = NOTES_DIR.resolve()
    candidates: list[tuple[int, float, str, Path]] = []

    # Pass one is cheap and touches every file; per-line work is deferred to the shortlist.
    for path in files:
        resolved = path.resolve()
        if resolved == SELF_PATH:
            continue
        text = read_text(path)
        if text is None:
            continue
        scanned += 1
        relative = _rel(path)
        low_path = relative.lower()
        low = text.lower()
        if query.phrase in low or query.phrase in low_path:
            phrase_files.append(relative)
        body = query.factors(low)
        on_path = query.factors(low_path)
        for term in query.terms:
            if max(body.get(term, 0.0), on_path.get(term, 0.0)) >= 0.6:
                term_files[term] += 1
        if resolved.parent == notes_dir or notes_dir in resolved.parents:
            continue
        if not body and not on_path:
            continue
        head = query.factors("\n".join(text[:4000].splitlines()[:60]).lower())
        best: dict[str, float] = {}
        cheap = 0.0
        for source, weight in ((on_path, W_PATH), (head, W_DOC), (body, W_BODY)):
            for term, factor in source.items():
                cheap += weight * factor
                best[term] = max(best.get(term, 0.0), factor)
        coverage = sum(1 for factor in best.values() if factor >= 0.6)
        if coverage:
            candidates.append((coverage, cheap, relative, path))

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    top_coverage = candidates[0][0] if candidates else 0
    at_top = [c for c in candidates if c[0] == top_coverage]
    shortlist = at_top[:SHORTLIST]

    contract_hits: list[dict[str, Any]] = []
    source_hits: list[dict[str, Any]] = []
    for _, _, relative, path in shortlist:
        text = read_text(path)
        if text is None:
            continue
        lines = text.splitlines()
        suffix = path.suffix.lower()
        header = header_text(lines, suffix)
        symbols = symbols_of(lines, suffix)
        symbol_text = " ".join(name for name, _ in symbols)
        coverage, score = query.score([
            (relative.lower(), W_PATH),
            (symbol_text.lower(), W_SYMBOL),
            (header.lower(), W_DOC),
            (text.lower(), W_BODY),
        ])
        evidence: list[tuple[int, int, str]] = []
        for number, line in enumerate(lines, start=1):
            rank = query.line_rank(line)
            if rank:
                evidence.append((rank, number, snippet(line)))
        # Terms sharing one line is the strongest cheap relevance signal in source text.
        best_line = max((rank for rank, _, _ in evidence), default=0)
        evidence.sort(key=lambda item: (-item[0], item[1]))
        identifiers = identifier_tokens(path.stem) | {path.stem.lower(), path.name.lower()}
        identifiers |= {name.lower() for name, _ in symbols}
        identifiers |= {part.lower() for part in relative.split("/")}
        record = {
            "path": relative,
            "exact": 1 if query.variants & identifiers else 0,
            "coverage": coverage,
            "best_line": best_line,
            "score": score + W_LINE * best_line,
            "symbols": [f"{name}:{number}" for name, number in symbols if query.line_rank(name)][:4],
            "header": snippet(header.replace("\n", " ")) if header else "",
            "matches": len(evidence),
            "lines": [{"line": number, "text": body} for _, number, body in evidence[:2]],
        }
        if path.name == CONTRACT_NAME:
            record["corpus"] = "contracts"
            contract_hits.append(record)
        else:
            record["corpus"] = "source"
            source_hits.append(record)

    conflicts = find_conflicts(components, contracts)
    notebook_hits, notebook_error = search_notebook(query, max(limit, CAPS["notebook"]))
    if notebook_error:
        problems.append(notebook_error)

    def order(hit: dict[str, Any]) -> tuple[Any, ...]:
        return (
            -hit["exact"], -hit["coverage"], -hit["best_line"], -hit["score"], hit.get("path", "")
        )

    registry_hits.sort(key=lambda hit: (-hit["exact"], -hit["coverage"], -hit["score"], hit["id"]))
    contract_hits.sort(key=order)
    source_hits.sort(key=order)

    matched_ids = {hit["id"] for hit in registry_hits[: CAPS["registry"]]}
    shown_conflicts = [c for c in conflicts if c["component"] in matched_ids]

    return {
        "query": query.raw,
        "terms": query.terms,
        "phrase": {
            "text": query.phrase,
            "files": len(phrase_files),
            "present": bool(phrase_files),
            "examples": phrase_files[:3],
        },
        "scanned_files": scanned,
        "term_files": term_files,
        "dropped_terms": query.dropped,
        "term_coverage": top_coverage,
        "matched_files": len(candidates),
        "ranked_files": len(at_top),
        "conflicts": shown_conflicts,
        "conflicts_elsewhere": len(conflicts) - len(shown_conflicts),
        "registry": registry_hits,
        "contracts": contract_hits,
        "source": source_hits,
        "notebook": notebook_hits,
        "problems": problems,
    }


def render(result: dict[str, Any], limit: int) -> str:
    out: list[str] = []
    phrase = result["phrase"]
    out.append(f"query   {result['query']}")
    if phrase["present"]:
        examples = ", ".join(phrase["examples"])
        out.append(
            f"phrase  \"{phrase['text']}\" PRESENT in {phrase['files']} file(s): {examples}"
        )
    else:
        out.append(
            f"phrase  \"{phrase['text']}\" ABSENT \u2014 0 exact matches "
            f"across {result['scanned_files']} files scanned"
        )
    out.append(
        "terms   "
        + "  ".join(f"{term}={count}" for term, count in result["term_files"].items())
        + f"   |  {result['matched_files']} file(s) matched, "
        f"{result['ranked_files']} at best coverage {result['term_coverage']}/{len(result['terms'])}"
    )
    if result["dropped_terms"]:
        out.append(f"ignored {' '.join(result['dropped_terms'])} (stopwords, phrase unaffected)")

    total = (
        len(result["registry"]) + len(result["contracts"])
        + len(result["source"]) + len(result["notebook"])
    )
    if total == 0:
        out.append("")
        out.append(
            f"NOT FOUND \u2014 no registry, contract, source or notebook hit "
            f"for any term across {result['scanned_files']} files. Treat as absent."
        )

    if result["conflicts"]:
        out.append("")
        out.append(f"CONFLICT ({len(result['conflicts'])})")
        for item in result["conflicts"]:
            out.append(
                f"  {item['component']} {item['detail']}: registry {item['registry']} "
                f"vs contract {item['contract']}  {item['ref']}"
            )
        if result["conflicts_elsewhere"] > 0:
            out.append(f"  +{result['conflicts_elsewhere']} conflict(s) in unmatched components")

    def heading(name: str, hits: list[Any], cap: int) -> int:
        shown = min(len(hits), cap)
        omitted = len(hits) - shown
        suffix = f" (+{omitted} omitted)" if omitted else ""
        out.append("")
        out.append(f"{name} ({len(hits)}){suffix}")
        return shown

    if result["registry"]:
        shown = heading("REGISTRY", result["registry"], min(limit, CAPS["registry"]))
        for hit in result["registry"][:shown]:
            out.append(f"  {hit['id']}  {hit['path']}  contract:{hit['contract']}")
            out.append(f"    artifacts: {hit['artifacts']}")
            out.append(f"    depends:   {hit['depends']}")
            consumers = ", ".join(hit["consumers"]) or "none"
            out.append(f"    consumers(DERIVED): {consumers}")

    if result["contracts"]:
        shown = heading("CONTRACTS", result["contracts"], min(limit, CAPS["contracts"]))
        for hit in result["contracts"][:shown]:
            out.append(f"  {hit['path']}  ({hit['matches']} matching lines)")
            for line in hit["lines"]:
                out.append(f"    :{line['line']}  {line['text']}")

    if result["source"]:
        shown = heading("SOURCE", result["source"], min(limit, CAPS["source"]))
        for hit in result["source"][:shown]:
            symbols = "  symbols: " + ", ".join(hit["symbols"]) if hit["symbols"] else ""
            out.append(f"  {hit['path']}  ({hit['matches']} matching lines){symbols}")
            for line in hit["lines"]:
                out.append(f"    :{line['line']}  {line['text']}")

    if result["notebook"]:
        shown = heading("NOTEBOOK", result["notebook"], min(limit, CAPS["notebook"]))
        for note in result["notebook"][:shown]:
            axes = f"{note.get('type', '?')}/{note.get('system', '?')}/{note.get('segment', '?')}"
            terms = note.get("matched_terms")
            out.append(
                f"  {note['id']}  {axes}  terms={terms}  {note.get('status', '?')}"
            )
            out.append(f"    {snippet(note.get('title', ''))}")

    if result["problems"]:
        out.append("")
        out.append("PROBLEMS")
        for problem in result["problems"]:
            out.append(f"  {problem}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="find.py",
        description=(
            "One retrieval call across four corpora: the app component REGISTRY with derived "
            "reverse dependencies, component CONTRACTS, SOURCE file/symbol/docblock text, and "
            "the investigation NOTEBOOK. Absence is reported explicitly with a scanned-file "
            "count, and registry/contract disagreement is reported as a CONFLICT."
        ),
        epilog=(
            'examples:\n'
            '  python3 .github/tools/find.py "collapse explorer"\n'
            '  python3 .github/tools/find.py "cache" --limit 3\n'
            '  python3 .github/tools/find.py "agent canvas" --json\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="words, an identifier, a path, or an exact phrase")
    parser.add_argument(
        "--limit", type=int, default=12, help="max results per corpus (default: per-corpus caps)"
    )
    parser.add_argument("--json", action="store_true", help="emit the full result as JSON")
    arguments = parser.parse_args(argv)
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")

    query = Query(arguments.query)
    result = collect(query, arguments.limit)
    if arguments.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render(result, arguments.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
