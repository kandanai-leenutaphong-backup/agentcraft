#!/usr/bin/env python3
"""Report documentation that no longer matches the repository.

A stale document costs more than a missing one. Agents here treat documents as authorities, so a
README naming a deleted path sends work down a road that ended months ago. Finds claims a document
makes about the repository that are no longer true, cheaply, executing nothing.

Checks, per markdown file:
  - relative links whose target does not exist;
  - inline code that looks like a repository path and does not exist;
  - commands in fenced blocks that invoke a script that does not exist.

Usage:
    python3 .github/tools/docaudit.py
    python3 .github/tools/docaudit.py --json
    python3 .github/tools/docaudit.py --path docs

Report only. Placeholders, globs and URLs are skipped; judgement is still required, since a
reported path may be one a document intends to create rather than describe.

Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".pytest_cache",
    "site-packages", ".next", ".vite", ".turbo", ".cache", "coverage", ".vocs", "htmlcov",
    ".agent-harness", "notes", "drafts", "upstream",
}

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
SCRIPT_CALL = re.compile(
    r"(?:^|\|\s*|&&\s*)(?:\./|(?:python3?|bash|sh|node|npx)\s+)([\w./@-]+\.(?:sh|py|mjs|cjs|js|ts))"
)
# A placeholder, a glob or a shell expansion is not a claim about a path that exists.
PLACEHOLDER = re.compile(r"[<>{}*?$|]|TODO|\.\.\.|\bexample\b")
PATHISH = re.compile(r"^[\w.@-]+(?:/[\w.@-]+)+/?$")
KNOWN_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".md", ".json", ".yml", ".yaml",
    ".toml", ".bicep", ".css", ".html", ".sql", ".txt", ".env", ".cfg", ".ini",
}


def markdown_files(root: Path, subpath: str | None) -> list[Path]:
    excluded = _excludes(root)
    base = root / subpath if subpath else root
    found: list[Path] = []
    stack = [base]
    while stack:
        directory = stack.pop()
        if not directory.is_dir():
            return [base] if base.is_file() else []
        for entry in sorted(directory.iterdir()):
            rel = entry.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, pattern) for pattern in excluded):
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS and not entry.is_symlink():
                    stack.append(entry)
            elif entry.suffix == ".md":
                found.append(entry)
    return sorted(found)


def _excludes(root: Path) -> tuple[str, ...]:
    try:
        config = json.loads((root / ".agent-harness.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return ()
    return tuple(config.get("exclude") or ())


def exists(root: Path, reference: str, relative_to: Path) -> bool:
    candidate = reference.split("#", 1)[0].rstrip("/")
    if not candidate:
        return True
    for base in (relative_to.parent, root):
        if (base / candidate).exists():
            return True
    return False


def audit_file(path: Path, root: Path, ignore: list[str]) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []

    def ignored(reference: str) -> bool:
        return any(fnmatch.fnmatch(reference, pattern) for pattern in ignore)

    def line_of(needle: str) -> int:
        for index, line in enumerate(lines, start=1):
            if needle in line:
                return index
        return 0

    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")) or PLACEHOLDER.search(target):
            continue
        if not ignored(target) and not exists(root, target, path):
            findings.append({"kind": "broken-link", "reference": target, "line": line_of(target)})

    fenced = "".join(FENCE.findall(text))
    for span in INLINE_CODE.findall(text):
        candidate = span.strip()
        if PLACEHOLDER.search(candidate) or not PATHISH.match(candidate):
            continue
        suffix = Path(candidate.rstrip("/")).suffix
        if suffix and suffix not in KNOWN_SUFFIXES:
            continue
        if not suffix and not candidate.endswith("/"):
            continue  # a bare dotted name is more likely a module than a path
        if not ignored(candidate) and not exists(root, candidate, path):
            findings.append({"kind": "missing-path", "reference": candidate, "line": line_of(candidate)})

    for script in SCRIPT_CALL.findall(fenced):
        if PLACEHOLDER.search(script) or ignored(script):
            continue
        if not exists(root, script, path):
            findings.append({"kind": "missing-script", "reference": script, "line": line_of(script)})

    seen: set[tuple[str, str]] = set()
    unique = []
    for finding in findings:
        key = (finding["kind"], finding["reference"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def audit(root: Path, subpath: str | None, ignore: list[str]) -> dict[str, Any]:
    documents = markdown_files(root, subpath)
    stale: list[dict[str, Any]] = []
    for path in documents:
        findings = audit_file(path, root, ignore)
        if findings:
            stale.append({"document": path.relative_to(root).as_posix(), "findings": findings})
    return {
        "documents_scanned": len(documents),
        "documents_with_findings": len(stale),
        "findings": sum(len(entry["findings"]) for entry in stale),
        "stale": stale,
    }


def render(result: dict[str, Any]) -> str:
    lines = [f"scanned {result['documents_scanned']} document(s); "
             f"{result['findings']} claim(s) in {result['documents_with_findings']} document(s) "
             f"no longer hold"]
    for entry in result["stale"]:
        lines.append(f"\n{entry['document']}")
        for finding in entry["findings"]:
            where = f":{finding['line']}" if finding["line"] else ""
            lines.append(f"  {finding['kind']}{where}  {finding['reference']}")
    if not result["stale"]:
        lines.append("every checked claim resolves")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report documentation that no longer matches the repository.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--path", default=None, help="limit to a subdirectory or one file")
    parser.add_argument("--ignore", action="append", default=[], metavar="GLOB",
                        help="reference pattern to skip; repeatable. Use for paths a document "
                             "describes in another tree, such as an install destination")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    result = audit(Path(args.root).resolve(), args.path, args.ignore)
    print(json.dumps(result, indent=2) if args.as_json else render(result))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
