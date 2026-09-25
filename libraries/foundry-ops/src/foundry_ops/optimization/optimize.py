"""Native agent optimization jobs over a caller-owned `AIProjectClient` (`project.beta.agents`).

Requests are wire-shaped mappings (`items`, not the SDK's snake-case `dataset_items`), which
`begin_create_optimization_job` accepts. Poll with `get_optimization_job`; the `Operation-Location` it
returns is an internal path that 404s publicly. Candidate ids are not generations and `avg_score` is the
service's composite, not an independent metric: `list_candidates` keeps generation/parent null.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import json
import math
import re
import time
from typing import Any
import uuid

from ..core.bounds import PollResult, poll_until
from ..core.errors import BoundExceededError, OutcomeUnknownError, RefusedError, VerificationError
from ..core.identifiers import safe_identifier, validate_version_label
from ..core.records import EvidenceLedger, to_plain

EventSink = Callable[[dict[str, Any]], None]
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "completed", "failed", "canceled", "cancelled"})
SUCCESS_JOB_STATUSES = frozenset({"succeeded", "completed"})
ITEM_FIELDS = frozenset({"query", "ground_truth", "desired_num_turns", "criteria"})
CONFIG_FIELDS = frozenset({"name", "instructions", "model", "temperature", "skills", "tools"})
CONFIG_API_VERSION = "2025-11-15-preview"
_SERVICE_ID = re.compile(r"[A-Za-z0-9_-]+")
SCORE_NOTE = "avg_score is the native composite; not an independent metric"
LINEAGE_NOTE = "native candidate ids and order are not generations; generation/parent_id stay null"


def inline_dataset(items: Iterable[Mapping[str, Any]], *, max_items: int = 1000) -> dict[str, Any]:
    """Wire JSON `{"type": "inline", "items": [...]}`; rows need a non-empty `query`."""
    if isinstance(items, Mapping):
        raise RefusedError("dataset_shape", "pass rows, not an envelope; `dataset_items` is not wire JSON")
    rows = [dict(row) for row in items]
    if not rows or len(rows) > max_items:
        raise RefusedError("dataset_shape", f"inline dataset needs 1-{max_items} rows")
    for row in rows:
        if set(row) - ITEM_FIELDS or not isinstance(row.get("query"), str) or not row["query"]:
            raise RefusedError("dataset_row", "row fields must be query/ground_truth/desired_num_turns/criteria")
    return {"type": "inline", "items": rows}


def reference_dataset(ref: Mapping[str, Any]) -> dict[str, Any]:
    """Wire JSON `{"type": "reference", "name", "version"}` from a registered dataset reference; version is
    required because an omitted version resolves to the mutable latest. Same shape as
    `foundry_ops.data.optimization_dataset`."""
    if not isinstance(ref, Mapping) or ref.get("type", "reference") != "reference":
        raise RefusedError("dataset_ref", "dataset reference must be a mapping of name and version")
    return {"type": "reference", "name": safe_identifier(ref.get("name"), "dataset name"),
            "version": validate_version_label(ref.get("version"), 50, what="dataset version", code="dataset_version")}


def _split(kind: str, items: Iterable[Mapping[str, Any]] | None, ref: Mapping[str, Any] | None) -> dict[str, Any]:
    if (items is None) == (ref is None):
        raise RefusedError("dataset_source", f"exactly one of {kind}_items or {kind}_dataset required")
    return inline_dataset(items) if items is not None else reference_dataset(ref)


def optimization_job(agent_name: str, agent_version: str, *, train_items: Iterable[Mapping[str, Any]] | None = None,
                     validation_items: Iterable[Mapping[str, Any]] | None = None,
                     evaluators: Iterable[Mapping[str, str]], optimization_model: str, max_candidates: int,
                     eval_model: str | None = None, max_stalls: int | None = None,
                     optimization_config: Mapping[str, Any] | None = None,
                     extra_options: Mapping[str, Any] | None = None, train_dataset: Mapping[str, Any] | None = None,
                     validation_dataset: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Wire-shaped `AgentOptimizationJob`; each split is inline rows or a registered dataset reference.
    `evaluation_level` is refused: the service rejects `turn` with 400."""
    if type(max_candidates) is not int or max_candidates < 1:
        raise RefusedError("max_candidates", "max_candidates must be a positive integer")
    refs = [{"name": ref["name"], "version": str(ref["version"])} for ref in evaluators]
    if not refs:
        raise RefusedError("evaluators", "at least one registered evaluator reference required")
    options: dict[str, Any] = {**dict(extra_options or {}), "max_candidates": max_candidates,
                               "optimization_model": optimization_model}
    if "evaluation_level" in options:
        raise RefusedError("evaluation_level", "omit evaluation_level; service rejects the advertised value")
    for field, value in (("eval_model", eval_model), ("max_stalls", max_stalls),
                         ("optimization_config", dict(optimization_config) if optimization_config else None)):
        if value is not None:
            options[field] = value
    return {"inputs": {"agent": {"agent_name": safe_identifier(agent_name, "agent name"), "agent_version": str(agent_version)},
                       "train_dataset": _split("train", train_items, train_dataset),
                       "validation_dataset": _split("validation", validation_items, validation_dataset),
                       "evaluators": refs, "options": options}}


def _job_id(details: Any) -> Any:
    return details.get("job_id") if isinstance(details, Mapping) else getattr(details, "job_id", None)


def submit_optimization(project: Any, ledger: EvidenceLedger, *, key: str, job: Mapping[str, Any],
                        operation_id: str | None = None) -> dict[str, Any]:
    """Submit once without SDK polling. Records `optimize-<key>-intent.json` (with operation id) and
    `-identity.json`; a rerun resumes from identity, an intent without it is unresolved."""
    identity_record = f"optimize-{key}-identity.json"
    agents = project.beta.agents
    if ledger.exists(identity_record):
        identity = ledger.read(identity_record)
    else:
        operation_id = operation_id or str(uuid.uuid4())
        ledger.intent(f"optimize-{key}", dict(job), context={"operation_id": operation_id})
        poller = agents.begin_create_optimization_job(job=dict(job), operation_id=operation_id, polling=False)
        job_id = _job_id(getattr(poller, "details", None))
        if not isinstance(job_id, str) or not _SERVICE_ID.fullmatch(job_id):
            raise OutcomeUnknownError("job_identity_unknown",
                                      "optimization accepted without job id; reconcile by operation id, never resubmit")
        identity = {"job_id": job_id, "operation_id": operation_id}
        ledger.retain(identity_record, identity)
    return {**identity, "job": to_plain(agents.get_optimization_job(identity["job_id"]))}


def wait_optimization(project: Any, *, job_id: str, seconds: float = 3600.0, interval: float = 20.0,
                      attempts: int | None = None, sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic,
                      on_event: EventSink | None = None) -> PollResult[dict[str, Any]]:
    """Bounded `get_optimization_job` polling to a terminal status; unsettled is returned, nothing cancelled."""
    safe_identifier(job_id, "job id")
    attempt = 0

    def read() -> dict[str, Any]:
        nonlocal attempt
        job = to_plain(project.beta.agents.get_optimization_job(job_id))
        if job.get("id") not in (None, job_id):
            raise VerificationError("foreign_job", "optimization job identity mismatch")
        if on_event is not None:
            on_event({"operation": "optimization_poll", "attempt": attempt, "status": job.get("status"),
                      "progress": job.get("progress"), "error": job.get("error")})
        attempt += 1
        return job

    return poll_until(read, lambda job: job.get("status") in TERMINAL_JOB_STATUSES, interval=interval,
                      attempts=attempts, seconds=seconds, sleep=sleep, clock=clock)


def list_candidates(job: Any, *, require_success: bool = True, require_generated: bool = True) -> dict[str, Any]:
    """Plain candidate records from `job.result.candidates` with service ids and observation order.

    Refuses duplicate/unsafe ids, missing eval identity, nonfinite metrics, a missing or repeated
    baseline, and (by default) a non-successful or baseline-only job.
    """
    job = to_plain(job)
    if require_success and (job.get("status") not in SUCCESS_JOB_STATUSES or job.get("error")):
        raise VerificationError("job_not_succeeded", "optimization job not successfully complete; retain job")
    result = job.get("result") or {}
    native = result.get("candidates")
    if not isinstance(native, list) or not native:
        raise VerificationError("candidates_missing", "optimization job returned no candidates")
    baseline = result.get("baseline")
    candidates, seen = [], set()
    for index, candidate in enumerate(native):
        identifier = candidate.get("candidate_id") or candidate.get("id")
        if not isinstance(identifier, str) or not _SERVICE_ID.fullmatch(identifier) or identifier in seen:
            raise VerificationError("candidate_identity", "duplicate, missing or unsafe candidate id")
        seen.add(identifier)
        if any(not isinstance(candidate.get(key), str) or not candidate[key] for key in ("eval_id", "eval_run_id")):
            raise VerificationError("candidate_evaluation", "candidate evaluation identity missing")
        for key in ("avg_score", "avg_tokens"):
            if type(candidate.get(key)) not in (int, float) or not math.isfinite(candidate[key]):
                raise VerificationError("candidate_metric", "candidate metric missing or nonfinite")
        candidates.append({"candidate_id": identifier, "name": candidate.get("name"),
                           "observation_index": index, "is_baseline": identifier == baseline,
                           "agent_version": candidate.get("agent_version"), "avg_score": candidate["avg_score"],
                           "avg_tokens": candidate["avg_tokens"], "eval_id": candidate["eval_id"],
                           "eval_run_id": candidate["eval_run_id"], "mutations": candidate.get("mutations"),
                           "generation": None, "parent_id": None, "native": candidate})
    if sum(item["is_baseline"] for item in candidates) != 1:
        raise VerificationError("baseline_membership", "exactly one baseline candidate required")
    generated = len(candidates) - 1
    if require_generated and not generated:
        raise VerificationError("baseline_only", "job produced no generated candidate")
    return {"job_id": job.get("id"), "status": job.get("status"), "baseline": baseline, "best": result.get("best"),
            "generated": generated, "candidates": candidates, "notes": [SCORE_NOTE, LINEAGE_NOTE]}


def resolve_candidate_config(project: Any, *, endpoint: str, job_id: str, candidate_id: str,
                             api_version: str = CONFIG_API_VERSION, allowed_fields: frozenset[str] = CONFIG_FIELDS,
                             max_bytes: int = 1_000_000, connection_timeout: float = 15, read_timeout: float = 30,
                             request_factory: Callable[[str, str], Any] | None = None,
                             validate: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
    """One bounded authenticated GET `{endpoint}/agent_optimization_jobs/{job}/candidates/{id}/config`.

    Uses `project.send_request`; `request_factory` defaults to `azure.core.rest.HttpRequest` (lazy).
    `validate` may be `azure.ai.agentserver.optimization.CandidateConfig.from_dict`.
    """
    safe_identifier(job_id, "job id")
    safe_identifier(candidate_id, "candidate id")
    if request_factory is None:
        from azure.core.rest import HttpRequest as request_factory  # type: ignore[no-redef]
    url = (endpoint.rstrip("/") + "/agent_optimization_jobs/" + job_id + "/candidates/" + candidate_id
           + "/config?api-version=" + api_version)
    response = project.send_request(request_factory("GET", url), connection_timeout=connection_timeout,
                                    read_timeout=read_timeout)
    if response.status_code != 200:
        raise VerificationError("candidate_config_status", f"candidate config HTTP {response.status_code}")
    payload = response.read()
    if len(payload) > max_bytes:
        raise BoundExceededError("candidate_config_size", "candidate config exceeds bound")
    config = json.loads(payload)
    if not isinstance(config, dict):
        raise VerificationError("candidate_config_shape", "candidate config must be an object")
    unknown = sorted(set(config) - allowed_fields)
    if unknown:
        raise VerificationError("candidate_config_field", "unapproved candidate config fields: " + ", ".join(unknown))
    if validate is not None:
        validate(config)
    return config


def candidate_configs(project: Any, listing: Mapping[str, Any], *, endpoint: str,
                      candidate_ids: Sequence[str] | None = None, **options: Any) -> dict[str, dict[str, Any]]:
    """`resolve_candidate_config` for each listed (or selected) candidate, keyed by candidate id."""
    job_id = listing["job_id"]
    wanted = candidate_ids or [item["candidate_id"] for item in listing["candidates"]]
    known = {item["candidate_id"] for item in listing["candidates"]}
    if set(wanted) - known:
        raise RefusedError("candidate_foreign", "candidate id not in this job's listing")
    return {candidate_id: resolve_candidate_config(project, endpoint=endpoint, job_id=job_id,
                                                   candidate_id=candidate_id, **options)
            for candidate_id in wanted}
