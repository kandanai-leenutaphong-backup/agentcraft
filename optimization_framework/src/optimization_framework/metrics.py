"""Observed runner and native telemetry; never infer hidden model effort."""

from collections import Counter
import difflib

METRIC_VERSION = "local-reference-2"


def footprint(before: dict[str, str], after: dict[str, str]) -> dict:
    changed = added = deleted = 0
    for name in sorted(before.keys() | after.keys()):
        if before.get(name) == after.get(name):
            continue
        changed += 1
        for line in difflib.ndiff(before.get(name, "").splitlines(),
                                 after.get(name, "").splitlines()):
            added += line.startswith("+ ")
            deleted += line.startswith("- ")
    return {"files_changed": changed, "lines_added": added, "lines_deleted": deleted}


def derive(run: dict) -> dict:
    submissions = [candidate for candidate in run["candidates"] if candidate["role"] == "submission"]
    events = run["events"]
    accepted = next((event for event in events if event["kind"] == "accepted"), None)
    metrics = {
        "version": METRIC_VERSION,
        "elapsed_seconds": max((event["elapsed_seconds"] for event in events), default=0.0),
        "repair_cycles": sum(previous["status"] == "failed" and
                             previous["digest"] != following["digest"]
                             for previous, following in zip(submissions, submissions[1:])),
        "actions": sum(event["kind"] == "candidate_created" for event in events),
        "calls": sum(event["kind"] == "check_dispatched" for event in events),
        **run.get("_footprint", {"files_changed": 0, "lines_added": 0, "lines_deleted": 0}),
        "first_pass_success": bool(submissions and submissions[0]["status"] == "passed"),
        "model_requests": None,
        "telemetry_coverage": "complete trusted deterministic actions and evaluator dispatches; model internals unobserved",
        "time_to_verified_acceptance_seconds": accepted["elapsed_seconds"] if accepted else None,
        "censored": accepted is None,
        "acceptance_numerator": int(accepted is not None),
        "admitted_denominator": 1,
        "units": {"elapsed_seconds": "seconds", "time_to_verified_acceptance_seconds": "seconds",
                  "actions": "snapshot creations", "calls": "evaluator dispatches"},
        "source": "trusted-runner-events",
        "exclusions": [],
        "uncertainty": "single synthetic trial; not real coding effort or a comparative experiment",
    }
    if run.get("executor") == "copilot":
        attempts = [attempt["executor_result"] for attempt in run.get("attempts", [])
                    if attempt["role"] == "authoring"]
        starts = [attempt.get("coverage", {}).get("model_requests") for attempt in attempts]
        observed = (sum(item["observed_starts"] for item in starts)
                    if starts and all(isinstance(item, dict) and "observed_starts" in item for item in starts)
                    else None)
        if any(attempt.get("coverage", {}).get("jsonl") == "unobserved" for attempt in attempts):
            observed = None
        metrics.update(
            model_requests=observed,
            native_attempts=sum(event["kind"] == "native_dispatched" for event in events),
            native_settled_attempts=len(attempts),
            repair_cycles=max(0, len(attempts) - 1),
            coding_latency_seconds=sum(attempt["elapsed_seconds"] for attempt in attempts) if attempts else None,
            native_event_kinds=dict(Counter(event["kind"] for attempt in attempts for event in attempt["events"])),
            telemetry_coverage="native observed events and CLI usage retained per authoring attempt; hidden requests unknown",
            uncertainty="single native config-only trial; trusted same-user evaluation, not independent or comparative A/B",
        )
        metrics["units"]["coding_latency_seconds"] = "seconds; sum of executor monotonic intervals including settlement"
        metrics["units"]["model_requests"] = "observed model.call_start events; not billing or hidden requests"
    return metrics