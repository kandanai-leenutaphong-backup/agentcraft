#!/usr/bin/env python3
"""Append-only performance log for the overseer.

One JSON object per line, one line per event, never a rewrite — so a write cannot corrupt history
and two writers cannot lose each other's entry. Durations are derived on read, not stored: a
stored duration is a second copy of two timestamps.

Usage:
    python3 .github/tools/oplog.py start "Add the skills index and the overseer log"
    python3 .github/tools/oplog.py start "Timed objective" --limit-seconds 600
    python3 .github/tools/oplog.py check --run <returned-run-id>
    python3 .github/tools/oplog.py end --run <returned-run-id> --achieved
    python3 .github/tools/oplog.py team index "skills index and fitness check"
    python3 .github/tools/oplog.py end index
    python3 .github/tools/oplog.py end
    python3 .github/tools/oplog.py record thinking --seconds 42 --agent orchestrator
    python3 .github/tools/oplog.py record code --seconds 120 --tokens 8100 --source "host usage panel"
    python3 .github/tools/oplog.py report --run r-20260907T053119Z --json --output run.json

The run identifier defaults to the most recent open run, so it never has to be carried around.
`--run` overrides that when two runs overlap.
Standard library only.
check appends and prints UTC, elapsed/remaining seconds and cumulative penalty_minutes:
one point per started overdue minute, frozen only by end --achieved after verified closure.
No limit means no deadline penalty. The tool records attestations; it cannot verify acceptance
or enforce agent scheduling. Monotonic readings are comparable on the same Linux boot;
otherwise clock_basis explicitly reports wall_clock_fallback. Always pass --run and --log
in delegated work. Do not sum cumulative penalties or overlapping parent/child elapsed times.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / ".github" / "overseer-log.jsonl"
PHASES = ("thinking", "reasoning", "planning", "reading", "code", "verification", "other")


def clock() -> dict[str, Any]:
    boot = Path("/proc/sys/kernel/random/boot_id")
    return {"checked_at": datetime.now(timezone.utc).isoformat(),
            "monotonic": time.monotonic(),
            "boot_id": boot.read_text().strip() if boot.is_file() else None}


def timing(log: Path, run: str, achieved: bool = False) -> dict[str, Any]:
    events = [event for event in read(log) if event.get("run") == run]
    start = next((event for event in events if event.get("event") == "run_start"), None)
    if start is None:
        raise SystemExit(f"unknown run: {run}")
    observed = clock()
    settled = next((event for event in events if event.get("objective_achieved")), None)
    if settled:
        return {key: value for key, value in settled.items()
                if key not in ("event", "run", "ts")} | observed
    same_boot = (observed["boot_id"] is not None
                 and observed["boot_id"] == start.get("boot_id")
                 and "monotonic" in start)
    if same_boot:
        elapsed = observed["monotonic"] - start["monotonic"]
    else:
        elapsed = (datetime.fromisoformat(observed["checked_at"])
                   - datetime.fromisoformat(start.get("checked_at", start["ts"]))).total_seconds()
    if elapsed < 0:
        raise SystemExit("clock moved backwards; elapsed time cannot be measured reliably")
    limit = start.get("limit_seconds")
    overdue = max(0.0, elapsed - limit) if limit is not None else 0.0
    return {**observed, "started_at": start.get("checked_at", start["ts"]),
            "elapsed_seconds": elapsed,
            "clock_basis": "monotonic" if same_boot else "wall_clock_fallback",
            "limit_seconds": limit,
            "remaining_seconds": limit - elapsed if limit is not None else None,
            "overrun_seconds": overdue,
            "penalty_minutes": math.ceil(overdue / 60),
            "completed_at": observed["checked_at"] if achieved else None,
            "objective_achieved": achieved}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(event: dict[str, Any], log: Path) -> dict[str, Any]:
    event["ts"] = now()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read(log: Path) -> list[dict[str, Any]]:
    if not log.is_file():
        return []
    events = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a truncated tail must not make the whole history unreadable
    return events


def seconds(start: str, end: str) -> int:
    return int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def runs(log: Path) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for event in read(log):
        run = event.get("run")
        if not run:
            continue
        entry = collected.setdefault(run, {"run": run, "task": "", "started": event["ts"],
                                           "ended": None, "teams": {}, "phases": []})
        kind = event.get("event")
        if kind == "run_start":
            entry["task"] = event.get("task", "")
            entry["started"] = event["ts"]
        elif kind == "run_end":
            entry["ended"] = event["ts"]
        elif kind == "phase":
            entry["phases"].append({"phase": event.get("phase"),
                                    "seconds": event.get("seconds"),
                                    "tokens": event.get("tokens"),
                                    "source": event.get("source"),
                                    "agent": event.get("agent"),
                                    "ts": event["ts"]})
        elif kind == "team_start":
            entry["teams"][event["team"]] = {"team": event["team"], "task": event.get("task", ""),
                                             "started": event["ts"], "ended": None}
        elif kind == "team_end":
            team = entry["teams"].get(event["team"])
            if team:
                team["ended"] = event["ts"]
    for entry in collected.values():
        for team in entry["teams"].values():
            closed = team["ended"] or entry["ended"]
            team["seconds"] = seconds(team["started"], closed) if closed else None
            team["open"] = team["ended"] is None
        entry["seconds"] = seconds(entry["started"], entry["ended"]) if entry["ended"] else None
        entry["open"] = entry["ended"] is None
    return sorted(collected.values(), key=lambda e: e["started"])


def current(log: Path, requested: str | None) -> str:
    if requested:
        return requested
    for entry in reversed(runs(log)):
        if entry["open"]:
            return entry["run"]
    raise SystemExit("no open run; start one with: oplog.py start \"<task>\"")


def render(entries: list[dict[str, Any]]) -> str:
    lines = []
    for entry in entries:
        lines.append(f"Task: {entry['task']}")
        if entry["teams"]:
            lines.append("Teams Chartered: {")
            for team in entry["teams"].values():
                measure = "open" if team["open"] else f"{team['seconds']}s"
                lines.append(f"    {team['team']}: {{")
                lines.append(f"        Task: {team['task']}")
                lines.append(f"        Time (Seconds): {measure}")
                lines.append("    }")
            lines.append("}")
        if entry.get("phases"):
            lines.append("Measured Phases: {")
            for phase in entry["phases"]:
                who = f" [{phase['agent']}]" if phase.get("agent") else ""
                tokens = phase["tokens"]
                token_text = "unknown" if tokens is None else f"{tokens} ({phase['source']})"
                lines.append(f"    {phase['phase']}{who}: {phase['seconds']}s, "
                             f"tokens {token_text}")
            lines.append("}")
            measured = sum(p["seconds"] for p in entry["phases"])
            counted = [p for p in entry["phases"] if p["tokens"] is not None]
            lines.append(f"Measured Phase Seconds (may overlap wall time): {measured}")
            lines.append(f"Reported Tokens ({len(counted)}/{len(entry['phases'])} phases "
                         f"reported): {sum(p['tokens'] for p in counted) if counted else 'unknown'}")
        total = "open" if entry["open"] else entry["seconds"]
        lines.append(f"Total Time (Seconds): {total}")
        lines.append("")
    return "\n".join(lines).rstrip() or "no runs recorded"


def positive_seconds(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("seconds must be a number")
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("seconds must be finite and not negative")
    return number


def token_count(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("tokens must be a whole number")
    if number < 0:
        raise argparse.ArgumentTypeError("tokens must not be negative")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("start", "check", "team", "end", "record", "report"))
    parser.add_argument("name", nargs="?", help="task sentence for start; team name otherwise")
    parser.add_argument("task", nargs="?", help="what the team was chartered to do")
    parser.add_argument("--phase", choices=PHASES, help="phase for record; or give it positionally")
    parser.add_argument("--seconds", type=positive_seconds, help="measured wall seconds")
    parser.add_argument("--tokens", type=token_count, help="host-reported token count")
    parser.add_argument("--source", help="where the token count came from; required with --tokens")
    parser.add_argument("--agent", help="which agent the measurement belongs to")
    parser.add_argument("--limit-seconds", type=positive_seconds,
                        help="explicit user time limit; start only")
    parser.add_argument("--achieved", action="store_true",
                        help="attest verified objective and closure; end only")
    parser.add_argument("--run", help="run id; defaults to the most recent open run")
    parser.add_argument("--log", default=str(LOG))
    parser.add_argument("--last", type=int, default=5, help="how many runs to report")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--output", help="write the report to this file instead of stdout")
    args = parser.parse_args(argv)
    log = Path(args.log)
    if args.limit_seconds is not None and args.verb != "start":
        parser.error("--limit-seconds is valid only for start; never reset a deadline")
    if args.achieved and (args.verb != "end" or args.name):
        parser.error("--achieved requires end of the whole run")

    if args.verb == "start":
        if not args.name:
            parser.error("start needs the task in one sentence")
        run = "r-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        taken = {entry["run"] for entry in runs(log)}
        if run in taken:  # two runs started inside the same second must stay distinct
            run = next(f"{run}-{n}" for n in range(2, 1000) if f"{run}-{n}" not in taken)
        append({"event": "run_start", "run": run, "task": args.name,
                "limit_seconds": args.limit_seconds, **clock()}, log)
        print(run)
    elif args.verb == "check":
        if not args.run:
            parser.error("check requires --run to avoid timing another task")
        measured = timing(log, args.run)
        append({"event": "time_check", "run": args.run, **measured}, log)
        print(json.dumps(measured))
    elif args.verb == "team":
        if not args.name:
            parser.error("team needs a name")
        append({"event": "team_start", "run": current(log, args.run),
                "team": args.name, "task": args.task or ""}, log)
    elif args.verb == "end":
        run = current(log, args.run)
        if args.name:
            append({"event": "team_end", "run": run, "team": args.name}, log)
        else:
            measured = timing(log, run, args.achieved)
            append({"event": "run_end", "run": run, **measured}, log)
            print(json.dumps(measured))
    elif args.verb == "record":
        phase = args.phase or args.name
        if phase not in PHASES:
            parser.error(f"record needs a phase, one of: {', '.join(PHASES)}")
        if args.seconds is None:
            parser.error("record needs --seconds, measured from a clock")
        if args.tokens is not None and not args.source:
            parser.error("--tokens needs --source naming where the count came from")
        append({"event": "phase", "run": current(log, args.run), "phase": phase,
                "seconds": args.seconds, "tokens": args.tokens,
                "source": args.source, "agent": args.agent}, log)
    else:
        entries = runs(log)
        if args.run:
            entries = [e for e in entries if e["run"] == args.run]
        entries = entries[-args.last:]
        text = json.dumps(entries, indent=2) if args.as_json else render(entries)
        if args.output:
            out = Path(args.output)
            if out.resolve() == log.resolve():
                parser.error("--output must not overwrite the log")
            tmp = out.with_name(out.name + ".tmp")
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text + "\n", encoding="utf-8")
            tmp.replace(out)
            print(out)
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
