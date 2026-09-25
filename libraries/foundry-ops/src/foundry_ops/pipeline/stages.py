"""Lifecycle stages over one RunSpec. Each takes `(spec, clients, ledger, **options)`, refuses before side effects,
records intent before every write and reuses retained results on rerun (a settled write is never replayed)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
from typing import Any

from .. import evaluation, optimization
from ..build import resolve_image, submit_build, wait_build
from ..core import EvidenceLedger, RefusedError, VerificationError, safe_identifier, sha256_hex, to_plain
from ..evaluation import (DEFAULT_INPUT_TEMPLATE, code_evaluator_definition, collect_rows, infer_item_schema,
                          register_code_evaluator, run_code_evaluator_canary)
from ..hosting import (DEFINITION_KEYS, FAILED_STATUSES, HostedTeardown, agent_responses_url, anonymous_probe,
                       check_active_version, check_identity, deploy_version, hosted_definition, invoke as hosted_invoke,
                       is_not_found, list_sessions, list_versions, output_text, read_stored_response, require_refusal,
                       session_log_excerpt, tool_calls)
from ..optimization import ITEM_FIELDS, list_candidates, optimization_job, resolve_candidate_config, wait_optimization
from .clients import Clients
from .inputs import (bounded_seconds, canonical, input_json, load_journeys, load_rows, parse_json, read_input,
                     referenced_file, register_rows)
from .source import release_label, source_manifest, stage_context
from .spec import GUID, RunSpec

PROJECT_API_VERSION = "2025-06-01"
EVAL_WAIT_CEILING = 1800
OPTIMIZE_WAIT_CEILING = 21600
MAX_INVOKE_CHARS = 8192
OVERLAY_FIELDS = frozenset({"instructions", "model"})
SELECTION_RULE = {"eligibility": "strictly_above_baseline", "tie_break": "earliest_observation",
                  "fallback": "baseline"}
SELECTION_SCORES = frozenset({"avg_score", "criterion_mean"})
SCORE_KIND = "native avg_score (service composite; not an independent metric)"
OPTIMIZATION_FIELDS = frozenset({"evaluators", "optimization_model", "max_candidates", "eval_model", "max_stalls",
                                 "optimization_config", "item_fields", "wait_seconds"})
CRITERIA_FIELDS = frozenset({"testing_criteria", "name", "input_template", "item_fields", "item_schema",
                             "wait_seconds"})
TARGETS = ("current", "baseline", "promoted")


# --- identity --------------------------------------------------------------------------------

def current_label(spec: RunSpec, clients: Clients) -> tuple[str, dict[str, Any]]:
    manifest = source_manifest(clients.layout.build_inputs(spec.package))
    return release_label(manifest), manifest


def current_deployment(spec: RunSpec, clients: Clients, ledger: EvidenceLedger,
                       target: str = "current") -> tuple[str, dict[str, Any]]:
    """The series' active deployment of the current source: `baseline` (plain image), `promoted` (optimization
    overlay) or `current` (promoted when present, else baseline)."""
    if target not in TARGETS:
        raise RefusedError("target", "target must be current, baseline or promoted")
    label, _ = current_label(spec, clients)
    names = [name for name in ledger.list("deploy-*-active.json") if name.startswith(f"deploy-{label}-")]
    promoted = [name for name in names if name.startswith(f"deploy-{label}-opt-")]
    baseline = [name for name in names if name not in promoted]
    chosen = {"baseline": baseline, "promoted": promoted, "current": promoted or baseline}[target]
    if not chosen:
        raise RefusedError("stage_missing", f"no {target} deployment for the current source; run deploy or promote")
    if len(chosen) > 1:
        raise RefusedError("deployment_ambiguous", "more than one deployment in this series")
    return label, ledger.read(chosen[0])


def expected_identity(spec: RunSpec, deployed: dict[str, Any]) -> dict[str, str]:
    metadata = deployed["metadata"]
    identity = {key: metadata[key] for key in ("source_sha256", "config_sha256", "package_sha256")}
    if "optimization_config_sha256" in metadata:
        identity["optimization_config_sha256"] = metadata["optimization_config_sha256"]
    return {**identity, "agent_name": spec.agent, "agent_version": deployed["version"]}


def build_record(ledger: EvidenceLedger, label: str) -> dict[str, Any]:
    """This series' build of the current source, else a sibling series' build of the identical source label."""
    name = f"build-{label}-image.json"
    if ledger.exists(name):
        return ledger.read(name)
    for sibling in sorted(ledger.directory.parent.iterdir()):
        record = sibling / name
        if sibling.is_dir() and not sibling.is_symlink() and record.is_file() and not record.is_symlink():
            return {**json.loads(record.read_bytes()), "build_series": sibling.name}
    raise RefusedError("stage_missing", "no build record for the current source; run build")


# --- preflight / build -----------------------------------------------------------------------

def preflight(spec: RunSpec, clients: Clients, ledger: EvidenceLedger) -> dict[str, Any]:
    """Read-only: package, account, project, registry, pull role, model, agent ownership. Gaps refuse."""
    config = clients.layout.package_config(spec.package)
    targets, subscription, az = spec.targets, spec.targets["subscription_id"], clients.az
    runtime = spec.models["runtime"]
    gaps: list[str] = []
    account = az(["account", "show", "--query", "{subscriptionId:id,tenantId:tenantId}"])
    if (account or {}).get("subscriptionId", "").lower() != subscription.lower() \
            or (account or {}).get("tenantId", "").lower() != targets["tenant_id"].lower():
        raise RefusedError("account_mismatch", "active az account differs from targets; run az account set explicitly")
    found = az(["resource", "show", "--ids", targets["project_resource_id"], "--api-version", PROJECT_API_VERSION,
                "--query", "{state:properties.provisioningState,endpoints:properties.endpoints,"
                           "principal:identity.principalId}"]) or {}
    if found.get("state") != "Succeeded" or targets["project_endpoint"] not in (found.get("endpoints") or {}).values():
        gaps.append("project state or endpoint mismatch")
    registry = az(["acr", "show", "--subscription", subscription, "--name", targets["acr_name"],
                   "--query", "{id:id,loginServer:loginServer}"]) or {}
    if registry.get("loginServer") != targets["acr_login_server"]:
        gaps.append("registry login server mismatch")
    principal = found.get("principal")
    if not isinstance(principal, str) or not re.fullmatch(GUID, principal):
        gaps.append("project managed identity missing")
    elif registry.get("id"):
        roles = az(["role", "assignment", "list", "--subscription", subscription, "--scope", registry["id"],
                    "--include-inherited", "--query",
                    f"[?principalId=='{principal}'].{{role:roleDefinitionName,condition:condition}}"]) or []
        if not any(role.get("role") == "AcrPull" and not role.get("condition") for role in roles):
            gaps.append("project identity lacks unconditional AcrPull on the registry (grant is out of scope here)")
    model = az(["cognitiveservices", "account", "deployment", "list", "--subscription", subscription,
                "--resource-group", targets["model_resource_group"], "--name", targets["model_account"], "--query",
                f"[?name=='{runtime}'].{{name:name,state:properties.provisioningState}}"]) or []
    if len(model) != 1 or model[0].get("state") != "Succeeded":
        gaps.append("model deployment not found or not ready")
    if config["model"] != runtime:
        gaps.append("package configuration.yaml model differs from the runtime model deployment")
    try:
        existing = to_plain(clients.project.agents.get(agent_name=spec.agent))
    except Exception as error:
        if not is_not_found(error):
            raise
        existing = None
    latest = str((((existing or {}).get("versions") or {}).get("latest") or {}).get("version")) if existing else None
    previous = spec.previous_version
    if existing is not None and previous is None and not ledger.list("deploy-*-active.json"):
        gaps.append("agent exists but is not owned by this series; set previous_version in the run spec")
    if existing is None and previous is not None:
        gaps.append("previous_version set but agent is absent")
    result = {"agent_exists": existing is not None, "latest_version": latest, "gaps": gaps,
              "package": {"dir": spec.package_dir, **config}}
    if gaps:
        raise RefusedError("preflight_gaps", "preflight blocked: " + "; ".join(gaps))
    return result


def build(spec: RunSpec, clients: Clients, ledger: EvidenceLedger) -> dict[str, Any]:
    """Layout self-check and preflight, then one server-side ACR build of the exact context; digest-pinned image."""
    spec.require("build")
    tests = clients.layout.self_check()
    preflight(spec, clients, ledger)
    inputs = clients.layout.build_inputs(spec.package)
    manifest = source_manifest(inputs)
    label = release_label(manifest)
    record = f"build-{label}-image.json"
    if ledger.exists(record):
        return ledger.read(record)
    targets, repository = spec.targets, spec.targets["image_repository"]
    subscription, registry = targets["subscription_id"], targets["acr_name"]
    with tempfile.TemporaryDirectory(prefix="foundry-hosted-agent-") as directory:
        stage_context(inputs, manifest, Path(directory))
        run_id = submit_build(clients.az, ledger, key=label, subscription=subscription, registry=registry,
                              image=f"{repository}:{label}", context_dir=directory)
    run = wait_build(clients.az, subscription=subscription, registry=registry, run_id=run_id, sleep=clients.sleep,
                     clock=clients.clock)
    image = resolve_image(clients.az, run, subscription=subscription, registry=registry,
                          registry_host=targets["acr_login_server"], repository=repository, tag=label)
    result = {"image": image, "release": label, "run_id": run_id, "source": manifest, "tests": tests,
              "package_dir": spec.package_dir, "package_sha256": manifest["package_sha256"]}
    ledger.retain(record, result)
    return result


# --- deploy / promote ------------------------------------------------------------------------

def _selection_overlay(record: Any) -> tuple[dict[str, Any], dict[str, str]]:
    if isinstance(record, dict) and record.get("action") == "select":
        if record.get("status") != "complete":
            raise RefusedError("candidate_record", "select receipt is not complete")
        record = record.get("result")
    if not isinstance(record, dict) or record.get("decision") not in ("baseline", "selected", "demonstration"):
        raise RefusedError("candidate_record", "not a select result")
    if record["decision"] == "baseline":
        raise RefusedError("baseline_retained", "selection retained the baseline; nothing to promote")
    if record["decision"] == "demonstration" and record.get("label") != "demonstration":
        raise RefusedError("candidate_record", "demonstration promotion must carry label demonstration")
    candidate = record.get("config")
    if not isinstance(candidate, dict) or sha256_hex(canonical(candidate)) != record.get("config_sha256"):
        raise RefusedError("candidate_record", "candidate config differs from its recorded sha256")
    return {"instructions": candidate.get("instructions")}, {
        "promotion": record["decision"], "optimization_candidate_id": safe_identifier(
            record.get("candidate_id"), "candidate id"), "candidate_config_sha256": record["config_sha256"]}


def optimization_overlay(spec: RunSpec, clients: Clients, *, config_path: Any = None, candidate_record: Any = None,
                         selection: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Instruction-only native override as definition env `OPTIMIZATION_CONFIG` (the runtime applies it).

    From a pinned config file `{instructions, model?}`, a pinned select record, or an in-series select result
    naming a selected or labelled demonstration candidate. A baseline decision refuses: nothing is promoted.
    """
    if sum(item is not None for item in (config_path, candidate_record, selection)) > 1:
        raise RefusedError("overlay_choice", "pass --optimization-config or --instructions-from-candidate, not both")
    if config_path is not None:
        config, metadata = input_json(spec, "optimization_config", config_path), {"promotion": "configured"}
    elif candidate_record is not None or selection is not None:
        config, metadata = _selection_overlay(
            selection if selection is not None else input_json(spec, "candidate_record", candidate_record))
    else:
        return None
    if not isinstance(config, dict) or set(config) - OVERLAY_FIELDS:
        raise RefusedError("overlay_fields", "optimization overlay may carry only instructions and model")
    instructions = config.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise RefusedError("overlay_instructions", "non-empty instructions required")
    model = clients.layout.package_config(spec.package)["model"]
    if config.get("model") not in (None, model):
        raise RefusedError("overlay_model", "overlay model differs from the package model")
    # The native loader strips instructions; strip here so the recorded digest is the served one.
    applied = {"instructions": instructions.strip(), "model": model}
    digest = sha256_hex(json.dumps(applied, sort_keys=True).encode())
    return {"env": json.dumps(applied, sort_keys=True), "digest": digest,
            "metadata": {"optimization_config_sha256": digest, **metadata}}


def _deploy(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, overlay_options: dict[str, Any], *,
            previous_version: str | None, siblings: tuple[str, ...] = ()) -> dict[str, Any]:
    label, manifest = current_label(spec, clients)
    built = build_record(ledger, label)
    metadata = {"source_sha256": manifest["sha256"], "config_sha256": manifest["config_sha256"],
                "package_sha256": manifest["package_sha256"], "release": label}
    definition = hosted_definition(built["image"])
    overlay = optimization_overlay(spec, clients, **overlay_options)
    key, previous_image = label, spec.previous_image
    if overlay:
        definition["environment_variables"] = {"OPTIMIZATION_CONFIG": overlay["env"]}
        metadata.update(overlay["metadata"])
        key, previous_image = f"{label}-opt-{overlay['digest'][:16]}", None
    foreign = [name for name in ledger.list("deploy-*-intent.json")
               if name != f"deploy-{key}-intent.json" and name not in siblings]
    if foreign:
        raise RefusedError("series_deployed", "this series already deployed another release; use a new series")
    result = deploy_version(clients.project, ledger, key=key, agent_name=spec.agent, definition=definition,
                            metadata=metadata, previous_version=previous_version, previous_image=previous_image,
                            seconds=spec.bounds["deploy_wait_seconds"], sleep=clients.sleep, clock=clients.clock)
    if overlay:
        actual = to_plain(clients.project.agents.get_version(agent_name=spec.agent, agent_version=result["version"]))
        served = ((actual.get("definition") or {}).get("environment_variables") or {}).get("OPTIMIZATION_CONFIG")
        if served != overlay["env"]:
            raise VerificationError("optimization_readback", "version OPTIMIZATION_CONFIG differs from the overlay")
    return result


def deploy(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, *, optimization_config: Any = None,
           candidate_record: Any = None) -> dict[str, Any]:
    """New immutable hosted version of the built image; waits active and reads back exact identity.

    One deployment per series. An overlay (pinned config or select record, typically in a second series with
    `previous_version`) sets `OPTIMIZATION_CONFIG` on the same image; the overlay digest replaces image distinctness.
    """
    spec.require("deploy")
    return _deploy(spec, clients, ledger, {"config_path": optimization_config, "candidate_record": candidate_record},
                   previous_version=spec.previous_version)


def selection_record(ledger: EvidenceLedger) -> dict[str, Any]:
    names = ledger.list("select-*.json")
    if len(names) != 1:
        raise RefusedError("selection_missing", "exactly one select record required in this series; "
                                                "otherwise pass the select result explicitly")
    return ledger.read(names[0])


def promote(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, *, selection: dict[str, Any] | None = None,
            candidate_record: Any = None, optimization_config: Any = None) -> dict[str, Any]:
    """Same-series promotion: the selected candidate as an overlay version on the baseline image.

    `previous_version` is the series' own baseline deployment; that deploy intent is the only allowed sibling.
    Default overlay source is the series' single select record. A baseline decision refuses `baseline_retained`.
    """
    spec.require("promote")
    if selection is None and candidate_record is None and optimization_config is None:
        selection = selection_record(ledger)
    label, baseline = current_deployment(spec, clients, ledger, target="baseline")
    return _deploy(spec, clients, ledger, {"config_path": optimization_config, "candidate_record": candidate_record,
                                           "selection": selection},
                   previous_version=baseline["version"], siblings=(f"deploy-{label}-intent.json",))


# --- invoke / verify -------------------------------------------------------------------------

def invocation_key(label: str, version: str, stream: bool, text: str) -> str:
    return f"{label}-v{version}-{'s' if stream else 'n'}-{sha256_hex(text.encode())[:16]}"


def invoke(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, text: str, *, stream: bool = False,
           target: str = "current", stage: str = "invoke") -> dict[str, Any]:
    """One stored, version-pinned Responses call per (release, version, mode, input); a rerun never re-infers."""
    spec.require(stage)
    label, deployed = current_deployment(spec, clients, ledger, target)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_INVOKE_CHARS:
        raise RefusedError("invoke_input", "bounded non-empty input required")
    reply = hosted_invoke(clients.openai, ledger, key=invocation_key(label, deployed["version"], stream, text),
                          agent_name=spec.agent, version=deployed["version"], input=text, stream=stream)
    if reply["response"].get("status") != "completed":
        raise VerificationError("invoke_incomplete", "response not completed; reconcile by response id, never replay")
    result = {"response_id": reply["response"]["id"], "version": deployed["version"], "stream": stream,
              "output_text": reply["output_text"], "seconds": reply["seconds"]}
    if stream:
        result.update(events=len(reply["stream"]["events"]), first_delta_seconds=reply["stream"]["first_delta_seconds"])
    return result


def invoke_journeys(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, path: Any = None, *,
                    target: str = "current", stage: str = "invoke") -> list[dict[str, Any]]:
    return [{"id": journey["id"], **invoke(spec, clients, ledger, journey["input"], stream=journey["stream"],
                                           target=target, stage=stage)}
            for journey in load_journeys(spec, path)]


def _check_tool_records(records: list[dict[str, Any]]) -> None:
    for record in records:
        if not {"output", "metadata"} <= set(record["sources"]) or any(
                record[key] is None for key in ("name", "status", "started_at", "ended_at", "duration_ms")):
            raise VerificationError("tool_record_incomplete", "tool call lacks native item or timing/status record")


def _check_stream(invoked: dict[str, Any], stored: dict[str, Any], records: list[dict[str, Any]]) -> None:
    stream = invoked["stream"]
    if not stream["types"] or stream["types"][0] != "response.created" or stream["types"][-1] != "response.completed":
        raise VerificationError("stream_order", "stream must open with response.created and end response.completed")
    streamed = tool_calls(invoked)
    if [record["call_id"] for record in streamed] != [record["call_id"] for record in records] \
            or any("stream" not in record["sources"] for record in streamed):
        raise VerificationError("stream_tool_drift", "streamed tool call ids differ from the stored response")
    if stream["text"] != output_text(stored):
        raise VerificationError("stream_text_drift", "streamed text deltas differ from the stored output text")


def _present(value: Any) -> Any:
    """Drop null-valued keys recursively: SDK `model_dump` emits unset optional fields the raw wire JSON omits."""
    if isinstance(value, dict):
        return {key: _present(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_present(item) for item in value]
    return value


def verify(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, *, journeys: Any = None,
           target: str = "current") -> dict[str, Any]:
    """Active exact version, anonymous refusal, each stored response read back with identity and tool records.

    With a journeys file, each journey's invocation must exist and its tool records (name, ok/error, error_code, in
    order) must equal the expectation; streamed journeys also match stream order, call ids and text.
    """
    label, deployed = current_deployment(spec, clients, ledger, target)
    definition = deployed["definition"]
    keys = DEFINITION_KEYS + (("environment_variables",) if "environment_variables" in definition else ())
    actual = to_plain(clients.project.agents.get_version(agent_name=spec.agent, agent_version=deployed["version"]))
    readback = check_active_version(actual, version=deployed["version"],
                                    image=definition["container_configuration"]["image"],
                                    metadata=deployed["metadata"], definition=definition, definition_keys=keys)
    status = require_refusal(anonymous_probe(agent_responses_url(spec.targets["project_endpoint"], spec.agent),
                                             http_client=clients.http))
    version = deployed["version"]
    if journeys is not None:
        planned = [(journey, f"invoke-{invocation_key(label, version, journey['stream'], journey['input'])}-result.json")
                   for journey in load_journeys(spec, journeys)]
        missing = [journey["id"] for journey, name in planned if not ledger.exists(name)]
        if missing:
            raise RefusedError("journey_not_invoked", "journeys without invocation: " + ", ".join(missing))
    else:
        planned = [(None, name) for name in ledger.list(f"invoke-{label}-v{version}-*-result.json")]
    if not planned:
        raise RefusedError("stage_missing", "no invocation to verify; run invoke first")
    identity = expected_identity(spec, deployed)
    bearer = clients.token()
    checked = []
    for journey, name in planned:
        invoked_record = ledger.read(name)
        invoked = invoked_record["response"]
        stored = read_stored_response(clients.openai, invoked["id"], bearer_token=bearer, http_client=clients.http)
        if stored is None:
            raise VerificationError("stored_response_missing", "stored response absent")
        if stored.get("status") != "completed" or _present(stored.get("output")) != _present(invoked.get("output")):
            raise VerificationError("stored_response_drift", "stored response status or output differs")
        check_identity(stored.get("metadata"), identity, what="stored response metadata")
        expected = [tool["name"] for tool in (journey or {}).get("expected_tools", [])]
        records = tool_calls(stored, metadata_prefix="tool_call.", expected=expected)
        _check_tool_records(records)
        entry: dict[str, Any] = {"response_id": invoked["id"], "tool_calls": records}
        if journey is not None:
            observed = [{"name": record["name"], "error_code": record["error_code"],
                         "status": "error" if record["status"] in FAILED_STATUSES else "ok"} for record in records]
            wanted = [{"name": tool["name"], "status": tool["status"], "error_code": tool.get("error_code")}
                      for tool in journey["expected_tools"]]
            if observed != wanted:
                raise VerificationError("tool_call_mismatch", f"journey {journey['id']}: tool records differ from expectation")
            if journey["stream"]:
                _check_stream(invoked_record, stored, records)
            entry["id"] = journey["id"]
            if "expected_answer" in journey:
                entry["answer_match"] = output_text(stored).strip() == str(journey["expected_answer"]).strip()
        checked.append(entry)
    return {"version": readback, "anonymous_status": status, "identity": identity,
            "stored_responses": [entry["response_id"] for entry in checked], "invocations": checked}


# --- evaluate / evaluator --------------------------------------------------------------------

def evaluate(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, criteria: Any = None, items: Any = None, *,
             previous: bool = False, target: str = "current", stage: str = "evaluate") -> dict[str, Any]:
    """Native eval of the target version: `run_agent_eval` with caller criteria `{testing_criteria, name?,
    input_template?, item_fields?, item_schema?, wait_seconds?}` over caller rows (JSON list/JSONL) or, with
    `data: dataset`, a registered dataset (pinned rows registered once, or a spec ref read back by sha256).

    `previous` targets the spec's reviewed `previous_version` instead (baseline side of a comparison)."""
    spec.require(stage)
    value = input_json(spec, "criteria", criteria)
    value = {"testing_criteria": value} if isinstance(value, list) else value
    if not isinstance(value, dict) or not value.get("testing_criteria") or set(value) - CRITERIA_FIELDS:
        raise RefusedError("criteria_missing", "criteria file needs non-empty testing_criteria")
    rows, ref = load_rows(spec, "items", items, fields=value.get("item_fields"))
    if previous and spec.previous_version is None:
        raise RefusedError("previous_missing", "--previous-version needs previous_version in the run manifest")
    label, deployed = current_deployment(spec, clients, ledger, target)
    version = spec.previous_version if previous else deployed["version"]
    seconds = bounded_seconds(value.get("wait_seconds", spec.bounds["eval_wait_seconds"]), EVAL_WAIT_CEILING)
    content = rows if rows is not None else ref["sha256"]
    key = f"{label}-v{version}-{sha256_hex(canonical([value, content]))[:16]}" + ("-ds" if spec.data == "dataset" else "")
    dataset = register_rows(spec, clients.project, ledger, "items", rows, ref)
    if dataset is None:
        source: dict[str, Any] = {"items": rows, "item_schema": value.get("item_schema")}
    else:
        source = {"dataset": dataset, "expected_count": len(rows) if rows is not None else dataset.get("rows"),
                  "item_schema": value.get("item_schema") or (infer_item_schema(rows) if rows else None)}
    return evaluation.run_agent_eval(
        clients.evals, ledger, key=key, name=safe_identifier(value.get("name") or f"{spec.agent}-v{version}", "eval name"),
        agent_name=spec.agent, agent_version=version, testing_criteria=value["testing_criteria"],
        input_template=value.get("input_template", DEFAULT_INPUT_TEMPLATE), attempts=max(1, int(seconds // 10)),
        interval=10.0, seconds=seconds, sleep=clients.sleep, clock=clients.clock, **source)


def register_evaluator(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, evaluator: Any = None) -> dict[str, Any]:
    """Register a custom code evaluator from a pinned spec, read it back, then run its native canary.

    Spec: `{name, metric, display_name, data_schema, description?, code_text | (code_file, code_sha256),
    canary: {criterion_name, item_schema, data_mapping, match_field, metric?, cases | (cases_file, cases_sha256)}}`.
    """
    spec.require("register_evaluator")
    value = input_json(spec, "evaluator", evaluator)
    path = spec.observed_inputs["evaluator"]["path"]
    if not isinstance(value, dict) or not isinstance(value.get("canary"), dict):
        raise RefusedError("evaluator_shape", "evaluator spec needs name, metric, data_schema, code and canary")
    code = value.get("code_text")
    if code is None:
        code = referenced_file(path, value.get("code_file"), value.get("code_sha256"), "evaluator_code").decode()
    elif "code_sha256" in value and sha256_hex(code.encode()) != value["code_sha256"]:
        raise RefusedError("evaluator_code_pin", "inline evaluator code differs from code_sha256")
    canary = value["canary"]
    cases = canary.get("cases")
    if cases is None and "cases_file" in canary:
        cases = json.loads(referenced_file(path, canary["cases_file"], canary.get("cases_sha256"), "canary_cases"))
    if isinstance(cases, dict):
        cases = cases.get("canaries") or cases.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RefusedError("canary_missing", "evaluator canary needs cases")
    try:
        definition = code_evaluator_definition(code, metric=value["metric"], data_schema=value["data_schema"],
                                               display_name=value["display_name"],
                                               description=value.get("description", ""))
        registered = register_code_evaluator(clients.project, ledger, name=value["name"], definition=definition)
        result = run_code_evaluator_canary(
            clients.evals, ledger, key=f"{value['name']}-v{registered['version']}", evaluator_name=value["name"],
            evaluator_version=registered["version"], criterion_name=canary["criterion_name"],
            item_schema=canary["item_schema"], data_mapping=canary["data_mapping"],
            cases=[{"item": case["item"], "expected": case["expected"]} for case in cases],
            match_field=canary["match_field"], metric=canary.get("metric"), sleep=clients.sleep, clock=clients.clock)
    except KeyError as error:
        raise RefusedError("evaluator_shape", f"evaluator spec field missing: {error.args[0]}") from error
    return {"evaluator": {"name": registered["name"], "version": registered["version"],
                          "code_sha256": sha256_hex(code.encode())},
            "canary": {key: result.get(key) for key in ("passed", "scores", "eval_id", "run_id", "status")}}


# --- optimize / select -----------------------------------------------------------------------

def _candidate_rows(eval_client: Any, candidate: dict[str, Any], expected: int) -> list[dict[str, Any]]:
    """Compact native validation rows of one candidate's eval run: item, output text and per-criterion scores."""
    rows = collect_rows(eval_client, eval_id=candidate["eval_id"], run_id=candidate["eval_run_id"],
                        expected_count=expected)
    compact = []
    for row in rows:
        if row.get("eval_id") != candidate["eval_id"] or row.get("run_id") != candidate["eval_run_id"]:
            raise VerificationError("candidate_rows_foreign", "native row belongs to another evaluation run")
        item = row.get("datasource_item") or {}
        compact.append({"id": row.get("id"), "status": row.get("status"), "query": item.get("query"),
                        "ground_truth": item.get("ground_truth"), "output_text": item.get("sample.output_text"),
                        "scores": {str(result.get("name")): result.get("score") if result.get("status") == "completed"
                                   and not result.get("error") else None
                                   for result in row.get("results") or [] if isinstance(result, dict)}})
    return compact


def _optimization_summary(retained: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": retained["job_id"], "settled": True, "status": retained["listing"]["status"],
            "baseline": retained["listing"]["baseline"], "generated": retained["listing"]["generated"],
            "candidates": [{"candidate_id": item["candidate_id"], "avg_score": item["avg_score"],
                            "observation_index": item["observation_index"], "is_baseline": item["is_baseline"],
                            "config_sha256": retained["configs"][item["candidate_id"]]["sha256"]}
                           for item in retained["listing"]["candidates"]],
            "notes": retained["listing"]["notes"]}


def _with_models(spec: RunSpec, value: dict[str, Any]) -> dict[str, Any]:
    """Spec `models.optimizer`/`models.judge` fill `optimization_model`/`eval_model`; a differing file value refuses."""
    for field, model in (("optimization_model", spec.models.get("optimizer")), ("eval_model", spec.models.get("judge"))):
        if model is None:
            continue
        if value.get(field) not in (None, model):
            raise RefusedError("model_mismatch", f"optimization {field} differs from the run spec models")
        value = {**value, field: model}
    return value


def optimize(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, optimization_spec: Any = None, train: Any = None,
             validation: Any = None, *, previous: bool = False) -> dict[str, Any]:
    """One native optimization job on the target version: submit once, wait (bounded), list and resolve every
    candidate. Resumable: rerun resumes polling from the retained job identity; never resubmits.

    Spec: `{evaluators: [{name, version}], optimization_model, max_candidates, eval_model?, max_stalls?,
    optimization_config?, item_fields?, wait_seconds?}`. Rows are projected to the optimizer's item fields.
    All candidate configs (baseline included) are retained in `optimize-<key>-candidates.json`; with `clients.evals`,
    so are each candidate's native validation rows (for `criterion_mean` selection). `previous` targets the spec's
    reviewed `previous_version`, so an optimization series need not deploy.
    """
    spec.require("optimize")
    value = input_json(spec, "optimization", optimization_spec)
    if not isinstance(value, dict) or set(value) - OPTIMIZATION_FIELDS:
        raise RefusedError("optimization_shape", "unknown optimization spec fields")
    if not value.get("evaluators"):
        raise RefusedError("evaluators_missing", "optimization needs registered evaluator references")
    value = _with_models(spec, value)
    if type(value.get("max_candidates")) is int and value["max_candidates"] > spec.bounds["max_candidates"]:
        raise RefusedError("bound_candidates", "max_candidates exceeds bounds.max_candidates")
    fields = value.get("item_fields")
    train_rows, train_ref = load_rows(spec, "train", train, fields=fields, allowed=ITEM_FIELDS)
    validation_rows, validation_ref = load_rows(spec, "validation", validation, fields=fields, allowed=ITEM_FIELDS)
    if previous:
        version = spec.previous_version
        if version is None:
            raise RefusedError("previous_missing", "--previous-version needs previous_version in the run manifest")
        label, _ = current_label(spec, clients)
    else:
        label, deployed = current_deployment(spec, clients, ledger)
        version = deployed["version"]

    def job_for(train_source: dict[str, Any], validation_source: dict[str, Any]) -> dict[str, Any]:
        try:
            return optimization_job(spec.agent, version, evaluators=value["evaluators"],
                                    optimization_model=value["optimization_model"],
                                    max_candidates=value["max_candidates"], eval_model=value.get("eval_model"),
                                    max_stalls=value.get("max_stalls"),
                                    optimization_config=value.get("optimization_config"),
                                    **train_source, **validation_source)
        except KeyError as error:
            raise RefusedError("optimization_shape", f"optimization spec field missing: {error.args[0]}") from error

    # The key names the content (rows or spec refs); registered dataset versions follow from the same rows.
    job = job_for({"train_items": train_rows} if train_rows is not None else {"train_dataset": train_ref},
                  {"validation_items": validation_rows} if validation_rows is not None
                  else {"validation_dataset": validation_ref})
    key = f"{label}-v{version}-{sha256_hex(canonical(job))[:16]}" + ("-ds" if spec.data == "dataset" else "")
    record = f"optimize-{key}-candidates.json"
    if ledger.exists(record):
        return {"record": record, **_optimization_summary(ledger.read(record))}
    foreign = [name for name in ledger.list("optimize-*-intent.json") if name != f"optimize-{key}-intent.json"]
    if foreign:
        raise RefusedError("series_optimized", "this series already submitted another optimization job")
    validation_count = len(validation_rows) if validation_rows is not None else validation_ref.get("rows")
    if spec.data == "dataset" and not ledger.exists(f"optimize-{key}-identity.json"):
        train_dataset = register_rows(spec, clients.project, ledger, "train", train_rows, train_ref)
        validation_dataset = register_rows(spec, clients.project, ledger, "validation", validation_rows, validation_ref)
        job = job_for({"train_dataset": train_dataset}, {"validation_dataset": validation_dataset})
    submitted = optimization.submit_optimization(clients.project, ledger, key=key, job=job)
    polled = wait_optimization(clients.project, job_id=submitted["job_id"], interval=20.0, sleep=clients.sleep,
                               clock=clients.clock, seconds=bounded_seconds(
                                   value.get("wait_seconds", spec.bounds["optimize_wait_seconds"]), OPTIMIZE_WAIT_CEILING))
    if not polled.settled:
        return {"job_id": submitted["job_id"], "settled": False, "status": polled.value.get("status"),
                "next": "rerun optimize to resume polling; never resubmit"}
    listing = list_candidates(polled.value, require_generated=False)
    configs = {}
    for candidate in listing["candidates"]:
        config = resolve_candidate_config(clients.project, endpoint=spec.targets["project_endpoint"],
                                          job_id=submitted["job_id"], candidate_id=candidate["candidate_id"],
                                          request_factory=clients.request_factory)
        configs[candidate["candidate_id"]] = {"config": config, "sha256": sha256_hex(canonical(config))}
    retained = {"job_id": submitted["job_id"], "operation_id": submitted["operation_id"], "agent_version": version,
                "listing": listing, "configs": configs, "job": polled.value}
    if clients.evals is not None and validation_count:
        retained.update(validation_count=validation_count, rows={
            candidate["candidate_id"]: _candidate_rows(clients.evals, candidate, validation_count)
            for candidate in listing["candidates"]})
    ledger.retain(record, retained)
    return {"record": record, **_optimization_summary(retained)}


def select(spec: RunSpec, clients: Clients | None, ledger: EvidenceLedger, rule: Any = None, *,
           demonstration: bool = False) -> dict[str, Any]:
    """Apply the frozen selection rule to the series' one retained optimization job. Ledger-only, deterministic.

    Rule file: `{status: frozen, score: avg_score | criterion_mean, criterion?, eligibility: strictly_above_baseline,
    tie_break: earliest_observation, fallback: baseline, demonstration: {allowed, label: demonstration}}`.
    `criterion_mean` scores each candidate by the named native criterion over its retained validation rows; missing
    or errored rows score 0 and stay in the denominator. Eligible candidates score strictly above the same job's
    baseline; highest wins, ties to earliest observation; none eligible keeps the baseline. `demonstration` promotes
    the top candidate only when the rule allows it, labelled `demonstration`, never optimized.
    """
    data = read_input(spec, "selection_rule", rule)
    value = parse_json(data, "selection_rule")
    if not isinstance(value, dict) or value.get("status") != "frozen":
        raise RefusedError("rule_unfrozen", "selection rule must be frozen (status: frozen) and pinned")
    drifted = sorted(key for key, expected in SELECTION_RULE.items() if value.get(key) != expected)
    if value.get("score") not in SELECTION_SCORES:
        drifted.insert(0, "score")
    criterion = value.get("criterion")
    if (value.get("score") == "criterion_mean") != (isinstance(criterion, str) and bool(criterion)):
        drifted.append("criterion")
    if drifted:
        raise RefusedError("rule_unsupported", "unsupported selection rule fields: " + ", ".join(drifted))
    policy = value.get("demonstration") or {}
    if demonstration and not (policy.get("allowed") is True and policy.get("label") == "demonstration"):
        raise RefusedError("demonstration_refused", "frozen rule does not allow labelled demonstration promotion")
    names = ledger.list("optimize-*-candidates.json")
    if len(names) != 1:
        raise RefusedError("optimization_missing", "exactly one retained optimization job required in this series")
    retained = ledger.read(names[0])
    score_kind = SCORE_KIND
    if criterion is None:
        candidates = retained["listing"]["candidates"]
    else:
        rows, count = retained.get("rows"), retained.get("validation_count")
        if not isinstance(rows, dict) or type(count) is not int or count < 1 or any(
                item["candidate_id"] not in rows for item in retained["listing"]["candidates"]):
            raise RefusedError("criterion_rows_missing", "retained job lacks native validation rows for every candidate")

        def mean(candidate_id: str) -> float:
            scores = [row["scores"].get(criterion) for row in rows[candidate_id] if row.get("status") == "completed"]
            return sum(score for score in scores if type(score) in (int, float)) / count

        candidates = [{**item, "avg_score": mean(item["candidate_id"])} for item in retained["listing"]["candidates"]]
        score_kind = f"mean native `{criterion}` score over {count} validation rows; missing or errored rows score 0"
    baseline = next(item for item in candidates if item["is_baseline"])
    generated = [item for item in candidates if not item["is_baseline"]]
    eligible = [item for item in generated if item["avg_score"] > baseline["avg_score"]]

    def best(pool: list[dict[str, Any]]) -> dict[str, Any]:
        return min(pool, key=lambda item: (-item["avg_score"], item["observation_index"]))

    if eligible:
        decision, chosen = "selected", best(eligible)
    elif demonstration and generated:
        decision, chosen = "demonstration", best(generated)
    else:
        decision, chosen = "baseline", None
    result = {"decision": decision, "label": "demonstration" if decision == "demonstration" else None,
              "job_id": retained["job_id"], "agent_version": retained["agent_version"], "score_kind": score_kind,
              "rule_sha256": sha256_hex(data), "optimization_record": names[0],
              "baseline": {"candidate_id": baseline["candidate_id"], "score": baseline["avg_score"]},
              "candidates": [{"candidate_id": item["candidate_id"], "score": item["avg_score"],
                              "observation_index": item["observation_index"], "eligible": item in eligible}
                             for item in generated],
              "candidate_id": None, "score": None, "config": None, "config_sha256": None}
    if chosen is not None:
        entry = retained["configs"][chosen["candidate_id"]]
        result.update(candidate_id=chosen["candidate_id"], score=chosen["avg_score"], config=entry["config"],
                      config_sha256=entry["sha256"])
    name = f"select-{retained['job_id']}-{result['rule_sha256'][:16]}-{decision}.json"
    retained_record = ledger.retain(name, result, allow_identical=True)
    return {**result, "record": retained_record["path"]}


# --- inspect / logs / teardown ---------------------------------------------------------------

def inspect(spec: RunSpec, clients: Clients, ledger: EvidenceLedger) -> dict[str, Any]:
    """Read-only inventory: agent, versions, sessions, and which versions this series created."""
    project = clients.project
    try:
        agent = to_plain(project.agents.get(agent_name=spec.agent))
    except Exception as error:
        if not is_not_found(error):
            raise
        agent = None
    versions = list_versions(project, spec.agent) if agent else []
    sessions = list_sessions(project, spec.agent) if agent else []
    owned = sorted({str(ledger.read(name)["version"]) for name in ledger.list("deploy-*-active.json")}, key=int)
    return {"agent_exists": agent is not None, "owned_versions": owned,
            "versions": [{"version": str(item.get("version")), "status": item.get("status"),
                          "image": ((item.get("definition") or {}).get("container_configuration") or {}).get("image"),
                          "metadata": item.get("metadata")} for item in versions],
            "sessions": [{"id": item.get("agent_session_id"), "status": item.get("status"),
                          "version": (item.get("version_indicator") or {}).get("agent_version")} for item in sessions]}


def logs(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, session_id: str | None = None,
         max_sessions: int = 3) -> dict[str, Any]:
    """Bounded redacted exception excerpts for the deployed version's sessions (or one named session)."""
    _, deployed = current_deployment(spec, clients, ledger)
    version = deployed["version"]
    if session_id is not None:
        sessions = [safe_identifier(session_id, "session id")]
    else:
        sessions = [item["agent_session_id"] for item in list_sessions(clients.project, spec.agent)
                    if str((item.get("version_indicator") or {}).get("agent_version")) == version][:max_sessions]
    return {"version": version, "excerpts": [session_log_excerpt(clients.project, agent_name=spec.agent,
                                                                 agent_version=version, session_id=sid)
                                             for sid in sessions]}


def teardown(spec: RunSpec, clients: Clients, ledger: EvidenceLedger, *, execute: bool) -> dict[str, Any]:
    """Owned responses -> sessions -> versions, then agent read-back. `execute=False` plans only."""
    if execute:
        spec.require("teardown")
    response_ids = [ledger.read(name)["response"]["id"] for name in ledger.list("invoke-*-result.json")]
    versions = sorted({str(ledger.read(name)["version"]) for pattern in ("deploy-*-created.json", "deploy-*-active.json")
                       for name in ledger.list(pattern)}, key=int)
    steps = HostedTeardown(clients.project, ledger, agent_name=spec.agent, execute=execute, sleep=clients.sleep)
    result = {"execute": execute,
              "responses": steps.responses(clients.openai, response_ids, bearer_token=clients.token(),
                                           http_client=clients.http),
              "sessions": steps.sessions(),
              "versions": steps.versions(versions)}
    if execute:
        result["agent"] = steps.agent_readback()
    return result
