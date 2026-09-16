"""The weight meter — does each tool pull its weight, or burn turns?

WHY THIS EXISTS
---------------
Past two or three tools, "should this tool exist?" stops being answerable
by taste. Every tool costs the caller attention on every decision it makes,
so a tool that is rarely reached, frequently malformed, or reliably empty
is a tax paid on every turn for an occasional payoff. The only way to know
which is which is to count.

This module turns a stream of call records into a per-tool table:

    total_calls          every observed invocation
    runs_using (%)       runs in which it was called at least once
    cases_touched        distinct tasks that reached for it
    avg_calls_per_run    intensity when used
    error_rate           calls returning a failure envelope
    refusal_rate         calls rejected at the input boundary
    duplicate_rate       calls that repeated an earlier identical call
    unproductive_rate    error OR empty OR refused OR duplicate OR missing
    association          outcome rate among tasks that used it vs did not
    signal               strong / ok / noisy but associated / review

Each rate answers a different design question, which is why they are not
collapsed:

* A high **error rate** means the caller cannot form a valid call. That is
  usually an argument the caller must author — a raw query string — and the
  fix is to shape the tool, not to prompt harder.
* A high **refusal rate** means the caller cannot satisfy the *validator*.
  Grouped by parameter, it names the exact affordance that is wrong: the
  free-text field that should be an enum, the identifier whose source is
  undocumented.
* A high **duplicate rate** means the result did not look like an answer.
  Almost always a missing scope block, not a confused caller.
* A high **empty rate** with valid inputs means the tool is asking the
  backend the wrong question.

ASSOCIATION IS NOT CAUSATION
----------------------------
The used-versus-unused outcome columns are descriptive. They say "tasks
that used this tool succeeded at rate X, tasks that did not at rate Y", and
they are confounded by which tasks are hard. The signal column flags a
*hypothesis*. The causal test is ablation: remove the tool, change nothing
else, re-run, and keep the removal only if outcomes hold and noise falls.
The protocol is in ``CONTRACT.md`` §6, and it exists because a tool with a
44% error rate was ablated here and outcomes regressed — it was doing real
work some of the time (GOTCHAS.md G2).

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ._envelope import (
    DUPLICATE,
    EMPTY,
    ERROR,
    MISSING,
    PRODUCTIVE,
    REFUSED,
    TURN_COST_CLASSES,
    UNPRODUCTIVE_CLASSES,
)
from ._ledger import CallRecord

# Tuning constants. Documented, not magic — every one of them is a place a
# reviewer may reasonably disagree, and disagreeing should mean changing a
# number here rather than reinterpreting a table.
LOW_USAGE_PCT = 15.0      # reached in fewer than this share of runs: rarely used
HIGH_UNPRODUCTIVE = 0.50  # at or above: noisy
HIGH_ERROR = 0.40         # at or above: the caller cannot form a valid call
HIGH_REFUSAL = 0.25       # at or above: advisory — the input contract is wrong
HIGH_DUPLICATE = 0.20     # at or above: advisory — the result does not read as an answer
MIN_ASSOC_N = 2           # smallest unused arm that counts as evidence

# Outcome bands treated as a (partial) success for association.
POSITIVE_BANDS = ("pass", "partial")

SIGNAL_STRONG = "strong"
SIGNAL_OK = "ok"
SIGNAL_NOISY_ASSOCIATED = "noisy but associated"
SIGNAL_REVIEW = "review / cull candidate"


@dataclass
class Outcome:
    """How one task turned out, per gate.

    ``gates`` is an open dict — ``{"detect": "pass", "explain": "partial"}``
    — because what a task is graded on is domain knowledge. The meter reads
    the bands, never the gate names.
    """

    case_id: str
    gates: dict[str, str] = field(default_factory=dict)
    split: str = ""


@dataclass
class ToolStat:
    """Aggregated weight statistics for one tool."""

    name: str
    total_calls: int = 0
    runs_using: int = 0
    cases_touched: int = 0
    classes: Counter = field(default_factory=Counter)
    refusal_params: Counter = field(default_factory=Counter)
    association: dict[str, Any] = field(default_factory=dict)
    signal: str = ""
    reason: str = ""

    @property
    def unproductive_calls(self) -> int:
        return sum(self.classes[c] for c in UNPRODUCTIVE_CLASSES)

    def _rate(self, *classes: str) -> float | None:
        """Share of calls in the given classes. None when nothing observed."""
        if not self.total_calls:
            return None
        return sum(self.classes[c] for c in classes) / self.total_calls

    def error_rate(self) -> float | None:
        return self._rate(ERROR)

    def refusal_rate(self) -> float | None:
        return self._rate(REFUSED)

    def duplicate_rate(self) -> float | None:
        return self._rate(DUPLICATE)

    def empty_rate(self) -> float | None:
        return self._rate(EMPTY)

    def unproductive_rate(self) -> float | None:
        return self._rate(*UNPRODUCTIVE_CLASSES)

    def turn_cost_rate(self) -> float | None:
        """Every class that consumed a turn without returning data.

        Reported, never used to decide a cull: a refusal and a duplicate
        both hand the caller a next step (GOTCHAS.md G13).
        """
        return self._rate(*TURN_COST_CLASSES)

    def avg_calls_per_run(self) -> float | None:
        return (self.total_calls / self.runs_using) if self.runs_using else None

    def to_dict(self, total_runs: int, total_cases: int) -> dict[str, Any]:
        def pct(value: float | None) -> float | None:
            return round(value, 4) if value is not None else None

        return {
            "name": self.name,
            "total_calls": self.total_calls,
            "runs_using": self.runs_using,
            "runs_using_pct": round(100 * self.runs_using / total_runs, 1)
            if total_runs else 0.0,
            "cases_touched": self.cases_touched,
            "cases_touched_pct": round(100 * self.cases_touched / total_cases, 1)
            if total_cases else 0.0,
            "avg_calls_per_run": round(self.avg_calls_per_run(), 2)
            if self.avg_calls_per_run() is not None else None,
            "counts": {name: self.classes[name] for name in sorted(self.classes)},
            "error_rate": pct(self.error_rate()),
            "refusal_rate": pct(self.refusal_rate()),
            "duplicate_rate": pct(self.duplicate_rate()),
            "empty_rate": pct(self.empty_rate()),
            "unproductive_rate": pct(self.unproductive_rate()),
            "turn_cost_rate": pct(self.turn_cost_rate()),
            "top_refused_parameters": self.refusal_params.most_common(3) or None,
            "outcome_association": self.association or None,
            "signal": self.signal,
            "reason": self.reason,
        }


@dataclass
class Report:
    """Everything the meter computed for one iteration."""

    tools: list[ToolStat]
    total_runs: int
    total_cases: int
    total_calls: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "total_cases": self.total_cases,
            "total_calls": self.total_calls,
            "tools": [
                tool.to_dict(self.total_runs, self.total_cases) for tool in self.tools
            ],
            "review_candidates": [
                tool.name for tool in self.tools if tool.signal == SIGNAL_REVIEW
            ],
        }

    def candidates(self) -> list[ToolStat]:
        """Tools flagged for review, worst first."""
        flagged = [t for t in self.tools if t.signal == SIGNAL_REVIEW]
        return sorted(flagged, key=lambda t: -(t.unproductive_rate() or 0))


def aggregate(
    records: Iterable[CallRecord], outcomes: Sequence[Outcome] = ()
) -> Report:
    """Compute per-tool statistics from call records and optional outcomes."""
    stats: dict[str, ToolStat] = {}
    runs_seen: set[str] = set()
    cases_seen: set[str] = set()
    runs_by_tool: dict[str, set[str]] = defaultdict(set)
    cases_by_tool: dict[str, set[str]] = defaultdict(set)
    tools_by_case: dict[str, set[str]] = defaultdict(set)
    total_calls = 0

    for entry in records:
        total_calls += 1
        stat = stats.setdefault(entry.tool, ToolStat(name=entry.tool))
        stat.total_calls += 1
        stat.classes[entry.result_class or MISSING] += 1
        if entry.result_class == REFUSED and entry.detail:
            stat.refusal_params[entry.detail] += 1

        run_key = entry.run_id or f"{entry.case_id}:0"
        runs_seen.add(run_key)
        runs_by_tool[entry.tool].add(run_key)
        if entry.case_id:
            cases_seen.add(entry.case_id)
            cases_by_tool[entry.tool].add(entry.case_id)
            tools_by_case[entry.case_id].add(entry.tool)

    for name, stat in stats.items():
        stat.runs_using = len(runs_by_tool[name])
        stat.cases_touched = len(cases_by_tool[name])

    # Cases with an outcome but no recorded call still belong to the unused
    # arm; without them the comparison silently drops its control group.
    for outcome in outcomes:
        cases_seen.add(outcome.case_id)
        tools_by_case.setdefault(outcome.case_id, set())

    outcome_index = {o.case_id: o for o in outcomes}
    total_runs = len(runs_seen)
    total_cases = len(cases_seen)

    for stat in stats.values():
        if outcome_index:
            stat.association = _associate(stat.name, tools_by_case, outcome_index)
        _label(stat, total_runs)

    ordered = sorted(stats.values(), key=lambda s: (-s.total_calls, s.name))
    return Report(ordered, total_runs, total_cases, total_calls)


def _positive_rate(
    case_ids: Iterable[str], outcomes: dict[str, Outcome], gate: str
) -> tuple[int, int]:
    """(#pass-or-partial, n) on one gate over cases that have an outcome."""
    scored = [c for c in case_ids if c in outcomes and gate in outcomes[c].gates]
    hits = sum(1 for c in scored if outcomes[c].gates[gate] in POSITIVE_BANDS)
    return hits, len(scored)


def _associate(
    name: str, tools_by_case: dict[str, set[str]], outcomes: dict[str, Outcome]
) -> dict[str, Any]:
    """Descriptive used-versus-unused outcome rates for one tool."""
    used = [c for c in tools_by_case if name in tools_by_case[c]]
    unused = [c for c in tools_by_case if name not in tools_by_case[c]]
    gates = sorted({g for o in outcomes.values() for g in o.gates})

    result: dict[str, Any] = {}
    for gate in gates:
        used_hits, used_n = _positive_rate(used, outcomes, gate)
        unused_hits, unused_n = _positive_rate(unused, outcomes, gate)
        result[gate] = {
            "used_pass": used_hits,
            "used_n": used_n,
            "used_rate": round(used_hits / used_n, 3) if used_n else None,
            "unused_pass": unused_hits,
            "unused_n": unused_n,
            "unused_rate": round(unused_hits / unused_n, 3) if unused_n else None,
        }
    return result


def _has_positive_association(association: dict[str, Any]) -> bool | None:
    """True if the used arm beats the unused arm on any gate, with evidence.

    The unused arm must have at least ``MIN_ASSOC_N`` cases. Without that
    floor, a tool used by all but one case gets a free pass from a single
    unlucky control — which is exactly how a noisy tool survives review.
    """
    if not association:
        return None
    evidence = False
    for gate in association.values():
        used, unused = gate.get("used_rate"), gate.get("unused_rate")
        if used is None or unused is None:
            continue
        if (gate.get("unused_n") or 0) < MIN_ASSOC_N:
            continue
        evidence = True
        if used > unused:
            return True
    return False if evidence else None


def _label(stat: ToolStat, total_runs: int) -> None:
    """Assign the weight signal and a one-line reason."""
    unproductive = stat.unproductive_rate() or 0.0
    error = stat.error_rate() or 0.0
    refusal = stat.refusal_rate() or 0.0
    duplicate = stat.duplicate_rate() or 0.0
    usage_pct = (100 * stat.runs_using / total_runs) if total_runs else 0.0
    associated = _has_positive_association(stat.association)

    reasons: list[str] = []
    advisories: list[str] = []
    if error >= HIGH_ERROR:
        reasons.append(
            f"error rate {error:.0%} — the caller cannot form a valid call; "
            "shape the tool rather than prompting harder"
        )
    if unproductive >= HIGH_UNPRODUCTIVE:
        reasons.append(f"unproductive rate {unproductive:.0%}")
    if usage_pct < LOW_USAGE_PCT:
        reasons.append(f"reached in only {usage_pct:.0f}% of runs")

    # Advisory: these cost turns but each hands the caller a next step, so
    # they describe a fixable affordance, not a tool to remove.
    if refusal >= HIGH_REFUSAL:
        worst = stat.refusal_params.most_common(1)
        target = f" (mostly {worst[0][0]!r})" if worst else ""
        advisories.append(
            f"refusal rate {refusal:.0%}{target} — narrow or document that parameter"
        )
    if duplicate >= HIGH_DUPLICATE:
        advisories.append(
            f"duplicate rate {duplicate:.0%} — the result does not read as an "
            "answer; check the scope block"
        )

    noisy = unproductive >= HIGH_UNPRODUCTIVE or error >= HIGH_ERROR
    rarely_used = usage_pct < LOW_USAGE_PCT

    if not reasons:
        stat.signal = SIGNAL_STRONG if associated else SIGNAL_OK
        base = (
            "productive and associated with better outcomes"
            if associated
            else "productive"
        )
        stat.reason = "; ".join([base, *advisories])
        return

    if (noisy or rarely_used) and associated:
        stat.signal = SIGNAL_NOISY_ASSOCIATED
        stat.reason = (
            "; ".join([*reasons, *advisories])
            + " — but used runs do better; fix, do not cull"
        )
        return

    stat.signal = SIGNAL_REVIEW if (noisy or rarely_used) else SIGNAL_OK
    stat.reason = "; ".join([*reasons, *advisories])


def render_markdown(report: Report, title: str = "Tool weight") -> str:
    """Render the report as a reviewable markdown table."""
    lines = [
        f"# {title}",
        "",
        f"{report.total_calls} calls across {report.total_runs} runs "
        f"and {report.total_cases} cases.",
        "",
        "| tool | calls | runs using | avg/run | error | refused | dup | "
        "unproductive | turn cost | signal |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    def pct(value: float | None) -> str:
        return "-" if value is None else f"{value:.0%}"

    for stat in report.tools:
        usage = (
            f"{stat.runs_using} ({100 * stat.runs_using / report.total_runs:.0f}%)"
            if report.total_runs
            else str(stat.runs_using)
        )
        avg = stat.avg_calls_per_run()
        lines.append(
            f"| `{stat.name}` | {stat.total_calls} | {usage} | "
            f"{'-' if avg is None else f'{avg:.1f}'} | "
            f"{pct(stat.error_rate())} | {pct(stat.refusal_rate())} | "
            f"{pct(stat.duplicate_rate())} | {pct(stat.unproductive_rate())} | "
            f"{pct(stat.turn_cost_rate())} | {stat.signal} |"
        )

    lines += ["", "## Signals", ""]
    for stat in report.tools:
        lines.append(f"- `{stat.name}` — **{stat.signal}**: {stat.reason}")

    candidates = report.candidates()
    lines += ["", "## Review / cull candidates", ""]
    if not candidates:
        lines.append("None. Every tool is productive or positively associated.")
    else:
        lines.append(
            "A flag is a hypothesis, not a verdict. Confirm with the ablation "
            "protocol (CONTRACT.md §6): remove one tool, change nothing else, "
            "re-run, keep the removal only if outcomes hold and noise falls."
        )
        lines.append("")
        for stat in candidates:
            lines.append(f"1. `{stat.name}` — {stat.reason}")

    hotspots = [
        (stat.name, param, count)
        for stat in report.tools
        for param, count in stat.refusal_params.most_common(3)
    ]
    if hotspots:
        lines += ["", "## Refused parameters", "",
                  "Each row is an affordance the caller cannot satisfy. Narrow "
                  "the type, enumerate the vocabulary, or say where the value "
                  "comes from.", ""]
        for tool_name, param, count in sorted(hotspots, key=lambda h: -h[2]):
            lines.append(f"- `{tool_name}.{param}` refused {count}x")

    return "\n".join(lines) + "\n"


def load_outcomes(path: str | Path) -> list[Outcome]:
    """Read an outcomes JSON file: a list of ``{case_id, gates, split}``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Outcome(
            case_id=str(item["case_id"]),
            gates=dict(item.get("gates") or {}),
            split=str(item.get("split", "")),
        )
        for item in data
    ]


__all__ = [
    "HIGH_DUPLICATE",
    "HIGH_ERROR",
    "HIGH_REFUSAL",
    "HIGH_UNPRODUCTIVE",
    "LOW_USAGE_PCT",
    "MIN_ASSOC_N",
    "Outcome",
    "Report",
    "SIGNAL_NOISY_ASSOCIATED",
    "SIGNAL_OK",
    "SIGNAL_REVIEW",
    "SIGNAL_STRONG",
    "ToolStat",
    "aggregate",
    "load_outcomes",
    "render_markdown",
]
