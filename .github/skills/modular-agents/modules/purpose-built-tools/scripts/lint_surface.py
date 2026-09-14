#!/usr/bin/env python3
"""lint_surface.py — check a tool surface against the affordance rules.

Usage:
    python3 scripts/lint_surface.py mytools/tools.py
    python3 scripts/lint_surface.py mytools/tools.py --max-tools 6
    python3 scripts/lint_surface.py mytools/tools.py --catalogue SURFACE.md
    python3 scripts/lint_surface.py mytools/tools.py --strict      # warnings fail

Loads the module, finds every function decorated with ``@purpose_built``,
and checks the rules that can be checked mechanically: every tool says what
it is for and when to call it, every parameter is described and validated,
every parameter says where its value comes from, repeat calls are
identified, and the surface is not wider than its budget.

What it cannot check is whether ``call_when`` is *true* and whether two
tools genuinely differ. That is what the weight meter and a reviewer are
for.

Exit codes:
    0  no errors (warnings may be present)
    1  at least one error, or --strict with warnings
    2  the module could not be loaded
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toolshape import catalogue, lint, specs_in  # noqa: E402


def load_module(path: Path):
    """Import a module from a file path without requiring it on sys.path."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before executing: a module that imports itself by name during
    # execution would otherwise get a second, half-built copy.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module", help="python file declaring the tools")
    parser.add_argument("--max-tools", type=int, default=8)
    parser.add_argument("--catalogue", default="", help="also write the surface page here")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    path = Path(args.module)
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return 2
    try:
        module = load_module(path)
    except Exception as exc:
        print(f"could not load {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    specs = specs_in(module)
    if not specs:
        print(f"no @purpose_built tools found in {path}", file=sys.stderr)
        return 2

    print(f"linting {len(specs)} tool(s) in {path}\n")
    findings = lint(specs, max_tools=args.max_tools)
    for finding in findings:
        print(f"  {finding}")
    if not findings:
        print("  clean")

    if args.catalogue:
        Path(args.catalogue).write_text(catalogue(specs), encoding="utf-8")
        print(f"\nwrote {args.catalogue}")

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warn"]
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
