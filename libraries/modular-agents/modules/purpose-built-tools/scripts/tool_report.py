#!/usr/bin/env python3
"""tool_report.py — score a tool surface from recorded calls.

Usage:
    python3 scripts/tool_report.py calls.jsonl
    python3 scripts/tool_report.py calls.jsonl --outcomes outcomes.json
    python3 scripts/tool_report.py calls.jsonl --out results/iteration_4
    python3 scripts/tool_report.py calls.jsonl --fail-on-review     # for CI

Inputs:
    calls.jsonl   one CallRecord per line, written by JsonlSink.
    outcomes.json optional list of {"case_id", "gates": {...}, "split"}.
                  Without it the usage and failure rates still compute; only
                  the outcome-association columns are omitted.

Outputs (to --out, or stdout when omitted):
    TOOL_WEIGHT.md    the reviewable table, signals and candidates
    tool_weight.json  the same, machine-readable

Exit codes:
    0  report produced
    1  --fail-on-review was given and at least one tool is flagged
    2  no usable records

A flag is a hypothesis. The causal test is the ablation protocol in
CONTRACT.md §6 — remove one tool, change nothing else, re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toolshape import aggregate, load_outcomes, read_records, render_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("records", help="JSONL file of call records")
    parser.add_argument("--outcomes", default="", help="outcomes JSON file")
    parser.add_argument("--out", default="", help="directory to write the report into")
    parser.add_argument("--title", default="Tool weight")
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="exit 1 when any tool is flagged for review",
    )
    args = parser.parse_args()

    records_path = Path(args.records)
    if not records_path.is_file():
        print(f"no such record file: {records_path}", file=sys.stderr)
        return 2

    records = list(read_records(records_path))
    if not records:
        print(f"no usable call records in {records_path}", file=sys.stderr)
        return 2

    outcomes = load_outcomes(args.outcomes) if args.outcomes else []
    report = aggregate(records, outcomes)
    markdown = render_markdown(report, title=args.title)
    payload = json.dumps(report.to_dict(), indent=2)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "TOOL_WEIGHT.md").write_text(markdown, encoding="utf-8")
        (out_dir / "tool_weight.json").write_text(payload, encoding="utf-8")
        print(f"wrote {out_dir / 'TOOL_WEIGHT.md'}")
        print(f"wrote {out_dir / 'tool_weight.json'}")
    else:
        print(markdown)

    candidates = report.candidates()
    if candidates:
        print(
            f"{len(candidates)} tool(s) flagged for review: "
            + ", ".join(c.name for c in candidates),
            file=sys.stderr,
        )
        if args.fail_on_review:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
