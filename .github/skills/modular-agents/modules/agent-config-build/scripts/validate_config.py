#!/usr/bin/env python3
"""validate_config.py — lint an agent control tree before it reaches a runtime.

Usage:
    python3 scripts/validate_config.py <control-dir> \\
        [--allow-prefix my_tools.] [--import-path .] [--strict]

Every check here catches a failure that otherwise appears as a working boot
followed by wrong behaviour: an agent with no prompt, a tool that silently
never loaded, a display name for a tool nobody uses. Run it in CI on every
change to the control tree.

Exits non-zero on any error. Warnings are advisory unless --strict.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agentconfig
from agentconfig import PromptLoadError
from agentconfig._config import _RESERVED_KEYS


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"  ok   {msg}")

    def warn(self, msg: str) -> None:
        print(f"  warn {msg}")
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        print(f"  ERR  {msg}")
        self.errors.append(msg)


def check_config(control: Path, prefixes: tuple[str, ...], r: Report) -> None:
    print("config")
    try:
        cfg = agentconfig.load_agent_config()
    except Exception as exc:
        r.error(f"config failed to load: {exc}")
        return
    if not cfg:
        r.error(f"no agent_config.yaml found under {control}")
        return
    r.ok(f"loaded, top-level keys: {sorted(cfg)}")

    # `include` is consumed by the merge, so the fragment list only exists in
    # the raw base file. Reading the merged config here would always see none.
    import yaml
    base_raw = yaml.safe_load(
        (control / "agent_config.yaml").read_text(encoding="utf-8")) or {}
    fragments = base_raw.get("include") or []
    if fragments:
        r.ok(f"{len(fragments)} include fragment(s): {fragments}")
    else:
        r.warn("no include: fragments — the roster lives entirely in the base file")

    try:
        block = agentconfig.load_agents_block()
    except ValueError as exc:
        r.error(str(exc))
        return

    ids = [aid for aid, _ in agentconfig.iter_agents(block)]
    r.ok(f"{len(ids)} agent(s): {ids}")

    default = block.get("default")
    if not default:
        r.warn("no 'default' agent declared in the base agents: block")
    elif default not in ids:
        r.error(f"default agent '{default}' is not a defined agent id")
    else:
        r.ok(f"default agent '{default}' resolves")

    # A fragment key that is neither `agents:` nor `tool_display_names:` is
    # parsed and discarded by the merge (GOTCHAS.md G4). Silent data loss.
    for rel in fragments:
        frag_path = (control / str(rel)).resolve()
        if not frag_path.exists():
            r.error(f"include fragment missing: {frag_path}")
            continue
        frag = yaml.safe_load(frag_path.read_text(encoding="utf-8")) or {}
        dropped = sorted(set(frag) - {"agents", "tool_display_names"})
        if dropped:
            r.warn(f"{frag_path.name}: keys dropped by merge (G4): {dropped}")


def check_agents(prefixes: tuple[str, ...], r: Report) -> None:
    print("agents")
    try:
        block = agentconfig.load_agents_block()
    except ValueError:
        return

    for agent_id, cfg in agentconfig.iter_agents(block):
        if agent_id in _RESERVED_KEYS:
            continue
        problems: list[str] = []

        if not cfg.get("model"):
            problems.append("no model")
        if not cfg.get("name"):
            r.warn(f"{agent_id}: no name — pickers will show the raw id")
        if not cfg.get("description"):
            r.warn(f"{agent_id}: no description")

        try:
            spec = agentconfig.build_spec(agent_id, allowed_prefixes=prefixes)
        except PromptLoadError as exc:
            r.error(f"{agent_id}: prompts unresolved — {exc}")
            continue
        except Exception as exc:
            r.error(f"{agent_id}: {type(exc).__name__}: {exc}")
            continue

        if not spec.instructions.strip():
            problems.append("empty system prompt")
        if problems:
            r.error(f"{agent_id}: {', '.join(problems)}")
        else:
            r.ok(f"{agent_id}: {len(spec.tools)} tool(s), "
                 f"{len(spec.instructions)} prompt chars")


def check_display_names(prefixes: tuple[str, ...], r: Report) -> None:
    print("tool display names")
    names = agentconfig.get_tool_display_names()
    if not names:
        r.warn("no tool_display_names — a UI will show raw function names")
        return

    referenced: set[str] = set()
    try:
        block = agentconfig.load_agents_block()
    except ValueError:
        return
    for _, cfg in agentconfig.iter_agents(block):
        for spec in cfg.get("tools") or []:
            text = str(spec)
            if text.startswith("@server:"):
                referenced.add(text.split(":")[1])
            elif ":" in text:
                referenced.add(text.rsplit(":", 1)[1])

    missing = sorted(referenced - set(names))
    if missing:
        r.warn(f"tools with no display name: {missing}")
    else:
        r.ok(f"every referenced tool has a display name ({len(referenced)})")

    stale = sorted(set(names) - referenced)
    if stale:
        r.warn(f"display names for tools no agent uses: {stale}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint an agent control tree.")
    ap.add_argument("control", help="directory holding agent_config.yaml")
    ap.add_argument("--allow-prefix", action="append", default=[],
                    help="importable tool-module prefix; repeatable")
    ap.add_argument("--import-path", action="append", default=[],
                    help="directory to add to sys.path so tool modules import")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    args = ap.parse_args()

    control = Path(args.control).resolve()
    if not control.is_dir():
        print(f"not a directory: {control}", file=sys.stderr)
        return 2

    for extra in args.import_path:
        sys.path.insert(0, str(Path(extra).resolve()))

    prefixes = tuple(args.allow_prefix)
    agentconfig.configure(control, allowed_tool_prefixes=prefixes)

    print(f"validating control tree: {control}\n")
    r = Report()
    check_config(control, prefixes, r)
    check_agents(prefixes, r)
    check_display_names(prefixes, r)

    print()
    if r.errors:
        print(f"FAILED: {len(r.errors)} error(s), {len(r.warnings)} warning(s)")
        return 1
    if args.strict and r.warnings:
        print(f"FAILED (strict): {len(r.warnings)} warning(s)")
        return 1
    print(f"PASSED: 0 errors, {len(r.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
