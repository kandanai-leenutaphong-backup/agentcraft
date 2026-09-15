from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import time
import zipfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ("PASS_LIVE", "PASS_REFUSAL", "FAIL", "BLOCKED", "NOT_RUN")
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
READ_AUTHORITY = "Live testing authorized against all existing deployed data sou4ces on Azure. Proceed."
ERROR_CODES = {"preflight_refused", "case_failed", "case_interrupted", "budget_exhausted",
               "oracle_mismatch", "credential_unavailable", "service_failed", "incomplete_result"}


class LiveRefusal(ValueError):
    pass


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LiveRefusal(code)


def fields(value, expected: set[str], code: str) -> None:
    require(isinstance(value, dict) and set(value) == expected, code)


def positive(value, maximum: int, *, integer: bool = True) -> bool:
    return (type(value) is int if integer else type(value) in (int, float)) and math.isfinite(value) and 0 < value <= maximum


def validate_plan(value: dict, *, require_oracle: bool = True) -> dict:
    fields(value, {"schema_version", "run_id", "target", "artifact", "limits", "data_classification", "retention", "cases"}
           | ({"baseline_binding"} if "baseline_binding" in value else set()), "invalid_plan_fields")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "invalid_plan_version")
    require(isinstance(value["run_id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value["run_id"]), "invalid_run_id")
    require(value["data_classification"] in ("synthetic", "approved-historical-replay"), "invalid_data_classification")
    require(value["retention"] == "receipt-only", "retention_not_supported")
    target = value["target"]
    service = target.get("service") if isinstance(target, dict) else None
    require(service in ("adx", "search"), "profile_not_implemented")
    fields(target, {"service", "subscription_id", "tenant_id", "principal_id", "resource_id", "endpoint"}
           | ({"database"} if service == "adx" else {"index", "key_field"}), "invalid_target_fields")
    for name in ("subscription_id", "tenant_id", "principal_id"):
        require(isinstance(target[name], str) and re.fullmatch(UUID, target[name]), "invalid_identity")
    require(isinstance(target["resource_id"], str), "invalid_resource")
    if service == "adx":
        resource = re.fullmatch(rf"/subscriptions/({UUID})/resourceGroups/([A-Za-z0-9_.-]+)/providers/Microsoft.Kusto/clusters/([a-z0-9-]+)/databases/([A-Za-z][A-Za-z0-9_-]*)", target["resource_id"])
        require(resource is not None and resource[4] == target["database"], "target_mismatch")
    else:
        resource = re.fullmatch(rf"/subscriptions/({UUID})/resourceGroups/([A-Za-z0-9_.-]+)/providers/Microsoft.Search/searchServices/([a-z0-9-]+)", target["resource_id"])
        require(isinstance(target["index"], str) and len(target["index"]) <= 128
                and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", target["index"]), "invalid_index")
        require(isinstance(target["key_field"], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", target["key_field"]), "invalid_key_field")
    require(resource is not None and resource[1] == target["subscription_id"], "target_mismatch")
    require(isinstance(target["endpoint"], str), "invalid_endpoint")
    try:
        endpoint = urlsplit(target["endpoint"])
        valid_endpoint = (endpoint.scheme == "https" and endpoint.hostname is not None
                          and endpoint.hostname.endswith(".kusto.windows.net" if service == "adx" else ".search.windows.net")
                          and endpoint.hostname.split(".")[0] == resource[3]
                          and endpoint.port in (None, 443) and not endpoint.username
                          and not endpoint.password and not endpoint.path and not endpoint.query
                          and not endpoint.fragment and endpoint.hostname == endpoint.hostname.lower())
    except ValueError:
        valid_endpoint = False
    require(valid_endpoint, "invalid_endpoint")
    artifact = value["artifact"]
    fields(artifact, {"distribution", "version", "wheel", "sha256"}, "invalid_artifact_fields")
    require(artifact["distribution"] == "azdata" and isinstance(artifact["version"], str)
            and re.fullmatch(r"[0-9][A-Za-z0-9.+-]{0,63}", artifact["version"]), "invalid_artifact_identity")
    require(isinstance(artifact["wheel"], str) and Path(artifact["wheel"]).is_absolute(), "artifact_path_required")
    require(isinstance(artifact["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"]), "artifact_digest_required")
    limits = value["limits"]
    fields(limits, {"max_calls", "timeout_seconds", "max_rows", "max_output_bytes"}, "invalid_limit_fields")
    for name, maximum in (("max_calls", 100), ("timeout_seconds", 600), ("max_rows", 1000), ("max_output_bytes", 1048576)):
        require(positive(limits[name], maximum, integer=name != "timeout_seconds"), "invalid_limits")
    require(isinstance(value["cases"], list) and 0 < len(value["cases"]) <= limits["max_calls"], "case_count_exceeds_budget")
    identifiers = set()
    for case in value["cases"]:
        case_fields = {"case_id", "expression", "parameters", "expected_status", "expected"}
        if service == "search":
            case_fields.update({"operation", "projection", "options"})
        else:
            case_fields.update({"comparison", "semantic"} & set(case))
            require(case.get("comparison", "ordered") in {"ordered", "typed-multiset"}, "invalid_comparison")
            require(case.get("semantic", "query") in {"query", "count", "ordinal-schema", "preview"}, "invalid_semantic")
        if "workflow" in case:
            case_fields.update({"workflow", "reads", "missing"})
        fields(case, case_fields, "invalid_case_fields")
        if "workflow" in case:
            require(service == "search" and case["workflow"] == "search-citation"
                and case["operation"] == "query" and case["expected_status"] == "success", "invalid_workflow")
            require(isinstance(case["reads"], list) and 0 < len(case["reads"]) <= 100
                and isinstance(case["missing"], dict), "invalid_workflow_reads")
            downstream = [*case["reads"], case["missing"]]
            require(all(item.get("operation") == "read" and "workflow" not in item
                and item.get("expected_status") == "success" for item in downstream), "invalid_workflow_reads")
            validate_plan({**value, "cases": downstream})
            require(isinstance(case["expected"], dict)
                and len(case["expected"].get("documents", [])) == len(case["reads"])
                and case["missing"]["expected"]["documents"] == [], "workflow_baseline_required")
            require(all(document.get(target["key_field"]) == read["expression"]
                for document, read in zip(case["expected"]["documents"], case["reads"])), "workflow_key_mismatch")
            require(1 + len(downstream) <= limits["max_calls"], "workflow_exceeds_budget")
        identifier = case["case_id"]
        require(isinstance(identifier, str) and re.fullmatch(rf"LI-{service.upper()}-[A-Za-z0-9_.-]{{1,64}}", identifier)
                and identifier not in identifiers, "duplicate_or_invalid_case")
        identifiers.add(identifier)
        require(isinstance(case["expression"], str) and 0 < len(case["expression"]) <= 12000
                and not case["expression"].lstrip().startswith("."), "read_query_required")
        require(isinstance(case["parameters"], dict), "invalid_parameters")
        if service == "search":
            require(case["operation"] in ("query", "read", "schema") and not case["parameters"], "only_search_reads_implemented")
            require(isinstance(case["projection"], list) and all(isinstance(name, str)
                and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) for name in case["projection"]), "invalid_projection")
            options = case["options"]
            require(isinstance(options, dict) and set(options) <= {"count", "filter", "orderby"}, "unsafe_search_options")
            require(all(type(option) is bool if name == "count" else isinstance(option, str)
                for name, option in options.items()), "invalid_search_options")
            require(case["operation"] == "query" or not options, "unexpected_search_options")
        require(case["expected_status"] in ("success", "denied", "invalid", "unsupported"), "invalid_expected_status")
        if case["expected_status"] == "success":
            expected = case["expected"]
            if expected is None and not require_oracle:
                continue
            if service == "search":
                fields(expected, {"documents", "metadata", "truncated"}, "expected_result_required")
                require(isinstance(expected["documents"], list) and len(expected["documents"]) <= limits["max_rows"]
                        and all(isinstance(document, dict) for document in expected["documents"])
                        and isinstance(expected["metadata"], dict) and type(expected["truncated"]) is bool, "invalid_expected_documents")
                continue
            fields(expected, {"columns", "rows", "truncated"}, "expected_result_required")
            require(isinstance(expected["columns"], list) and all(isinstance(name, str) for name in expected["columns"])
                    and len(set(expected["columns"])) == len(expected["columns"]), "invalid_expected_columns")
            require(isinstance(expected["rows"], list) and len(expected["rows"]) <= limits["max_rows"]
                    and all(isinstance(row, list) and len(row) == len(expected["columns"]) for row in expected["rows"])
                    and type(expected["truncated"]) is bool, "invalid_expected_rows")
        else:
            require(case["expected"] is None, "refusal_has_no_result")
    require(sum(2 + len(case["reads"]) if "workflow" in case else 1 for case in value["cases"])
            <= limits["max_calls"], "case_count_exceeds_budget")
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        raise LiveRefusal("invalid_json_values") from None
    require(len(encoded.encode()) <= 2097152, "plan_byte_limit")
    return json.loads(encoded)


def describe_plan(plan: dict) -> dict:
    return {"schema_version": 1, "status": "BLOCKED", "execution_enabled": False,
            "reason": "operator_approval_and_artifact_preflight_required", "plan_sha256": digest(plan),
            "run_id": plan["run_id"], "target": plan["target"], "operations": sorted({case.get("operation", "query") for case in plan["cases"]}),
            "limits": plan["limits"], "cases": [case["case_id"] for case in plan["cases"]],
            "data_classification": plan["data_classification"], "retention": plan["retention"],
            "mutations": False, "model_calls": False, "cleanup": "no_remote_state_created"}


def keyed_search_plan(value: dict) -> dict:
    plan = validate_plan(value)
    require(plan["target"]["service"] == "search", "search_observation_required")
    observed = next((case for case in plan["cases"] if case["operation"] == "query"
                     and case["expected_status"] == "success" and case["expected"]["documents"]), None)
    require(observed is not None, "observed_document_required")
    field = plan["target"]["key_field"]
    key = observed["expected"]["documents"][0].get(field)
    require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_=-]{1,1024}", key), "invalid_observed_key")
    common = {"parameters": {}, "projection": observed["projection"], "expected_status": "success", "expected": None}
    plan["run_id"] = plan["run_id"][:58] + "-keyed"
    plan["limits"]["max_calls"] = 3
    plan["cases"] = [
        {**common, "case_id": "LI-SEARCH-OBSERVED-QUERY", "operation": "query", "expression": "*",
         "options": {"count": True, "filter": f"{field} eq '{key}'"}},
        {**common, "case_id": "LI-SEARCH-OBSERVED-READ", "operation": "read", "expression": key, "options": {}},
        {**common, "case_id": "LI-SEARCH-OBSERVED-EMPTY", "operation": "query", "expression": "*",
         "options": {"count": True, "filter": "false"}},
    ]
    return validate_plan(plan, require_oracle=False)


def write_private_plan(path: Path, plan: dict) -> None:
    require(path.is_absolute() and not path.resolve().is_relative_to(ROOT), "private_new_baseline_required")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())


def validate_approval(plan: dict, value: dict | None, *, acknowledged_sha256: str | None,
                      now: datetime | None = None) -> dict:
    conversation = isinstance(value, dict) and type(value.get("schema_version")) is int and value["schema_version"] == 2
    fields(value, {"schema_version", "plan_sha256", "approval_reference", "approved_by", "not_before",
                   "expires_at", "operations", "resource_id", "principal_id"}
           | ({"authority_statement"} if conversation else {"max_cost_usd"}), "operator_approval_required")
    require(type(value["schema_version"]) is int and value["schema_version"] in (1, 2), "invalid_approval_version")
    require(value["plan_sha256"] == digest(plan), "approval_digest_mismatch")
    if conversation:
        require(acknowledged_sha256 is None and value["authority_statement"] == READ_AUTHORITY
                and value["approved_by"] == "conversation-user", "conversation_authority_required")
        require(plan["limits"]["timeout_seconds"] <= 30 and plan["limits"]["max_rows"] <= 100,
                "conversation_limits_exceeded")
    else:
        require(acknowledged_sha256 == digest(value), "approval_digest_mismatch")
        require(positive(value["max_cost_usd"], 100, integer=False), "cost_authorization_required")
    for field in ("approval_reference", "approved_by"):
        require(isinstance(value[field], str) and re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,160}", value[field]), "approval_origin_required")
    require(value["resource_id"] == plan["target"]["resource_id"] and value["principal_id"] == plan["target"]["principal_id"], "approval_target_mismatch")
    operations = sorted({case.get("operation", "query") for case in plan["cases"]})
    require(value["operations"] == operations and set(operations) <= {"query", "read", "schema"}, "only_reads_are_implemented")
    try:
        start = datetime.fromisoformat(value["not_before"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        valid = (start.utcoffset() is not None and end.utcoffset() is not None
                 and start <= current < end and 0 < (end - start).total_seconds() <= 86400)
    except (ValueError, TypeError, AttributeError):
        valid = False
    require(valid, "approval_expired_or_not_active")
    return json.loads(json.dumps(value))


class CallBudget:
    def __init__(self, *, max_calls: int, timeout_seconds: float, clock=time.monotonic) -> None:
        require(positive(max_calls, 100) and positive(timeout_seconds, 600, integer=False), "invalid_limits")
        self.clock, self.maximum = clock, max_calls
        self.deadline = clock() + timeout_seconds
        self.calls = 0

    def reserve(self) -> float:
        remaining = self.remaining()
        require(self.calls < self.maximum, "budget_exhausted")
        self.calls += 1
        return remaining

    def remaining(self) -> float:
        remaining = self.deadline - self.clock()
        require(remaining > 0, "budget_exhausted")
        return remaining


class ReadLedger:
    @staticmethod
    def create(path: Path, continuation: dict) -> None:
        require(not path.exists(), "ledger_collision")
        inherited = continuation.get("call_accounting", {})
        require(inherited.get("executor_ceiling") == 100
                and inherited.get("known_total_attempts") == 26
                and inherited.get("unknown_attempt_operations") == 1
                and inherited.get("reserved_call_slots") == 27, "continuation_baseline_required")
        write_private_plan(path, {"schema_version": 1, "ceiling": 100,
            "inherited": {"known": 26, "unknown": 1, "reserved": 27, "receipt_sha256": digest(continuation)},
            "entries": []})

    def __init__(self, path: Path):
        self.path = Path(path)
        self.snapshot()

    @contextmanager
    def _transaction(self, *, write=False):
        try:
            require(self.path.is_absolute() and not self.path.is_symlink()
                    and not self.path.resolve().is_relative_to(ROOT)
                    and self.path.stat().st_uid == os.getuid()
                    and self.path.stat().st_mode & 0o777 == 0o600
                    and self.path.parent.stat().st_mode & 0o077 == 0, "private_ledger_required")
            descriptor = os.open(str(self.path) + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "r+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                value = load_document(self.path)
                self._validate(value)
                yield value
                if write:
                    self._validate(value)
                    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                                     prefix=".ledger-", delete=False) as staged:
                        json.dump(value, staged, indent=2, allow_nan=False)
                        staged.flush()
                        os.fsync(staged.fileno())
                    os.replace(staged.name, self.path)
                fcntl.flock(lock, fcntl.LOCK_UN)
        except (OSError, TypeError, KeyError):
            raise LiveRefusal("ledger_unavailable_or_locked") from None

    @staticmethod
    def _validate(value):
        require(value.get("schema_version") == 1 and value.get("ceiling") == 100, "invalid_ledger")
        inherited = value.get("inherited", {})
        require(inherited.get("known") == 26 and inherited.get("unknown") == 1
                and inherited.get("reserved") == 27, "continuation_reset_refused")
        require(isinstance(value.get("entries"), list), "invalid_ledger")
        seen, reserved = set(), 27
        for entry in value["entries"]:
            identifier = entry.get("reservation_id")
            require(isinstance(identifier, str) and re.fullmatch(r"[a-f0-9]{32}", identifier)
                    and identifier not in seen and positive(entry.get("maximum"), 73), "invalid_ledger_entry")
            seen.add(identifier)
            require(entry.get("state") in {"reserved", "known", "unknown"}, "invalid_ledger_state")
            attempts = entry.get("attempts")
            require(type(attempts) is int and 0 <= attempts <= entry["maximum"] if entry["state"] == "known"
                    else attempts is None, "invalid_ledger_attempts")
            reserved += attempts if entry["state"] == "known" else entry["maximum"]
        require(reserved <= 100, "ledger_ceiling_exceeded")

    @staticmethod
    def _snapshot(value):
        entries = value["entries"]
        known = 26 + sum(entry["attempts"] for entry in entries if entry["state"] == "known")
        unknown = 1 + sum(entry["state"] == "unknown" for entry in entries)
        reserved = 27 + sum(entry["attempts"] if entry["state"] == "known" else entry["maximum"] for entry in entries)
        return {"ceiling": 100, "known_total_attempts": known, "unknown_attempt_operations": unknown,
                "reserved_call_slots": reserved, "remaining_slots": 100 - reserved,
                "pending_reservations": sum(entry["state"] == "reserved" for entry in entries),
                "cost_usd": None, "cost_reason": "billing_not_observed", "ledger_sha256": digest(value)}

    def snapshot(self):
        with self._transaction() as value:
            return self._snapshot(value)

    def reserve(self, owner: str, maximum: int, binding: dict) -> str:
        require(isinstance(owner, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", owner), "invalid_reservation_owner")
        require(positive(maximum, 73), "invalid_reservation_limit")
        fields(binding, {"plan_sha256", "candidate_sha256", "target_sha256"}, "invalid_reservation_binding")
        require(all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in binding.values()), "invalid_reservation_binding")
        with self._transaction(write=True) as value:
            require(maximum <= self._snapshot(value)["remaining_slots"], "budget_exhausted")
            identifier = uuid.uuid4().hex
            value["entries"].append({"reservation_id": identifier, "owner": owner, "maximum": maximum,
                "binding": dict(binding), "state": "reserved", "attempts": None,
                "reserved_at": datetime.now(timezone.utc).isoformat()})
            return identifier

    def settle(self, identifier: str, attempts: int | None) -> None:
        with self._transaction(write=True) as value:
            entry = next((entry for entry in value["entries"] if entry["reservation_id"] == identifier), None)
            require(entry is not None and entry["state"] == "reserved", "reservation_already_settled_or_missing")
            require(attempts is None or type(attempts) is int and 0 <= attempts <= entry["maximum"], "unreserved_attempts")
            entry.update(state="unknown" if attempts is None else "known", attempts=attempts,
                         settled_at=datetime.now(timezone.utc).isoformat())


def make_baseline_binding(plan: dict, *, captured_at: datetime) -> dict:
    return {"target_sha256": digest(plan["target"]), "artifact_sha256": plan["artifact"]["sha256"],
            "principal_id": plan["target"]["principal_id"], "captured_at": captured_at.isoformat(),
            "inputs_sha256": digest([{name: value for name, value in case.items() if name != "expected"} for case in plan["cases"]]),
            "expected_sha256": digest([case["expected"] for case in plan["cases"]])}


def validate_baseline_binding(plan: dict, binding: dict, *, now: datetime) -> None:
    require(isinstance(binding, dict), "baseline_binding_required")
    try:
        captured = datetime.fromisoformat(binding["captured_at"].replace("Z", "+00:00"))
        require(captured.utcoffset() is not None and 0 <= (now - captured).total_seconds() <= 86400, "baseline_stale")
        require(binding == make_baseline_binding(plan, captured_at=captured), "baseline_binding_mismatch")
    except (KeyError, TypeError, ValueError):
        raise LiveRefusal("baseline_binding_mismatch_or_stale") from None


def verify_artifact(artifact: dict) -> dict:
    try:
        path = Path(artifact["wheel"]).resolve(strict=True)
        require(path.suffix == ".whl" and path.stat().st_size <= 20971520, "wheel_required")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"], "artifact_digest_mismatch")
        distribution = importlib.metadata.distribution(artifact["distribution"])
        require(distribution.version == artifact["version"], "installed_version_mismatch")
        direct = distribution.read_text("direct_url.json")
        require(not direct or not json.loads(direct).get("dir_info", {}).get("editable", False), "editable_artifact_refused")
        with zipfile.ZipFile(path) as wheel:
            members = [name for name in wheel.namelist() if name.startswith("azdata/") and not name.endswith("/")]
            require("azdata/__init__.py" in members, "invalid_wheel")
            for name in members:
                installed = Path(distribution.locate_file(name)).resolve(strict=True)
                require(not installed.is_relative_to(ROOT), "checkout_import_refused")
                require(installed.read_bytes() == wheel.read(name), "installed_bytes_mismatch")
        found = importlib.util.find_spec("azdata")
        require(found is not None and found.origin is not None
                and Path(found.origin).resolve() == Path(distribution.locate_file("azdata/__init__.py")).resolve(), "import_origin_mismatch")
        dependencies = {}
        for name in ("azure-core", "azure-kusto-data", "azure-search-documents", "aiohttp", "azure-identity"):
            try:
                dependencies[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                dependencies[name] = None
        return {"distribution": artifact["distribution"], "version": distribution.version,
                "sha256": artifact["sha256"], "import_origin": found.origin,
                "python": sys.version.split()[0], "platform": sys.platform,
            "dependencies": dependencies}
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, importlib.metadata.PackageNotFoundError):
        raise LiveRefusal("artifact_verification_failed") from None


class Receipt:
    def __init__(self, path: Path, plan: dict) -> None:
        self.path, self.plan = path, plan
        self.handle = None
        self.report = {"schema_version": 1, "run_id": plan["run_id"], "plan_sha256": digest(plan),
                       "target": plan["target"], "artifact": None, "approval_reference": None,
                       "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
                       "mutations": False, "model_calls": False, "fixtures": [],
                       "cleanup": "no_remote_state_created", "cost_usd": None,
                       "cost_unknown_reason": "billing_not_observed", "passed": False,
                       "cases": [{"case_id": case["case_id"], "outcome": "NOT_RUN", "attempts": 0}
                                 for case in plan["cases"]]}
        self._summarize()

    def _summarize(self) -> None:
        self.report["counts"] = {name: sum(case["outcome"] == name for case in self.report["cases"]) for name in OUTCOMES}
        self.report["required"] = len(self.report["cases"])
        self.report["attempted"] = sum(case["outcome"] not in ("BLOCKED", "NOT_RUN") for case in self.report["cases"])
        self.report["passed"] = all(observed["outcome"] == ("PASS_LIVE" if expected["expected_status"] == "success" else "PASS_REFUSAL")
                                    for observed, expected in zip(self.report["cases"], self.plan["cases"]))
        steps = [step for case in self.report["cases"] for step in case.get("steps", [])]
        if steps:
            self.report["workflow_required"] = len(steps)
            self.report["workflow_counts"] = {name: sum(step["outcome"] == name for step in steps) for name in OUTCOMES}

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            self.handle = os.fdopen(descriptor, "w", encoding="utf-8")
        except OSError:
            raise LiveRefusal("receipt_collision_or_unwritable") from None
        self.flush()
        return self

    def flush(self) -> None:
        self._summarize()
        text = json.dumps(self.report, indent=2, allow_nan=False) + "\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".live-receipt-", delete=False) as staged:
                temporary = Path(staged.name)
                staged.write(text)
                staged.flush()
                os.fsync(staged.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _validate_values(self, outcome: str, values: dict) -> None:
        allowed = {"attempts", "attempts_unknown_reason", "row_count", "observed_sha256", "evidence_class", "error_code", "elapsed_ms", "request_id", "result_status", "result_error_code", "exception_type", "steps"}
        require(set(values) <= allowed and outcome in OUTCOMES, "unsafe_report_fields")
        attempts = values.get("attempts", 0)
        known_attempts = type(attempts) is int and 0 <= attempts <= self.plan["limits"]["max_calls"]
        require(known_attempts or attempts is None and outcome == "FAIL"
            and values.get("attempts_unknown_reason") == "interrupted_or_unreported", "invalid_attempts")
        require("attempts_unknown_reason" not in values or attempts is None, "unexpected_unknown_reason")
        evidence = values.get("evidence_class", "offline")
        require(evidence in ("offline", "live", "unknown"), "invalid_evidence_class")
        require(outcome != "PASS_LIVE" or evidence == "live" and known_attempts and attempts > 0, "live_evidence_required")
        require("error_code" not in values or values["error_code"] in ERROR_CODES, "unsafe_error_code")
        require("result_status" not in values or values["result_status"] in
            {"success", "partial", "pending", "unknown", "not_found", "conflict", "invalid", "denied", "unsupported", "failed"}, "unsafe_result_status")
        for name in ("result_error_code", "exception_type"):
            require(name not in values or isinstance(values[name], str)
                and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", values[name]), "unsafe_error_code")
        require("observed_sha256" not in values or isinstance(values["observed_sha256"], str)
                and re.fullmatch(r"[a-f0-9]{64}", values["observed_sha256"]), "invalid_observed_digest")
        for name in ("row_count", "elapsed_ms"):
            if name in values:
                require(type(values[name]) in (int, float) and math.isfinite(values[name]) and values[name] >= 0, "invalid_measurement")
        if "request_id" in values:
            require(isinstance(values["request_id"], str) and re.fullmatch(r"[a-f0-9-]{1,64}", values["request_id"]), "invalid_request_id")

    def record(self, case_id: str, outcome: str, **values) -> None:
        self._validate_values(outcome, values)
        index = next((index for index, case in enumerate(self.report["cases"]) if case["case_id"] == case_id), None)
        require(index is not None and self.report["cases"][index]["outcome"] == "NOT_RUN", "case_already_settled_or_unknown")
        expected = self.plan["cases"][index]
        if "steps" in values:
            require(expected.get("workflow") == "search-citation" and isinstance(values["steps"], list), "unexpected_workflow_steps")
            identifiers = [expected["case_id"], *[read["case_id"] for read in expected["reads"]], expected["missing"]["case_id"]]
            require([step.get("case_id") for step in values["steps"]] == identifiers, "workflow_rows_mismatch")
            for step in values["steps"]:
                require("steps" not in step, "unsafe_report_fields")
                child = dict(step)
                child.pop("case_id")
                self._validate_values(child.pop("outcome"), child)
            require(outcome != "PASS_LIVE" or all(step["outcome"] == "PASS_LIVE" for step in values["steps"]), "workflow_incomplete")
        else:
            require("workflow" not in expected or outcome in {"BLOCKED", "NOT_RUN", "FAIL"}, "workflow_rows_required")
        attempts = values.get("attempts", 0)
        self.report["cases"][index] = {"case_id": case_id, "outcome": outcome, "attempts": attempts, **values}
        self.flush()

    def __exit__(self, *_):
        try:
            self.report["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.flush()
        finally:
            self.handle.close()


def load_document(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        require(path.stat().st_size <= 2097152, "document_byte_limit")
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(LiveRefusal("invalid_json_number")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LiveRefusal("document_unavailable_or_invalid") from None


class IdentityBoundCliCredential:
    def __init__(self, credential, target: dict) -> None:
        self.credential = credential
        self.principal, self.tenant = target["principal_id"], target["tenant_id"]

    def get_token(self, *scopes, **kwargs):
        try:
            token = self.credential.get_token(*scopes, **kwargs)
            parts = token.token.split(".")
            require(len(parts) == 3 and len(parts[1]) <= 65536, "runtime_identity_mismatch")
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            require(claims.get("oid") == self.principal and claims.get("tid") == self.tenant
                    and type(claims.get("exp")) is int and claims["exp"] > time.time(), "runtime_identity_mismatch")
            return token
        except LiveRefusal:
            raise
        except Exception:
            raise LiveRefusal("credential_unavailable") from None

    def close(self):
        self.credential.close()


def operator_credential(target: dict, timeout_seconds: float, *, cli=None, credential_type=None):
    if cli is None:
        if __package__:
            from .resource_group import azure_cli
        else:
            from resource_group import azure_cli
        cli = azure_cli
    if credential_type is None:
        from azure.identity import AzureCliCredential
        credential_type = AzureCliCredential

    deadline = time.monotonic() + timeout_seconds
    account = cli("account", "show", "--query",
                        "{subscription:id,tenant:tenantId,cloud:environmentName,user_type:user.type}",
                        timeout_seconds=max(0.001, deadline - time.monotonic()))
    require(account.get("subscription", "").lower() == target["subscription_id"]
            and account.get("tenant", "").lower() == target["tenant_id"]
            and account.get("cloud") == "AzureCloud" and account.get("user_type") == "user", "runtime_identity_mismatch")
    credential = IdentityBoundCliCredential(credential_type(subscription=target["subscription_id"],
        process_timeout=min(10, max(1, deadline - time.monotonic()))), target)
    try:
        credential.get_token("https://management.azure.com/.default")
        require(deadline > time.monotonic(), "budget_exhausted")
        return credential
    except Exception:
        credential.close()
        raise


def load_case_runner(*, observer: bool = False, service: str = "adx", workflow: str | None = None):
    name = {"adx": "adx_query", "search": "search_read"}[service]
    path = ROOT / f"libraries/azure-data-connectors/tests/live_tests/features/{name}.py"
    spec = importlib.util.spec_from_file_location(f"agentcraft_{name}_live_case", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    if workflow is not None:
        require(service == "search" and workflow == "search-citation" and not observer, "workflow_requires_frozen_feature_observations")
        path = ROOT / "libraries/azure-data-connectors/tests/live_tests/workflows/search_citation.py"
        workflow_spec = importlib.util.spec_from_file_location("agentcraft_search_citation_workflow", path)
        composed = importlib.util.module_from_spec(workflow_spec)
        workflow_spec.loader.exec_module(composed)
        return partial(composed.run, feature=loaded)
    return loaded.observe if observer else loaded.run


def inspect_metadata(target: dict, before_call, *, cli=None) -> dict:
    if cli is None:
        if __package__:
            from .resource_group import azure_cli
        else:
            from resource_group import azure_cli
        cli = azure_cli
    subscription = target["subscription_id"]
    group = target["resource_id"].split("/")[4]
    types = ("Microsoft.Kusto/clusters", "Microsoft.DocumentDB/databaseAccounts", "Microsoft.Search/searchServices",
             "Microsoft.Storage/storageAccounts", "Microsoft.Sql/servers", "Microsoft.DBforPostgreSQL/flexibleServers",
             "Microsoft.Fabric/capacities")
    report = {"inventory_status": "observed", "subscription_id": subscription, "related_resource_group": group,
              "resource_types": list(types), "commands": [], "resources": [], "control_plane_only": True,
              "data_calls": 0, "http_request_count": None, "http_count_unknown_reason": "azure_cli_not_instrumented"}
    allowed_fields = {"id", "name", "type", "kind", "location", "state", "provisioningState", "publicNetworkAccess",
                      "endpoint", "blobEndpoint", "tableEndpoint", "capabilities", "database", "graph", "partitionKey"}

    def validate_metadata(value):
        if isinstance(value, dict):
            require(set(value) <= allowed_fields, "unsafe_metadata_fields")
            for child in value.values():
                validate_metadata(child)
        elif isinstance(value, list):
            require(len(value) <= 100, "metadata_inventory_truncated")
            for child in value:
                validate_metadata(child)
        else:
            require(value is None or type(value) in (str, int, bool), "unsafe_metadata_value")
            if isinstance(value, str):
                require(len(value) <= 2048 and not any(marker in value for marker in
                        ("AccountKey=", "SharedAccessSignature=", "Bearer ")), "unsafe_metadata_value")

    def capture(*arguments):
        entry = {"argv": ["az", *arguments, "--only-show-errors", "--output", "json"],
                 "observed_at": datetime.now(timezone.utc).isoformat()}
        started = time.monotonic()
        try:
            remaining = before_call()
            value = cli(*arguments, timeout_seconds=min(30, remaining))
            validate_metadata(value)
            require(len(json.dumps(value).encode()) <= 1048576, "metadata_byte_limit")
            entry.update(status="observed", result=value)
        except Exception as error:
            entry.update(status="blocked", error_code="metadata_read_failed", exception_type=type(error).__name__)
            report["inventory_status"] = "partial"
            value = None
        entry["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        report["commands"].append(entry)
        return value

    query = "[?" + " || ".join(f"type=='{name}'" for name in types) + "].{id:id,type:type,name:name,location:location,kind:kind} | [0:101]"
    resources = capture("resource", "list", "--subscription", subscription, "--query", query)
    if not isinstance(resources, list):
        return report
    report["resources"] = resources
    for resource in resources:
        identifier = resource.get("id", "")
        prefix = f"/subscriptions/{subscription}/resourceGroups/{group}/providers/"
        if not identifier.lower().startswith(prefix.lower()):
            continue
        name = resource["name"]
        metadata = capture("resource", "show", "--ids", identifier, "--subscription", subscription, "--query",
            "{id:id,name:name,type:type,location:location,state:properties.state,provisioningState:properties.provisioningState,"
            "publicNetworkAccess:properties.publicNetworkAccess,endpoint:properties.uri,blobEndpoint:properties.primaryEndpoints.blob,"
            "tableEndpoint:properties.primaryEndpoints.table,capabilities:properties.capabilities}")
        if resource["type"] == "Microsoft.Kusto/clusters":
            capture("rest", "--method", "get", "--url", f"https://management.azure.com{identifier}/databases?api-version=2024-04-13",
                "--subscription", subscription, "--query", "value[0:101].{id:id,name:name,kind:kind}")
        elif resource["type"] == "Microsoft.DocumentDB/databaseAccounts" and metadata is not None:
            if not any(item.get("name") == "EnableGremlin" for item in metadata.get("capabilities") or []):
                continue
            databases = capture("cosmosdb", "gremlin", "database", "list", "--account-name", name,
                "--resource-group", group, "--subscription", subscription, "--query", "[0:101].{id:id,database:resource.id}")
            for database in databases or []:
                capture("cosmosdb", "gremlin", "graph", "list", "--account-name", name, "--database-name", database["database"],
                    "--resource-group", group, "--subscription", subscription,
                    "--query", "[0:101].{id:id,graph:resource.id,partitionKey:resource.partitionKey.paths}")
        elif resource["type"] == "Microsoft.Storage/storageAccounts" and name in {"staitpipeline01", "stperthpipeline01"}:
            capture("storage", "container-rm", "list", "--storage-account", name, "--resource-group", group,
                "--subscription", subscription, "--query", "[0:101].{id:id,name:name}")
            capture("rest", "--method", "get", "--url", f"https://management.azure.com{identifier}/tableServices/default/tables?api-version=2023-05-01",
                "--subscription", subscription, "--query", "value[0:101].{id:id,name:name}")
    present = capture("group", "exists", "--name", "rg-agentcraft-azdata-live-tests", "--subscription", subscription)
    if present is True:
        capture("resource", "list", "--resource-group", "rg-agentcraft-azdata-live-tests", "--subscription", subscription,
                "--query", "[0:101].{id:id,name:name,type:type}")
    report["cli_commands"] = len(report["commands"])
    return report


async def run_plan(value, approval, *, acknowledged_sha256, report_path,
                   credential_factory=operator_credential, artifact_verifier=verify_artifact,
                   case_runner=None, now=lambda: datetime.now(timezone.utc), baseline_path: Path | None = None,
                   inventory: bool = False, inventory_reader=inspect_metadata, ledger_path: Path | None = None,
                   observed_path: Path | None = None) -> dict:
    observer = baseline_path is not None
    if observed_path is not None:
        require(not observer and not inventory and observed_path.is_absolute()
                and not observed_path.resolve().is_relative_to(ROOT) and not observed_path.exists()
                and observed_path.parent.stat().st_mode & 0o077 == 0, "private_new_observation_required")
    captured_results = {}
    plan = validate_plan(value, require_oracle=not (observer or inventory))
    if observer:
        require(baseline_path.is_absolute() and not baseline_path.resolve().is_relative_to(ROOT)
                and not baseline_path.exists(), "private_new_baseline_required")
    with Receipt(report_path, plan) as receipt:
        receipt.report["evidence_subject"] = "arm-inventory" if inventory else "independent-native-observer" if observer else "installed-public-library"
        credential = None
        ledger = None
        try:
            if ledger_path is not None:
                ledger = ReadLedger(ledger_path)
                require(plan["limits"]["timeout_seconds"] <= 30 and plan["limits"]["max_rows"] <= 100, "conversation_limits_exceeded")
                require(plan["limits"]["max_calls"] <= ledger.snapshot()["remaining_slots"], "budget_exhausted")
                if not observer and not inventory:
                    validate_baseline_binding(plan, plan.get("baseline_binding"), now=now())
            validated = validate_approval(plan, approval, acknowledged_sha256=acknowledged_sha256, now=now())
            require(not inventory or validated["schema_version"] == 2, "conversation_authority_required")
            receipt.report["approval_reference"] = validated["approval_reference"]
            receipt.report["approval_sha256"] = digest(validated)
            if validated["schema_version"] == 2:
                receipt.report["authorization"] = {
                    "origin": "conversation-user", "statement": validated["authority_statement"],
                    "reference": validated["approval_reference"], "recorded_by": "trusted-local-executor",
                    "limits_basis": "executor", "not_before": validated["not_before"],
                    "expires_at": validated["expires_at"], "user_cost_ceiling_usd": None,
                }
            if not inventory:
                receipt.report["artifact"] = artifact_verifier(plan["artifact"])
            require(not observer or not any("workflow" in case for case in plan["cases"]), "workflow_requires_frozen_feature_observations")
            budget = CallBudget(max_calls=40 if inventory else plan["limits"]["max_calls"],
                                timeout_seconds=600 if inventory else plan["limits"]["timeout_seconds"])
            credential = credential_factory(plan["target"], budget.remaining())
            runner = None if inventory else case_runner or load_case_runner(observer=observer, service=plan["target"]["service"])
        except Exception:
            if credential is not None:
                credential.close()
            for case in plan["cases"]:
                receipt.record(case["case_id"], "BLOCKED", error_code="preflight_refused", attempts=0, evidence_class="offline")
            return receipt.report

        reservations = []
        binding = {"plan_sha256": digest(plan), "candidate_sha256": plan["artifact"]["sha256"],
                   "target_sha256": digest(plan["target"])}

        def before_call():
            validate_approval(plan, validated, acknowledged_sha256=acknowledged_sha256, now=now())
            remaining = budget.reserve()
            if ledger is not None:
                reservations.append(ledger.reserve("native" if observer else "library", 1, binding))
            return remaining

        def settle(attempts):
            if ledger is None:
                return
            retained, reservations[:] = list(reservations), []
            valid = type(attempts) is int and 0 <= attempts <= len(retained)
            for position, reservation in enumerate(retained):
                ledger.settle(reservation, int(position < attempts) if valid else None)
            require(attempts is None or valid, "unreserved_attempts")

        try:
            if inventory:
                receipt.report["inventory_limits"] = {"max_cli_commands": 40, "per_command_seconds": 30,
                    "deadline_seconds": 600, "max_records_per_command": 100, "max_output_bytes": 1048576}
                receipt.report.update(inventory_reader(plan["target"], before_call))
                return receipt.report
            if observer:
                receipt.report["observations"] = []
                receipt.report["observer_status"] = "blocked"
                baseline = json.loads(json.dumps(plan))
                for case in baseline["cases"]:
                    try:
                        result = await runner(case, target=plan["target"], limits=plan["limits"],
                                              credential=credential, before_call=before_call)
                        observer_fields = {"expected", "attempts", "request_id", "row_count", "observed_sha256", "elapsed_ms"}
                        fields(result, observer_fields, "unsafe_observer_fields")
                        settle(result["attempts"])
                        case["expected"] = result["expected"]
                        receipt.report["observations"].append({"case_id": case["case_id"],
                            "status": "observed", **{name: result[name] for name in
                            ("attempts", "request_id", "row_count", "observed_sha256", "elapsed_ms")}})
                        receipt.flush()
                    except Exception as error:
                        settle(None)
                        response = getattr(error, "http_response", None)
                        status = getattr(response, "status_code", None)
                        receipt.report["reserved_query_calls"] = budget.calls
                        refusal = str(error) if isinstance(error, LiveRefusal) else None
                        receipt.report["observations"].append({"case_id": case["case_id"], "status": "blocked",
                            "error_code": "native_observer_failed", "attempts": None,
                            "attempts_unknown_reason": "native_sdk_not_instrumented",
                            "exception_type": type(error).__name__,
                            "refusal_code": refusal if refusal in {"approval_expired_or_not_active",
                                "approval_digest_mismatch", "budget_exhausted", "runtime_identity_mismatch",
                                "credential_unavailable"} else None,
                            "http_status": status if type(status) is int and 100 <= status <= 599 else None})
                        return receipt.report
                if ledger is not None:
                    baseline["baseline_binding"] = make_baseline_binding(baseline, captured_at=now())
                baseline = validate_plan(baseline)
                write_private_plan(baseline_path, baseline)
                receipt.report.update(observer_status="observed", baseline_path=str(baseline_path),
                                      baseline_sha256=digest(baseline), native_calls=budget.calls)
                return receipt.report
            for case in plan["cases"]:
                try:
                    selected = (load_case_runner(service=plan["target"]["service"], workflow=case["workflow"])
                                if case.get("workflow") and case_runner is None else runner)
                    arguments = {"target": plan["target"], "limits": plan["limits"], "credential": credential, "before_call": before_call}
                    if observed_path is not None:
                        captured_results[case["case_id"]] = {}
                        arguments["observed_out"] = captured_results[case["case_id"]]
                    result = await selected(case, **arguments)
                    result = dict(result)
                    outcome = result.pop("outcome")
                    settle(result.get("attempts"))
                    receipt.record(case["case_id"], outcome, **result)
                    if outcome not in ("PASS_LIVE", "PASS_REFUSAL"):
                        break
                except asyncio.CancelledError:
                    settle(None)
                    receipt.record(case["case_id"], "FAIL", error_code="case_interrupted", attempts=None,
                                   attempts_unknown_reason="interrupted_or_unreported", evidence_class="unknown")
                    raise
                except Exception as error:
                    settle(None)
                    receipt.record(case["case_id"], "FAIL", error_code="case_failed", attempts=None,
                                   attempts_unknown_reason="interrupted_or_unreported", evidence_class="unknown",
                                   exception_type=type(error).__name__)
                    break
        finally:
            try:
                if ledger is not None:
                    settle(None)
                    receipt.report["call_accounting"] = ledger.snapshot()
                if observed_path is not None:
                    require(len(json.dumps(captured_results, allow_nan=False).encode()) <= 2097152, "observation_byte_limit")
                    write_private_plan(observed_path, captured_results)
                    receipt.report["private_observation"] = {"path": str(observed_path), "sha256": hashlib.sha256(observed_path.read_bytes()).hexdigest()}
            finally:
                credential.close()
    return receipt.report


def reconcile_acceptance(manifest: dict, *, report_path: Path, summary_path: Path) -> dict:
    require(manifest.get("schema_version") == 1 and isinstance(manifest.get("cases"), list), "invalid_case_manifest")
    candidate = manifest.get("candidate_sha256")
    require(isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{64}", candidate), "candidate_identity_required")
    require(report_path.is_absolute() and summary_path.is_absolute() and report_path != summary_path
            and not report_path.exists() and not summary_path.exists(), "receipt_collision_or_unwritable")
    success = {"offline": {"PASS_OFFLINE", "PASS_REFUSAL"}, "artifact": {"PASS_ARTIFACT"},
               "live": {"PASS_LIVE"}, "consumer": {"PASS_LIVE"}, "browser": {"PASS_LIVE"},
               "independent-developer": {"PASS_LIVE"}, "provider-denial": {"PASS_REFUSAL"},
               "local-refusal": {"PASS_REFUSAL"}, "native-observer": {"PASS_OBSERVER"}}
    identifiers, rows = set(), []
    for declared in manifest["cases"]:
        identifier = declared.get("case_id")
        evidence = declared.get("evidence_class")
        require(isinstance(identifier, str) and re.fullmatch(r"SCR-[A-Z][0-9]+[A-Za-z0-9_.-]*", identifier)
                and identifier not in identifiers and evidence in success
                and type(declared.get("required")) is bool, "duplicate_or_invalid_required_case")
        identifiers.add(identifier)
        row = {"case_id": identifier, "family": declared.get("family"), "required": declared["required"],
               "evidence_class": evidence, "outcome": "NOT_RUN", "reason": "evidence_not_returned"}
        if declared.get("receipt") is None:
            if declared.get("blocked_reason"):
                reason = declared["blocked_reason"]
                require(isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,100}", reason), "unsafe_blocked_reason")
                row.update(outcome="BLOCKED", reason=reason)
        else:
            try:
                path = Path(declared["receipt"])
                require(path.is_absolute(), "receipt_absolute_path_required")
                require(hashlib.sha256(path.read_bytes()).hexdigest() == declared.get("receipt_sha256"), "receipt_digest_mismatch")
                receipt = load_document(path)
                require(receipt.get("candidate_sha256") == candidate, "receipt_candidate_mismatch")
                observed_rows = receipt.get("cases", [])
                observed_ids = [item.get("case_id") for item in observed_rows]
                require(len(observed_ids) == len(set(observed_ids)), "duplicate_receipt_rows")
                matched = [item for item in observed_rows if item.get("case_id") == declared.get("receipt_case_id")]
                require(len(matched) == 1, "receipt_case_missing")
                observed = matched[0]
                require(observed.get("evidence_class") == evidence, "receipt_evidence_mismatch")
                outcome = observed.get("outcome")
                require(outcome in success[evidence] | {"FAIL", "BLOCKED", "NOT_RUN"}, "incompatible_evidence_outcome")
                if evidence not in {"offline", "artifact", "local-refusal"} and outcome in success[evidence]:
                    require(type(observed.get("attempts")) is int and observed["attempts"] > 0, "live_attempt_evidence_required")
                row.update(outcome=outcome, reason="matched_receipt", receipt=str(path),
                           receipt_sha256=declared["receipt_sha256"], receipt_case_id=declared["receipt_case_id"])
            except (OSError, ValueError, TypeError, KeyError):
                row.update(outcome="FAIL", reason="receipt_validation_failed")
        rows.append(row)
    outcomes = {"PASS_LIVE", "PASS_REFUSAL", "PASS_OFFLINE", "PASS_ARTIFACT", "PASS_OBSERVER", "FAIL", "BLOCKED", "NOT_RUN"}
    required = [row for row in rows if row["required"]]
    passed = bool(required) and all(row["outcome"] in success[row["evidence_class"]] for row in required)
    counts = {outcome: sum(row["outcome"] == outcome for row in required) for outcome in sorted(outcomes)}
    report = {"schema_version": 1, "candidate_sha256": candidate, "manifest_sha256": digest(manifest),
              "required": len(required), "attempted": sum(row["outcome"] not in {"BLOCKED", "NOT_RUN"} for row in required),
              "completed": sum(row["outcome"] not in {"BLOCKED", "NOT_RUN"} for row in required),
              "counts": counts, "cases": rows, "passed": passed, "exit_code": 0 if passed else 2,
              "service_calls": 0, "credential_calls": 0, "model_calls": False, "mutations": False,
              "cleanup": "no_remote_state_created", "cost_usd": None,
              "observed_at": datetime.now(timezone.utc).isoformat()}
    if manifest.get("ledger"):
        report["call_accounting"] = ReadLedger(Path(manifest["ledger"])).snapshot()
    summary = "# Search And Catalogue Read Acceptance\n\n"
    summary += f"Status: {'PASS' if passed else 'INCOMPLETE'}. Required: {len(required)}. Exit: {report['exit_code']}.\n\n"
    summary += "| Case | Evidence | Outcome | Reason |\n| --- | --- | --- | --- |\n"
    summary += "".join(f"| {row['case_id']} | {row['evidence_class']} | {row['outcome']} | {row['reason']} |\n" for row in rows)
    summary += "\nLocal reconciliation makes no service or credential calls. No remote state created; no teardown proof. Parent programme remains open.\n"
    for path, text in ((report_path, json.dumps(report, indent=2, allow_nan=False) + "\n"), (summary_path, summary)):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, observe or run approved ADX/Search reads; no provisioning, writes or model calls.")
    parser.add_argument("action", choices=("plan", "derive-search-reads", "inventory", "observe", "run", "reconcile",
                                          "ledger-init", "ledger-status", "ledger-reserve", "ledger-settle"))
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--require-ledger", action="store_true", help="Require a shared continuation ledger before live reads.")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--maximum", type=int)
    parser.add_argument("--binding", help="Payload-free plan/candidate/target digest object.")
    parser.add_argument("--reservation")
    parser.add_argument("--attempts", help="Exact integer, or unknown; never a guessed zero.")
    authority = parser.add_mutually_exclusive_group()
    authority.add_argument("--approval", type=Path)
    authority.add_argument("--conversation-statement", help="Exact genuine user statement; trusted local operator only.")
    parser.add_argument("--conversation-reference", help="Conversation provenance, not a generated human signature.")
    parser.add_argument("--plan-sha256", help="Freeze the target-bound plan for conversation-authorized execution.")
    parser.add_argument("--not-before", help="Executor-selected UTC interval start, required with conversation authority.")
    parser.add_argument("--expires-at", help="Executor-selected UTC expiry; not a user-stated spend limit.")
    parser.add_argument("--approval-sha256")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline-out", type=Path, help="New private file outside the checkout for independent native observations.")
    parser.add_argument("--observed-out", type=Path, help="New private raw candidate output; never a native baseline.")
    options = parser.parse_args()
    try:
        if options.action.startswith("ledger-"):
            require(options.ledger is not None, "ledger_path_required")
            if options.action == "ledger-init":
                require(options.plan_file is not None, "continuation_receipt_required")
                ReadLedger.create(options.ledger, load_document(options.plan_file))
            ledger = ReadLedger(options.ledger)
            if options.action == "ledger-reserve":
                reservation = ledger.reserve(options.owner, options.maximum, json.loads(options.binding))
                print(json.dumps({"reservation_id": reservation, **ledger.snapshot()}))
                return 0
            if options.action == "ledger-settle":
                ledger.settle(options.reservation, None if options.attempts == "unknown" else int(options.attempts))
            print(json.dumps(ledger.snapshot()))
            return 0
        require(options.plan_file is not None, "plan_file_required")
        if options.action == "reconcile":
            require(options.report is not None and options.summary is not None, "report_and_summary_required")
            report = reconcile_acceptance(load_document(options.plan_file), report_path=options.report, summary_path=options.summary)
            print(json.dumps({name: value for name, value in report.items() if name != "cases"}, indent=2))
            return report["exit_code"]
        plan = validate_plan(load_document(options.plan_file), require_oracle=options.action == "run")
        if options.action == "plan":
            print(json.dumps(describe_plan(plan), indent=2))
            return 0
        if options.action == "derive-search-reads":
            require(options.baseline_out is not None, "private_new_baseline_required")
            derived = keyed_search_plan(plan)
            write_private_plan(options.baseline_out, derived)
            print(json.dumps({**describe_plan(derived), "source_plan_sha256": digest(plan),
                              "derived_plan_path": str(options.baseline_out), "live_calls": 0}, indent=2))
            return 0
        require(options.report is not None, "report_path_required")
        if options.require_ledger:
            require(options.ledger is not None, "continuation_ledger_required")
        require((options.baseline_out is not None) == (options.action == "observe"), "baseline_only_for_observe")
        approval = None
        if options.approval is not None:
            approval_path = options.approval.resolve(strict=True)
            require(not approval_path.is_relative_to(ROOT), "approval_must_be_operator_owned_outside_checkout")
            require(approval_path.is_file() and approval_path.stat().st_uid == os.getuid()
                    and approval_path.stat().st_mode & 0o022 == 0, "unsafe_approval_file")
            approval = load_document(approval_path)
            require(approval.get("schema_version") == 1, "external_approval_version_required")
        elif options.conversation_statement is not None:
            approval = {
                "schema_version": 2, "plan_sha256": options.plan_sha256,
                "approval_reference": options.conversation_reference, "approved_by": "conversation-user",
                "authority_statement": options.conversation_statement,
                "not_before": options.not_before, "expires_at": options.expires_at,
                "operations": sorted({case.get("operation", "query") for case in plan["cases"]}),
                "resource_id": plan["target"]["resource_id"],
                "principal_id": plan["target"]["principal_id"],
            }
        report = asyncio.run(run_plan(plan, approval, acknowledged_sha256=options.approval_sha256,
                                      report_path=options.report, baseline_path=options.baseline_out,
                                      inventory=options.action == "inventory", ledger_path=options.ledger, observed_path=options.observed_out))
        print(json.dumps(report, indent=2))
        return 0 if report.get("observer_status") == "observed" or report.get("inventory_status") == "observed" or report["passed"] else 2
    except LiveRefusal as error:
        print(json.dumps({"status": "BLOCKED", "error_code": str(error), "live_calls": 0}), file=sys.stderr)
        return 2
    except (OSError, TypeError, ValueError):
        print(json.dumps({"status": "BLOCKED", "error_code": "invalid_input_or_path", "live_calls": 0}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())