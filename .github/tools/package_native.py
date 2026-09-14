#!/usr/bin/env python3
"""Materialize native plugin discovery from authored protocols, agents and instructions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def native_files(root: Path) -> dict[str, str]:
    core = root / "core"
    protocols = json.loads((core / "protocols/catalogue.json").read_text())["protocols"]
    outputs = {}
    for protocol in protocols:
        document = core / "protocols" / protocol["path"]
        if not document.resolve().is_relative_to((core / "protocols").resolve()) or not document.is_file():
            raise ValueError("Protocol entry escapes its authored directory or is absent")
    agents = sorted((core / "agents").glob("*.agent.md")) + sorted(root.glob("modules/*/agents/*.agent.md"))
    for agent in agents:
        relative = f"com.github.copilot/agents/{agent.name}"
        if relative in outputs:
            raise ValueError(f"Two agents own {relative}")
        text = agent.read_text(encoding="utf-8")
        text = re.sub(r"\]\(\.\./(skills|protocols|instructions)/", r"](../../\1/", text)
        outputs[relative] = text
    for instruction in sorted((core / "instructions").glob("*.instructions.md")):
        text = instruction.read_text(encoding="utf-8")
        text = re.sub(r"\]\(\.\./(skills|protocols|instructions)/", r"](../../\1/", text)
        outputs[f"com.github.copilot/rules/{instruction.name}"] = text
    return outputs


def native_catalogue(root: Path) -> str:
    core = root / "core"
    document = json.loads((core / "skills/catalogue.json").read_text())
    authored = [entry for entry in document["skills"] if not entry.get("protocol")]
    for protocol in json.loads((core / "protocols/catalogue.json").read_text())["protocols"]:
        name = protocol["name"] if protocol["name"].startswith("protocol-") else "protocol-" + protocol["name"]
        if any(entry["name"] == name for entry in authored):
            raise ValueError(f"Workflow name collides with authored skill: {name}")
        authored.append({"name": name, "summary": protocol["summary"], "access": "native workflow skill",
                         "protocol": protocol["name"], "keywords": protocol.get("keywords", [])})
    document["skills"] = sorted(authored, key=lambda entry: entry["name"])
    return json.dumps(document, indent=2) + "\n"


def materialize(root: Path, *, check: bool = False) -> list[str]:
    core = root / "core"
    outputs = native_files(root)
    authored_protocols = {f"protocols/{protocol['path']}" for protocol in
                          json.loads((core / "protocols/catalogue.json").read_text())["protocols"]}
    previous_path = core / "native-manifest.json"
    if previous_path.is_symlink():
        raise ValueError("Native manifest must not be a symlink")
    previous_document = json.loads(previous_path.read_text()) if previous_path.is_file() else {"schema_version": 1, "files": {}}
    if not isinstance(previous_document, dict) or previous_document.get("schema_version") != 1 or not isinstance(previous_document.get("files"), dict):
        raise ValueError("Invalid previous native manifest")
    previous = previous_document["files"]
    stale = []
    for relative, expected in previous.items():
        if not re.fullmatch(r"(?:skills|protocols)/protocol-[a-z0-9-]+/SKILL\.md|com\.github\.copilot/(?:agents/[\w-]+\.agent|rules/[\w-]+\.instructions)\.md", relative):
            raise ValueError("Previous native manifest claims a path outside generated ownership")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Invalid previous native hash")
        if relative in outputs:
            continue
        target = core / relative
        if target.is_symlink() or not target.resolve().is_relative_to(core.resolve()):
            raise ValueError("Previous native manifest contains an escaping path")
        if relative in authored_protocols:
            continue
        if target.is_file():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Retired native file was edited: {relative}; preserve it before regenerating")
            stale.append(relative)
    manifest = {"schema_version": 1, "generator": "tools/package_native.py", "files": {
        relative: hashlib.sha256(text.encode()).hexdigest() for relative, text in sorted(outputs.items())}}
    outputs["native-manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    outputs["skills/catalogue.json"] = native_catalogue(root)
    changed = list(stale)
    if not check:
        for relative in stale:
            (core / relative).unlink()
    for relative, text in outputs.items():
        target = core / relative
        if target.is_symlink() or not target.resolve().is_relative_to(core.resolve()):
            raise ValueError(f"Refusing escaped generated target: {relative}")
        if target.is_file() and target.read_text(encoding="utf-8") == text:
            continue
        changed.append(relative)
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    changed = materialize(options.root.resolve(), check=options.check)
    if options.check and changed:
        print("Native package is stale: " + ", ".join(changed))
        return 1
    print(f"Native package {'verified' if options.check else 'generated'}: {len(changed)} changed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())