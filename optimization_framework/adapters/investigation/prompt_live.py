"""Bounded source-prompt comparison through the native Investigation service."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import httpx


PROMPT_PATH = "prompts/cyber/cyber_defender.md"
FIELDS = {"observation", "inference", "unknowns", "scope", "citation_ids"}
SCENARIOS = (
    {
        "id": "synthetic-authentication",
        "historical_replay": True,
        "scope": "2026-01-01T00:00:00Z/2026-01-01T00:05:00Z",
        "rows": [{"resource_id": "synthetic-auth-001", "host": "synthetic-host-a",
                  "account": "synthetic-account-a", "event": "explicit credential logon",
                  "timestamp": "2026-01-01T00:02:00Z", "count": 1}],
        "unknown": "Whether the account owner authorized the logon is not supplied.",
    },
    {
        "id": "synthetic-session-title",
        "historical_replay": True,
        "scope": "2026-01-02T00:00:00Z/2026-01-02T00:05:00Z",
        "rows": [{"resource_id": "synthetic-session-001", "host": "synthetic-host-b",
                  "account": "synthetic-account-b", "event": "session window title displayed nslookup",
                  "timestamp": "2026-01-02T00:02:00Z", "count": 1}],
        "unknown": "Whether nslookup executed is not supplied; a window title is not execution proof.",
    },
)
SCHEDULE = ((0, "baseline"), (0, "candidate"), (1, "candidate"), (1, "baseline"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}


def prepare_controls(source: Path, root: Path, instruction: str):
    from app.cybereye.backend.agents.config import load_agent_spec

    shutil.copytree(source, root / "baseline")
    shutil.copytree(root / "baseline", root / "candidate")
    prompt = root / "candidate" / PROMPT_PATH
    prompt.write_bytes(prompt.read_bytes() + ("\n\n" + instruction + "\n").encode())
    baseline_hashes, candidate_hashes = hashes(root / "baseline"), hashes(root / "candidate")
    changed = [name for name in baseline_hashes if baseline_hashes[name] != candidate_hashes[name]]
    if changed != [PROMPT_PATH] or baseline_hashes.keys() != candidate_hashes.keys():
        raise ValueError("prompt_only_change_required")
    specs = {variant: load_agent_spec(root / variant / "agent_config.yaml")
             for variant in ("baseline", "candidate")}
    baseline, candidate = specs.values()
    if (baseline.tools != candidate.tools or baseline.foundation_files != candidate.foundation_files
            or baseline.config_digest == candidate.config_digest
            or baseline.instructions == candidate.instructions):
        raise ValueError("prompt_invariants_failed")
    pins = {variant: {"config_digest": spec.config_digest,
                      "instructions_sha256": digest(spec.instructions),
                      "prompt_sha256": hashes(root / variant)[PROMPT_PATH],
                      "control_hashes": hashes(root / variant)}
            for variant, spec in specs.items()}
    return specs, {"variants": pins, "changed_control_paths": changed,
                   "tools_unchanged": True, "foundations_unchanged": True}


def request_text(scenario: dict) -> str:
    return ("Review only this supplied synthetic historical incident evidence. This is not a scanner "
            "situation or an open-ended investigation. Do not call tools or retrieve additional data. "
            "Report observation, inference, unknowns and bounded scope. Cite the supplied resource_id "
            "for the observed row, never an invented identifier. Treat unknowns as unknown; do not "
            "claim confirmed execution, compromise or containment.\n" + json.dumps(scenario, sort_keys=True))


def evaluate(text: str, scenario: dict) -> dict:
    identifiers = [row["resource_id"] for row in scenario["rows"]]
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = None
    exact_fields = isinstance(payload, dict) and set(payload) == FIELDS
    checks = {
        "exact_json_fields": exact_fields,
        "nonempty_sections": bool(exact_fields and all(
            isinstance(payload[name], str) and payload[name].strip()
            for name in FIELDS - {"citation_ids"})),
        "exact_scope": bool(exact_fields and payload["scope"] == scenario["scope"]),
        "only_supplied_citations": bool(exact_fields and payload["citation_ids"] == identifiers),
        "observed_host_and_account": bool(exact_fields and isinstance(payload["observation"], str)
            and all(scenario["rows"][0][name] in payload["observation"] for name in ("host", "account"))),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "semantic_entailment": "requires receipt review; not established by field checks"}


class RefuseData:
    def __getattr__(self, name):
        raise RuntimeError("synthetic_probe_forbids_data_access")


class CountedTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner = inner
        self.requests = []
        self.active = None

    async def handle_async_request(self, request):
        from llm_interface import LlmError

        if self.active is None or len(self.requests) >= 4 or self.active["requests"] >= 1:
            raise LlmError("prompt_request_budget", category="denied")
        body = json.loads(request.content)
        spec = self.active["spec"]
        instructions = body.get("instructions")
        if instructions is None:
            instructions = next((message.get("content") for message in body.get("messages", [])
                                 if message.get("role") in {"system", "developer"}), None)
        if instructions != spec.instructions:
            raise LlmError("prompt_delivery_mismatch", category="denied")
        advertised = [item.get("function", item) for item in body.get("tools", [])]
        actual = {item["name"]: item["parameters"] for item in advertised}
        expected = {item.metadata.name: item.metadata.parameters for item in spec.tools}
        if actual != expected or body.get("model") != spec.model or body.get("store") is not False:
            raise LlmError("prompt_native_contract_mismatch", category="denied")
        entry = {"scenario": self.active["scenario"], "variant": self.active["variant"],
                 "request_sha256": hashlib.sha256(request.content).hexdigest(),
                 "instructions_sha256": digest(instructions), "tool_schemas_unchanged": True,
                 "model": body["model"], "method": request.method, "url": str(request.url),
                 "dispatched_at": datetime.now(timezone.utc).isoformat()}
        self.active["requests"] += 1
        self.requests.append(entry)
        started = time.monotonic()
        try:
            response = await self.inner.handle_async_request(request)
            entry["http_status"] = response.status_code
            if response.status_code >= 400:
                await response.aread()
                try:
                    error = response.json().get("error", {})
                    entry["provider_error_code"] = safe_code(error.get("code"))
                except (ValueError, AttributeError):
                    entry["provider_error_code"] = "unavailable"
            return response
        finally:
            entry["response_headers_seconds"] = round(time.monotonic() - started, 6)

    async def aclose(self):
        await self.inner.aclose()


def safe_code(value) -> str:
    import re

    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value) else "unavailable"


def safe_failure(error: Exception) -> dict:
    from llm_interface import LlmError

    if isinstance(error, LlmError):
        return error.metadata()
    return {"code": "deadline_exceeded" if isinstance(error, TimeoutError) else "probe_failed",
            "exception_type": type(error).__name__, "detail": "exception payload omitted"}


async def run_variant(spec, scenario: dict, model) -> dict:
    from app.cybereye.backend.agents.service import AgentService
    from llm_interface import LlmError

    service = AgentService(RefuseData(), RefuseData(), spec, connection=model,
                           authorize_tool=lambda call: False)
    session = service.create_session(principal="synthetic-prompt-owner")
    terminal = None
    async for event, data in service.stream_turn(request_text(scenario), principal="synthetic-prompt-owner",
                                                session=session, situation=None):
        if event == "done":
            terminal = data
    result = session.result(principal="synthetic-prompt-owner")
    if result is None or terminal is None or terminal["status"] != "completed":
        raise LlmError("prompt_incomplete", category="interrupted")
    try:
        session.result(principal="foreign-owner")
    except LlmError:
        owner_refused = True
    else:
        raise LlmError("prompt_owner_check_failed", category="denied")
    return {"output": result.text, "evaluation": evaluate(result.text, scenario),
            "native_receipt": result.additional_properties["llm_interface"],
            "foreign_owner_refused": owner_refused}


async def prompt_live(*, allow_model_calls: bool) -> dict:
    if not allow_model_calls:
        return {"status": "refusal", "failure": {"code": "explicit_model_permission_required"},
                "model_request_count": 0}

    from azure.identity.aio import DefaultAzureCredential
    from dotenv import dotenv_values
    from llm_interface import Capabilities, Limits, connect
    import yaml
    import adapter

    started = time.monotonic()
    source = adapter.APP / "app/cybereye/control"
    local = adapter.APP / "app/cybereye/.local"
    source_before, local_before = adapter.source_hashes(), hashes(local)
    contract_path = adapter.TASKS / "prompt.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    receipt = {"status": "refusal", "evidence_class": "live_model_synthetic_supplied_evidence",
               "started_at": datetime.now(timezone.utc).isoformat(),
               "command": [sys.executable, *sys.argv], "cwd": str(Path.cwd()),
               "python": sys.version.split()[0], "source_hashes": source_before,
               "task_sha256": adapter.sha256(contract_path), "trials": [],
               "scenarios": SCENARIOS, "scenario_sha256": digest(json.dumps(SCENARIOS, sort_keys=True)),
               "schedule": SCHEDULE, "max_model_requests": 4, "timeout_seconds_per_run": 120,
               "credential": "azure.identity.aio.DefaultAzureCredential; borrowed current identity",
               "tool_execution": "denied", "data_access": "no ADX/scanner/cloud data clients constructed",
               "limitations": ["Two synthetic cases, one observation per variant; not a general behavior benchmark.",
                               "Evidence supplied in analyst message, not fetched through tools or persisted profiles.",
                               "No production lifespan, browser or deployed-auth acceptance.",
                               "Provider billing and work after timeout are unknown; no automatic retries.",
                               "Semantic entailment requires review of retained synthetic outputs."]}
    transport = CountedTransport(httpx.AsyncHTTPTransport(retries=0, trust_env=False))
    previous_env = {name: os.environ.get(name) for name in ("PYTHON_DOTENV_DISABLED", "CYBEREYE_AGENT_STORE_DIR")}
    logging.getLogger("azure").setLevel(logging.CRITICAL)
    logging.getLogger("agent_framework").setLevel(logging.CRITICAL)
    try:
        with tempfile.TemporaryDirectory(prefix="investigation-prompt-") as temporary:
            root = Path(temporary)
            os.environ["PYTHON_DOTENV_DISABLED"] = "1"
            os.environ["CYBEREYE_AGENT_STORE_DIR"] = str(root / "agents")
            sys.path.insert(0, str(adapter.APP))
            specs, controls = prepare_controls(source, root, contract["instruction"])
            receipt.update(controls)
            target_path = adapter.REPO / "deploy/env/existing-perth-m1.env"
            endpoint = os.environ.get("CYBEREYE_OPENAI_ENDPOINT")
            receipt["endpoint_source"] = "environment:CYBEREYE_OPENAI_ENDPOINT"
            if not endpoint:
                endpoint = dotenv_values(target_path, interpolate=False).get("CYBEREYE_OPENAI_ENDPOINT")
                receipt["endpoint_source"] = str(target_path.relative_to(adapter.REPO))
            if not endpoint:
                raise ValueError("configured_endpoint_missing")
            limits = Limits(timeout_seconds=120, max_model_calls=1, max_tool_calls=1,
                            max_output_tokens=specs["baseline"].max_output_tokens, max_concurrency=1)
            receipt["limits"] = asdict(limits)
            async with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
                async with connect(endpoint, specs["baseline"].model, credential=credential,
                                   allow_model_calls=True, transport=transport, limits=limits,
                                   capabilities=Capabilities(reasoning=True),
                                   allowed_tools=tuple(tool.metadata.name for tool in specs["baseline"].tools)) as model:
                    receipt["connection"] = asdict(model.config)
                    receipt["runtime"] = {name: {"path": str(Path(module.__file__).resolve()),
                                                "sha256": adapter.sha256(Path(module.__file__))}
                                          for name in ("llm_interface", "agent_framework")
                                          if (module := sys.modules.get(name)) is not None}
                    for index, variant in SCHEDULE:
                        scenario, spec = SCENARIOS[index], specs[variant]
                        transport.active = {"spec": spec, "scenario": scenario["id"],
                                            "variant": variant, "requests": 0}
                        trial = {"scenario": scenario["id"], "variant": variant,
                                 "input_sha256": digest(request_text(scenario))}
                        receipt["trials"].append(trial)
                        trial_started = time.monotonic()
                        try:
                            async with asyncio.timeout(120):
                                trial.update(await run_variant(spec, scenario, model))
                        except Exception as error:
                            trial["failure"] = safe_failure(error)
                            receipt["failure"] = trial["failure"]
                            break
                        finally:
                            trial["duration_seconds"] = round(time.monotonic() - trial_started, 6)
                            trial["model_requests"] = transport.active["requests"]
                    if "failure" not in receipt:
                        candidates = [trial for trial in receipt["trials"] if trial["variant"] == "candidate"]
                        baselines = [trial for trial in receipt["trials"] if trial["variant"] == "baseline"]
                        passed = (len(candidates) == len(baselines) == 2
                                  and all(trial["evaluation"]["passed"] for trial in candidates)
                                  and all(not trial["evaluation"]["checks"]["exact_json_fields"] for trial in baselines)
                                  and all(trial["model_requests"] == 1 for trial in receipt["trials"]))
                        receipt["status"] = "pass" if passed else "refusal"
                        receipt["behavior_acceptance"] = "narrow_format_adherence_passed" if passed else "not_established"
            receipt["source_unchanged"] = adapter.source_hashes() == source_before
        receipt["temporary_candidate_state_removed"] = not root.exists()
    except Exception as error:
        receipt["failure"] = safe_failure(error)
    finally:
        await transport.aclose()
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        receipt["requests"] = transport.requests
        receipt["model_request_count"] = len(transport.requests)
        receipt["source_unchanged"] = adapter.source_hashes() == source_before
        receipt["original_local_state_unchanged"] = hashes(local) == local_before
        receipt["original_local_manifest_sha256"] = digest(json.dumps(local_before, sort_keys=True))
        receipt["temporary_candidate_state_removed"] = "root" in locals() and not root.exists()
        receipt["duration_seconds"] = round(time.monotonic() - started, 6)
        receipt["retained_processes"] = []
        if not receipt["source_unchanged"] or not receipt["original_local_state_unchanged"]:
            receipt["status"] = "refusal"
            receipt["integrity_failure"] = True
    return receipt