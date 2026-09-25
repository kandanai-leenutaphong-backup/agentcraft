"""The ordered lifecycle over one RunSpec: resume from retained stage records, refuse unauthorized or under-specified
stages before any side effect, stop at the first pending, blocked or baseline-retained stage."""

from __future__ import annotations

from typing import Any

from ..core import EvidenceLedger, RefusedError, error_summary, utc_stamp
from . import stages
from .clients import Clients
from .spec import STAGES, WRITE_STAGES, RunSpec

STAGE_INPUTS = {"invoke": ("journeys",), "verify": ("journeys",), "register_evaluator": ("evaluator",),
                "evaluate": ("criteria", "items"), "optimize": ("optimization", "train", "validation"),
                "select": ("selection_rule",), "reverify": ("journeys",), "reevaluate": ("criteria", "items")}
AFTER_PROMOTION = ("reverify", "reevaluate")


def stage_record(stage: str) -> str:
    return f"pipeline-{STAGES.index(stage) + 1:02d}-{stage}.json"


def window(until: str | None = None, from_: str | None = None) -> tuple[str, ...]:
    unknown = [name for name in (until, from_) if name is not None and name not in STAGES]
    if unknown:
        raise RefusedError("stage_unknown", "unknown stage: " + ", ".join(unknown) + "; stages: " + ", ".join(STAGES))
    start = STAGES.index(from_) if from_ else 0
    end = STAGES.index(until) + 1 if until else len(STAGES)
    if start >= end:
        raise RefusedError("stage_window", "from stage must not follow until stage")
    return STAGES[start:end]


def _declared(spec: RunSpec, kind: str) -> bool:
    return spec.declared(kind) is not None or any(ref.dataset for ref in spec.inputs.get(kind, ()))


def _baseline_retained(ledger: EvidenceLedger) -> bool:
    name = stage_record("promote")
    return ledger.exists(name) and ledger.read(name).get("outcome") == "baseline_retained"


def plan(spec: RunSpec, ledger: EvidenceLedger, *, until: str | None = None, from_: str | None = None) -> dict[str, Any]:
    """What `run` would do. Refuses a resume gap, an unauthorized write stage or an undeclared input up front."""
    selected = window(until, from_)
    done = {stage for stage in STAGES if ledger.exists(stage_record(stage))}
    gap = [stage for stage in STAGES[:STAGES.index(selected[0])] if stage not in done]
    if gap:
        raise RefusedError("resume_gap", "earlier stages have no retained completion: " + ", ".join(gap))
    skipped = set(AFTER_PROMOTION) if _baseline_retained(ledger) else set()
    pending = [stage for stage in selected if stage not in done and stage not in skipped]
    unauthorized = [stage for stage in pending if stage in WRITE_STAGES and stage not in spec.authorization]
    if unauthorized:
        raise RefusedError("stage_unauthorized", "cloud-write stages not in authorization.cloud_write: "
                           + ", ".join(unauthorized))
    missing = sorted({kind for stage in pending for kind in STAGE_INPUTS.get(stage, ()) if not _declared(spec, kind)})
    if missing:
        raise RefusedError("inputs_missing", "run spec declares no input for: " + ", ".join(missing))
    return {"window": list(selected), "reuse": [stage for stage in selected if stage in done],
            "execute": pending, "not_applicable": [stage for stage in selected if stage in skipped and stage not in done]}


def _journeys(spec: RunSpec) -> Any:
    return spec.repo / spec.declared("journeys")


def _execute(stage: str, spec: RunSpec, clients: Clients, ledger: EvidenceLedger, results: dict[str, Any],
             demonstration: bool) -> Any:
    if stage == "preflight":
        return stages.preflight(spec, clients, ledger)
    if stage == "build":
        return stages.build(spec, clients, ledger)
    if stage == "deploy":
        return stages.deploy(spec, clients, ledger)
    if stage == "invoke":
        return stages.invoke_journeys(spec, clients, ledger, target="baseline")
    if stage == "verify":
        return stages.verify(spec, clients, ledger, journeys=_journeys(spec), target="baseline")
    if stage == "register_evaluator":
        return stages.register_evaluator(spec, clients, ledger)
    if stage == "evaluate":
        return stages.evaluate(spec, clients, ledger, target="baseline")
    if stage == "optimize":
        return stages.optimize(spec, clients, ledger)
    if stage == "select":
        return stages.select(spec, clients, ledger, demonstration=demonstration)
    if stage == "promote":
        return stages.promote(spec, clients, ledger, selection=results["select"])
    if stage == "reverify":
        invoked = stages.invoke_journeys(spec, clients, ledger, target="promoted", stage="reverify")
        return {"invocations": invoked,
                "verify": stages.verify(spec, clients, ledger, journeys=_journeys(spec), target="promoted")}
    return stages.evaluate(spec, clients, ledger, target="promoted", stage="reevaluate")


def run(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, *, until: str | None = None,
        from_: str | None = None, demonstration: bool = False) -> dict[str, Any]:
    """Execute `STAGES[from_..until]`. A stage with a retained `pipeline-NN-<stage>.json` is reused, never rerun.

    Status: `complete`; `pending` (evaluate/optimize unsettled at its bound: rerun resumes polling);
    `blocked` (error recorded as `pipeline-NN-<stage>-blocked-<stamp>.json`); `baseline_retained` (selection kept
    the baseline: promotion and post-promotion stages are not applicable).
    """
    planned = plan(spec, ledger, until=until, from_=from_)
    results = {stage: ledger.read(stage_record(stage)).get("result") for stage in STAGES
               if ledger.exists(stage_record(stage))}
    outcomes: list[dict[str, Any]] = []

    def finish(status: str, stopped_at: str | None = None, code: str | None = None) -> dict[str, Any]:
        return {"status": status, "stopped_at": stopped_at, "code": code, "stages": outcomes,
                "not_applicable": planned["not_applicable"]}

    for stage in planned["window"]:
        name = stage_record(stage)
        if stage in planned["not_applicable"]:
            continue
        if ledger.exists(name):
            outcomes.append({"stage": stage, "outcome": "reused", "record": name})
            if ledger.read(name).get("outcome") == "baseline_retained":
                return finish("baseline_retained", stage, "baseline_retained")
            continue
        try:
            result = _execute(stage, spec, clients, ledger, results, demonstration)
        except RefusedError as error:
            if stage == "promote" and error.code == "baseline_retained":
                ledger.retain(name, {"stage": stage, "outcome": "baseline_retained", "completed_at": utc_stamp(),
                                     "result": {"decision": "baseline", "select": results.get("select")}})
                outcomes.append({"stage": stage, "outcome": "baseline_retained", "record": name})
                return finish("baseline_retained", stage, error.code)
            return _blocked(ledger, stage, error, outcomes, finish)
        except Exception as error:
            return _blocked(ledger, stage, error, outcomes, finish)
        if isinstance(result, dict) and result.get("settled") is False:
            outcomes.append({"stage": stage, "outcome": "pending", "result": result})
            return finish("pending", stage)
        ledger.retain(name, {"stage": stage, "outcome": "complete", "completed_at": utc_stamp(), "result": result})
        results[stage] = result
        outcomes.append({"stage": stage, "outcome": "complete", "record": name})
    return finish("complete")


def _blocked(ledger: EvidenceLedger, stage: str, error: BaseException, outcomes: list[dict[str, Any]],
             finish: Any) -> dict[str, Any]:
    code = getattr(error, "code", None) or type(error).__name__
    record = f"{stage_record(stage)[:-5]}-blocked-{utc_stamp()}.json"
    ledger.retain(record, {"stage": stage, "outcome": "blocked", "code": code, "error": error_summary(error)})
    outcomes.append({"stage": stage, "outcome": "blocked", "code": code, "record": record})
    return finish("blocked", stage, code)
