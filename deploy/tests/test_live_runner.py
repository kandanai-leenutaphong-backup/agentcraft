import copy
import asyncio
import base64
import hashlib
import importlib.util
import json
import sys
import tempfile
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


spec = importlib.util.spec_from_file_location("live_runner", Path(__file__).resolve().parents[1] / "live.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)
SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
TENANT = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"


def plan_value():
    return {
        "schema_version": 1,
        "run_id": "adx-fixture-run",
        "target": {
            "service": "adx", "subscription_id": SUBSCRIPTION, "tenant_id": TENANT,
            "principal_id": PRINCIPAL,
            "resource_id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture/providers/Microsoft.Kusto/clusters/fixture/databases/Fixture",
            "endpoint": "https://fixture.australiaeast.kusto.windows.net", "database": "Fixture",
        },
        "artifact": {"distribution": "azdata", "version": "4.0.0a3", "wheel": "/tmp/fixture.whl", "sha256": "a" * 64},
        "limits": {"max_calls": 2, "timeout_seconds": 30, "max_rows": 20, "max_output_bytes": 65536},
        "data_classification": "synthetic",
        "retention": "receipt-only",
        "cases": [
            {"case_id": "LI-ADX-01", "expression": "print value=1", "parameters": {},
             "expected_status": "success", "expected": {"columns": ["value"], "rows": [[1]], "truncated": False}},
            {"case_id": "LI-ADX-02", "expression": "print value=1 | where false", "parameters": {},
             "expected_status": "success", "expected": {"columns": ["value"], "rows": [], "truncated": False}},
        ],
    }


def approval_value(plan):
    return {"schema_version": 1, "plan_sha256": module.digest(plan),
            "approval_reference": "operator-reviewed-fixture", "approved_by": "fixture-operator",
            "not_before": (NOW - timedelta(minutes=1)).isoformat(),
            "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
            "operations": ["query"], "max_cost_usd": 1.0,
            "resource_id": plan["target"]["resource_id"], "principal_id": PRINCIPAL}


def conversation_value(plan):
    approval = approval_value(plan)
    approval.pop("max_cost_usd")
    approval.update(schema_version=2, approved_by="conversation-user",
                    authority_statement="Live testing authorized against all existing deployed data sou4ces on Azure. Proceed.")
    return approval


class LiveCliLedgerTests(unittest.TestCase):
    def test_required_ledger_refuses_before_live_runner(self):
        for action in ("inventory", "observe", "run"):
            arguments = ["live.py", action, "--plan-file", "/tmp/plan.json",
                         "--report", "/tmp/receipt.json", "--require-ledger"]
            with self.subTest(action=action), patch.object(sys, "argv", arguments), \
                 patch.object(module, "load_document", return_value=plan_value()), \
                 patch.object(module, "run_plan", new_callable=AsyncMock) as runner, \
                 redirect_stderr(StringIO()) as error:
                self.assertEqual(module.main(), 2)
                self.assertEqual(json.loads(error.getvalue()), {
                    "status": "BLOCKED", "error_code": "continuation_ledger_required", "live_calls": 0})
                runner.assert_not_called()

    def test_explicit_ledger_and_standalone_reads_reach_live_runner(self):
        for required, ledger in ((False, None), (False, "/tmp/ledger.json"), (True, "/tmp/ledger.json")):
            arguments = ["live.py", "run", "--plan-file", "/tmp/plan.json", "--report", "/tmp/receipt.json"]
            if required:
                arguments.append("--require-ledger")
            if ledger is not None:
                arguments.extend(("--ledger", ledger))
            with self.subTest(required=required, ledger=ledger), patch.object(sys, "argv", arguments), \
                 patch.object(module, "load_document", return_value=plan_value()), \
                 patch.object(module, "run_plan", new_callable=AsyncMock, return_value={"passed": True}) as runner, \
                 redirect_stdout(StringIO()):
                self.assertEqual(module.main(), 0)
                runner.assert_awaited_once()
                self.assertEqual(runner.call_args.kwargs["ledger_path"], Path(ledger) if ledger else None)

    def test_offline_plan_needs_no_ledger(self):
        arguments = ["live.py", "plan", "--plan-file", "/tmp/plan.json", "--require-ledger"]
        with patch.object(sys, "argv", arguments), \
             patch.object(module, "load_document", return_value=plan_value()), \
             patch.object(module, "run_plan", new_callable=AsyncMock) as runner, \
             redirect_stdout(StringIO()):
            self.assertEqual(module.main(), 0)
            runner.assert_not_called()


class ContinuationLedgerTests(unittest.TestCase):
    def create(self, root):
        continuation = {"call_accounting": {"executor_ceiling": 100, "known_total_attempts": 26,
                        "unknown_attempt_operations": 1, "reserved_call_slots": 27}}
        path = Path(root) / "ledger.json"
        module.ReadLedger.create(path, continuation)
        return path, module.ReadLedger(path)

    def binding(self, plan="a"):
        return {"plan_sha256": plan * 64, "candidate_sha256": "b" * 64, "target_sha256": "c" * 64}

    def test_inherited_unknown_and_every_reopened_plan_share_one_ceiling(self):
        with tempfile.TemporaryDirectory() as root:
            path, ledger = self.create(root)
            self.assertEqual(ledger.snapshot()["reserved_call_slots"], 27)
            first = ledger.reserve("native", 4, self.binding())
            module.ReadLedger(path).settle(first, 2)
            second = module.ReadLedger(path).reserve("consumer", 3, self.binding("d"))
            module.ReadLedger(path).settle(second, None)
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot["known_total_attempts"], 28)
            self.assertEqual(snapshot["unknown_attempt_operations"], 2)
            self.assertEqual(snapshot["reserved_call_slots"], 32)
            self.assertEqual(snapshot["remaining_slots"], 68)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIsNone(snapshot["cost_usd"])

    def test_exhausted_or_unsettled_reservations_cannot_reset_or_replay(self):
        with tempfile.TemporaryDirectory() as root:
            path, ledger = self.create(root)
            reservation = ledger.reserve("browser", 73, self.binding())
            with self.assertRaises(module.LiveRefusal):
                module.ReadLedger(path).reserve("different-plan", 1, self.binding("d"))
            self.assertEqual(module.ReadLedger(path).snapshot()["remaining_slots"], 0)
            with self.assertRaises(module.LiveRefusal):
                module.ReadLedger.create(path, {})
            with self.assertRaises(module.LiveRefusal):
                ledger.settle(reservation, 74)
            ledger.settle(reservation, None)
            with self.assertRaises(module.LiveRefusal):
                ledger.settle(reservation, 0)
            self.assertEqual(ledger.snapshot()["reserved_call_slots"], 100)

    def test_pending_developer_reservation_is_not_a_claimed_unknown_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            _, ledger = self.create(root)
            ledger.reserve("independent-developer", 3, self.binding())
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot["reserved_call_slots"], 30)
            self.assertEqual(snapshot["unknown_attempt_operations"], 1)
            self.assertEqual(snapshot["pending_reservations"], 1)

    def test_missing_or_unsafe_ledger_refuses_without_factories(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "missing.json"
            with self.assertRaises(module.LiveRefusal):
                module.ReadLedger(missing)
            path, _ = self.create(root)
            os.chmod(path, 0o644)
            with self.assertRaises(module.LiveRefusal):
                module.ReadLedger(path)

    def test_baseline_binding_rejects_target_artifact_principal_drift_and_staleness(self):
        plan = plan_value()
        binding = module.make_baseline_binding(plan, captured_at=NOW)
        module.validate_baseline_binding(plan, binding, now=NOW)
        for change in ({"artifact_sha256": "d" * 64}, {"principal_id": TENANT},
                       {"target_sha256": "e" * 64}, {"expected_sha256": "f" * 64},
                       {"captured_at": (NOW - timedelta(days=2)).isoformat()}):
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_baseline_binding(plan, {**binding, **change}, now=NOW)

    def test_live_plan_with_missing_ledger_refuses_before_artifact_or_credentials(self):
        touched = []
        with tempfile.TemporaryDirectory() as root:
            report = asyncio.run(module.run_plan(plan_value(), conversation_value(plan_value()), acknowledged_sha256=None,
                report_path=Path(root) / "receipt.json", ledger_path=Path(root) / "missing.json",
                artifact_verifier=lambda *_: touched.append("artifact"), credential_factory=lambda *_: touched.append("credential"),
                now=lambda: NOW))
        self.assertEqual(touched, [])
        self.assertEqual(report["counts"]["BLOCKED"], 2)

    def test_native_library_attempts_settle_the_same_persistent_ledger(self):
        plan = plan_value()
        plan["baseline_binding"] = module.make_baseline_binding(plan, captured_at=NOW)
        touched = []

        async def runner(case, **kwargs):
            kwargs["before_call"]()
            touched.append(case["case_id"])
            if case["case_id"].endswith("02"):
                raise RuntimeError("unknown delivery")
            return {"outcome": "PASS_LIVE", "attempts": 1, "evidence_class": "live"}

        with tempfile.TemporaryDirectory() as root:
            path, ledger = self.create(root)
            report = asyncio.run(module.run_plan(plan, conversation_value(plan), acknowledged_sha256=None,
                report_path=Path(root) / "receipt.json", ledger_path=path,
                artifact_verifier=lambda *_: {}, credential_factory=lambda *_: SimpleNamespace(close=lambda: None),
                case_runner=runner, now=lambda: NOW))
            self.assertEqual(ledger.snapshot()["reserved_call_slots"], 29)
            self.assertEqual(ledger.snapshot()["known_total_attempts"], 27)
            self.assertEqual(ledger.snapshot()["unknown_attempt_operations"], 2)
            self.assertEqual(report["call_accounting"], ledger.snapshot())
        self.assertEqual(len(touched), 2)
        self.assertFalse(report["passed"])

    def test_stale_bound_plan_refuses_before_artifact_and_credential_factories(self):
        plan = plan_value()
        plan["baseline_binding"] = module.make_baseline_binding(plan, captured_at=NOW - timedelta(days=2))
        touched = []
        with tempfile.TemporaryDirectory() as root:
            path, ledger = self.create(root)
            report = asyncio.run(module.run_plan(plan, conversation_value(plan), acknowledged_sha256=None,
                report_path=Path(root) / "receipt.json", ledger_path=path,
                artifact_verifier=lambda *_: touched.append("artifact"), credential_factory=lambda *_: touched.append("credential"),
                now=lambda: NOW))
            self.assertEqual(ledger.snapshot()["reserved_call_slots"], 27)
        self.assertEqual(touched, [])
        self.assertEqual(report["counts"]["BLOCKED"], 2)


class LocalAcceptanceReconciliationTests(unittest.TestCase):
    def test_native_observer_evidence_is_not_library_execution(self):
        with tempfile.TemporaryDirectory() as root:
            manifest, receipt = self.fixture(root)
            value = {"candidate_sha256": "a" * 64, "cases": [
                {"case_id": "offline-1", "outcome": "PASS_OBSERVER", "evidence_class": "native-observer", "attempts": 1}]}
            receipt.write_text(json.dumps(value))
            manifest["cases"][0].update(evidence_class="native-observer", receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
            report = module.reconcile_acceptance(manifest, report_path=Path(root) / "r.json", summary_path=Path(root) / "s.md")
            self.assertEqual(report["counts"]["PASS_OBSERVER"], 1)
            self.assertEqual(report["counts"]["PASS_LIVE"], 0)
            self.assertFalse(report["passed"])

    def fixture(self, root):
        receipt = Path(root) / "evidence.json"
        value = {"candidate_sha256": "a" * 64, "cases": [
            {"case_id": "offline-1", "outcome": "PASS_OFFLINE", "evidence_class": "offline"}]}
        receipt.write_text(json.dumps(value))
        manifest = {"schema_version": 1, "candidate_sha256": "a" * 64, "cases": [
            {"case_id": "SCR-O1-fixture", "family": "SCR-O1", "evidence_class": "offline", "required": True,
             "receipt": str(receipt), "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(), "receipt_case_id": "offline-1"},
            {"case_id": "SCR-A2-developer", "family": "SCR-A2", "evidence_class": "independent-developer", "required": True,
             "receipt": None, "receipt_sha256": None, "receipt_case_id": None, "blocked_reason": "independent_evidence_missing"}]}
        return manifest, receipt

    def test_local_reconciliation_keeps_required_blocked_denominator_and_is_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            manifest, _ = self.fixture(root)
            report = module.reconcile_acceptance(manifest, report_path=Path(root) / "report.json", summary_path=Path(root) / "summary.md")
            self.assertEqual(report["required"], 2)
            self.assertEqual(report["counts"]["PASS_OFFLINE"], 1)
            self.assertEqual(report["counts"]["BLOCKED"], 1)
            self.assertFalse(report["passed"])
            self.assertEqual(report["exit_code"], 2)
            self.assertEqual(report["service_calls"], 0)
            self.assertTrue((Path(root) / "summary.md").exists())

    def test_duplicate_missing_mismatched_or_wrong_evidence_never_passes(self):
        for change in ("duplicate", "missing", "class", "digest", "candidate"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                manifest, receipt = self.fixture(root)
                if change == "duplicate":
                    manifest["cases"].append(copy.deepcopy(manifest["cases"][0]))
                elif change == "missing":
                    manifest["cases"][0]["receipt_case_id"] = "missing-row"
                elif change == "class":
                    manifest["cases"][0]["evidence_class"] = "live"
                elif change == "digest":
                    manifest["cases"][0]["receipt_sha256"] = "f" * 64
                else:
                    manifest["candidate_sha256"] = "b" * 64
                if change == "duplicate":
                    with self.assertRaises(module.LiveRefusal):
                        module.reconcile_acceptance(manifest, report_path=Path(root) / "r.json", summary_path=Path(root) / "s.md")
                else:
                    report = module.reconcile_acceptance(manifest, report_path=Path(root) / "r.json", summary_path=Path(root) / "s.md")
                    self.assertEqual(report["cases"][0]["outcome"], "FAIL")
                    self.assertEqual(report["required"], 2)

    def test_output_collision_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            manifest, _ = self.fixture(root)
            path = Path(root) / "r.json"
            path.write_text("existing")
            with self.assertRaises(module.LiveRefusal):
                module.reconcile_acceptance(manifest, report_path=path, summary_path=Path(root) / "s.md")
            self.assertEqual(path.read_text(), "existing")


class LiveRunnerTests(unittest.TestCase):
    def test_search_only_artifact_does_not_require_optional_kusto_distribution(self):
        import zipfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            package = root / "site/azdata"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("fixture = True\n")
            wheel = root / "azdata.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("azdata/__init__.py", (package / "__init__.py").read_bytes())
            distribution = SimpleNamespace(version="4.0.0a3", read_text=lambda *_: None,
                                            locate_file=lambda name: root / "site" / name)
            def version(name):
                if name == "azure-kusto-data":
                    raise module.importlib.metadata.PackageNotFoundError(name)
                return "fixture"
            with patch.object(module.importlib.metadata, "distribution", return_value=distribution), \
                 patch.object(module.importlib.metadata, "version", side_effect=version), \
                 patch.object(module.importlib.util, "find_spec", return_value=SimpleNamespace(origin=str(package / "__init__.py"))):
                report = module.verify_artifact({"distribution": "azdata", "version": "4.0.0a3", "wheel": str(wheel),
                                               "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()})
            self.assertIsNone(report["dependencies"]["azure-kusto-data"])
            self.assertEqual(report["dependencies"]["azure-search-documents"], "fixture")

    def test_candidate_raw_observation_is_private_not_in_receipt_and_collision_refuses(self):
        plan = plan_value()

        async def run(case, **kwargs):
            kwargs["before_call"]()
            kwargs["observed_out"].update({"rows": [["private-fixture"]]})
            return {"outcome": "PASS_LIVE", "attempts": 1, "evidence_class": "live"}

        with tempfile.TemporaryDirectory() as root:
            observed = Path(root) / "observed.json"
            report = asyncio.run(module.run_plan(plan, conversation_value(plan), acknowledged_sha256=None,
                report_path=Path(root) / "receipt.json", observed_path=observed, now=lambda: NOW,
                credential_factory=lambda *_: SimpleNamespace(close=lambda: None), artifact_verifier=lambda *_: {}, case_runner=run))
            self.assertNotIn("private-fixture", json.dumps(report))
            self.assertIn("private-fixture", observed.read_text())
            self.assertEqual(observed.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(module.LiveRefusal):
                asyncio.run(module.run_plan(plan, conversation_value(plan), acknowledged_sha256=None,
                    report_path=Path(root) / "second.json", observed_path=observed,
                    credential_factory=lambda *_: self.fail("collision reached credential")))

    def test_search_citation_dispatch_and_nested_case_validation(self):
        plan = plan_value()
        plan["target"] = {"service": "search", "subscription_id": SUBSCRIPTION, "tenant_id": TENANT,
            "principal_id": PRINCIPAL, "resource_id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture/providers/Microsoft.Search/searchServices/fixture",
            "endpoint": "https://fixture.search.windows.net", "index": "fixture", "key_field": "id"}
        common = {"operation": "read", "expression": "one", "parameters": {}, "projection": [],
                  "options": {}, "expected_status": "success"}
        expected = {"documents": [{"id": "one"}], "metadata": {}, "truncated": False}
        plan["limits"]["max_calls"] = 3
        plan["cases"] = [{**common, "case_id": "LI-SEARCH-WORKFLOW", "operation": "query", "expression": "*",
            "expected": expected, "workflow": "search-citation",
            "reads": [{**common, "case_id": "LI-SEARCH-READ", "expected": expected}],
            "missing": {**common, "case_id": "LI-SEARCH-MISSING", "expression": "missing",
                        "expected": {"documents": [], "metadata": {}, "truncated": False}}}]
        self.assertEqual(module.validate_plan(plan), plan)
        runner = module.load_case_runner(service="search", workflow="search-citation")
        self.assertTrue(callable(runner))
        for change in ("missing_oracle", "wrong_key", "budget", "mutation"):
            changed = copy.deepcopy(plan)
            if change == "missing_oracle":
                changed["cases"][0]["reads"][0]["expected"] = None
            elif change == "wrong_key":
                changed["cases"][0]["reads"][0]["expression"] = "other"
            elif change == "budget":
                changed["limits"]["max_calls"] = 2
            else:
                changed["cases"][0]["reads"][0]["operation"] = "delete"
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_plan(changed)

    def test_inventory_is_control_plane_only_and_redacts_unrequested_fields(self):
        target = plan_value()["target"]
        calls = []

        def cli(*arguments, **kwargs):
            calls.append(arguments)
            if arguments[:2] == ("resource", "list"):
                return [{"id": target["resource_id"].split("/databases/")[0], "name": "fixture",
                         "type": "Microsoft.Kusto/clusters", "location": "fixture", "kind": None}]
            if arguments[:2] == ("resource", "show"):
                return {"accessToken": "private-payload"}
            if arguments[0] == "rest":
                self.assertIn("get", arguments)
                return []
            return False

        report = module.inspect_metadata(target, lambda: 10, cli=cli)
        self.assertEqual(report["inventory_status"], "partial")
        self.assertEqual(report["data_calls"], 0)
        self.assertNotIn("private-payload", json.dumps(report))
        self.assertFalse(any(word in command for command in calls for word in ("listKeys", "create", "delete", "start", "stop")))

    def test_inventory_cannot_claim_library_credit_or_use_external_exact_target_approval(self):
        plan = plan_value()
        approval = conversation_value(plan)

        def observe(target, before_call):
            before_call()
            return {"inventory_status": "observed", "data_calls": 0, "cli_commands": 1}

        with tempfile.TemporaryDirectory() as temporary:
            report = asyncio.run(module.run_plan(plan, approval, acknowledged_sha256=None,
                report_path=Path(temporary) / "inventory.json", inventory=True, inventory_reader=observe,
                credential_factory=lambda *_: SimpleNamespace(close=lambda: None),
                artifact_verifier=lambda *_: self.fail("inventory is not artifact execution"), now=lambda: NOW))
        self.assertEqual(report["evidence_subject"], "arm-inventory")
        self.assertEqual(report["counts"]["PASS_LIVE"], 0)
        self.assertIsNone(report["artifact"])

    def test_keyed_search_plan_uses_observed_identity_and_requires_fresh_oracles(self):
        plan = plan_value()
        plan["target"] = {"service": "search", "subscription_id": SUBSCRIPTION, "tenant_id": TENANT,
            "principal_id": PRINCIPAL, "resource_id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture/providers/Microsoft.Search/searchServices/fixture",
            "endpoint": "https://fixture.search.windows.net", "index": "fixture", "key_field": "id"}
        plan["cases"] = [{"case_id": "LI-SEARCH-DISCOVERY", "operation": "query", "expression": "*",
            "parameters": {}, "projection": ["id"], "options": {"count": True}, "expected_status": "success",
            "expected": {"documents": [{"id": "observed-key"}], "metadata": {"count": 1}, "truncated": False}}]
        derived = module.keyed_search_plan(plan)
        self.assertEqual(derived["cases"][0]["options"]["filter"], "id eq 'observed-key'")
        self.assertEqual(derived["cases"][1]["expression"], "observed-key")
        self.assertEqual(derived["target"], plan["target"])
        self.assertTrue(all(case["expected"] is None for case in derived["cases"]))
        self.assertNotIn("observed-key", json.dumps(module.describe_plan(derived)))
        with self.assertRaises(module.LiveRefusal):
            module.validate_plan(derived)
        plan["cases"][0]["expected"]["documents"] = []
        with self.assertRaises(module.LiveRefusal):
            module.keyed_search_plan(plan)

    def test_search_scope_accepts_only_bound_index_reads_without_model_options(self):
        plan = plan_value()
        plan["target"] = {"service": "search", "subscription_id": SUBSCRIPTION, "tenant_id": TENANT,
            "principal_id": PRINCIPAL, "resource_id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/fixture/providers/Microsoft.Search/searchServices/fixture",
            "endpoint": "https://fixture.search.windows.net", "index": "fixture-index", "key_field": "id"}
        plan["cases"] = [{"case_id": "LI-SEARCH-01", "operation": "query", "expression": "*", "parameters": {},
            "projection": ["id"], "options": {"count": True}, "expected_status": "success",
            "expected": {"documents": [{"id": "fixture"}], "metadata": {"count": 1}, "truncated": False}}]
        self.assertEqual(module.validate_plan(plan)["target"]["index"], "fixture-index")
        for change in ({"operation": "delete"}, {"options": {"queryType": "semantic"}},
                       {"options": {"vectorQueries": []}}, {"projection": ["credential/value"]}):
            modified = copy.deepcopy(plan)
            modified["cases"][0].update(change)
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_plan(modified)
        changed = copy.deepcopy(plan)
        changed["target"]["index"] = "other-index"
        approval = conversation_value(plan)
        with self.assertRaises(module.LiveRefusal):
            module.validate_approval(changed, approval, acknowledged_sha256=None, now=NOW)

    def test_native_observer_failure_retains_type_not_provider_payload(self):
        plan = plan_value()
        approval = conversation_value(plan)

        async def observe(case, **kwargs):
            kwargs["before_call"]()
            raise RuntimeError("private provider payload")

        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            report = asyncio.run(module.run_plan(plan, approval, acknowledged_sha256=None,
                report_path=Path(temporary) / "observer.json", baseline_path=baseline,
                credential_factory=lambda *_: SimpleNamespace(close=lambda: None),
                artifact_verifier=lambda *_: {}, case_runner=observe, now=lambda: NOW))
            self.assertFalse(baseline.exists())
        self.assertEqual(report["observer_status"], "blocked")
        self.assertEqual(report["observations"][0]["exception_type"], "RuntimeError")
        self.assertEqual(report["reserved_query_calls"], 1)
        self.assertNotIn("private provider payload", json.dumps(report))

    def test_native_observer_freezes_private_expectations_without_library_credit(self):
        plan = plan_value()
        expected = {case["case_id"]: case["expected"] for case in plan["cases"]}
        for case in plan["cases"]:
            case["expected"] = None
        approval = conversation_value(plan)

        async def observe(case, **kwargs):
            kwargs["before_call"]()
            value = expected[case["case_id"]]
            return {"expected": value, "attempts": 1, "request_id": "a" * 32,
                    "row_count": len(value["rows"]), "observed_sha256": module.digest(value), "elapsed_ms": 1}

        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            report = asyncio.run(module.run_plan(plan, approval, acknowledged_sha256=None,
                report_path=Path(temporary) / "observer.json", baseline_path=baseline,
                credential_factory=lambda *_: SimpleNamespace(close=lambda: None),
                artifact_verifier=lambda *_: {}, case_runner=observe, now=lambda: NOW))
            frozen = module.validate_plan(json.loads(baseline.read_text()))
            self.assertEqual(frozen["cases"][0]["expected"], expected["LI-ADX-01"])
            self.assertEqual(report["baseline_sha256"], module.digest(frozen))
            self.assertEqual(baseline.stat().st_mode & 0o777, 0o600)
        self.assertEqual(report["observer_status"], "observed")
        self.assertEqual(report["evidence_subject"], "independent-native-observer")
        self.assertEqual(report["native_calls"], 2)
        self.assertEqual(report["counts"]["PASS_LIVE"], 0)
        self.assertEqual(report["counts"]["NOT_RUN"], 2)
        self.assertNotIn("rows", json.dumps(report))
        self.assertFalse(report["passed"])

    def test_operator_credential_uses_verified_subscription_and_pins_token_identity(self):
        observed = []
        claims = {"oid": PRINCIPAL, "tid": TENANT, "exp": 2**31}

        class Credential:
            def __init__(self, **kwargs):
                observed.append(kwargs)

            def get_token(self, *scopes, **kwargs):
                payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
                return SimpleNamespace(token=f"fixture.{payload}.fixture", expires_on=2**31)

            def close(self):
                observed.append("closed")

        def cli(*arguments, **kwargs):
            self.assertEqual(arguments[:2], ("account", "show"))
            return {"subscription": SUBSCRIPTION, "tenant": TENANT, "cloud": "AzureCloud", "user_type": "user"}

        credential = module.operator_credential(plan_value()["target"], 30, cli=cli, credential_type=Credential)
        self.assertEqual(observed[0]["subscription"], SUBSCRIPTION)
        self.assertNotIn("tenant_id", observed[0])
        credential.get_token("https://search.azure.com/.default")
        for invalid in ({"oid": TENANT}, {"tid": PRINCIPAL}, {"exp": 1}):
            saved = dict(claims)
            claims.update(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(module.LiveRefusal):
                credential.get_token("https://search.azure.com/.default")
            claims.clear()
            claims.update(saved)
        credential.close()
        self.assertEqual(observed[-1], "closed")

    def test_wrong_active_account_refuses_before_credential_construction(self):
        touched = []
        with self.assertRaises(module.LiveRefusal):
            module.operator_credential(plan_value()["target"], 30,
                cli=lambda *args, **kwargs: {"subscription": TENANT, "tenant": TENANT, "cloud": "AzureCloud", "user_type": "user"},
                credential_type=lambda **kwargs: touched.append(True))
        self.assertEqual(touched, [])

    def test_conversation_authority_is_explicit_bound_and_not_a_dollar_approval(self):
        plan = module.validate_plan(plan_value())
        approval = conversation_value(plan)
        validated = module.validate_approval(plan, approval, acknowledged_sha256=None, now=NOW)
        self.assertEqual(validated, approval)
        self.assertNotIn("max_cost_usd", validated)
        for change in ({"authority_statement": "allow_live=true"}, {"approved_by": "executor"},
                       {"approval_reference": ""}, {"plan_sha256": "b" * 64},
                       {"resource_id": "different"}, {"principal_id": TENANT},
                       {"expires_at": NOW.isoformat()}, {"operations": ["query", "delete"]},
                       {"max_cost_usd": 1}):
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_approval(plan, {**approval, **change}, acknowledged_sha256=None, now=NOW)

    def test_conversation_executor_bounds_cannot_exceed_current_read_scope(self):
        for change in ({"timeout_seconds": 31}, {"max_rows": 101}):
            plan = plan_value()
            plan["limits"].update(change)
            approval = conversation_value(plan)
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_approval(plan, approval, acknowledged_sha256=None, now=NOW)

    def test_conversation_run_records_provenance_and_rechecks_expiry_before_io(self):
        plan = plan_value()
        approval = conversation_value(plan)
        clock = [NOW]
        touched = []

        class Credential:
            def close(self):
                touched.append("closed")

        async def observed(case, **kwargs):
            if case["case_id"] == "LI-ADX-02":
                clock[0] = NOW + timedelta(minutes=10)
            kwargs["before_call"]()
            touched.append(case["case_id"])
            return {"outcome": "PASS_LIVE", "attempts": 1, "evidence_class": "live"}

        with tempfile.TemporaryDirectory() as temporary:
            report = asyncio.run(module.run_plan(
                plan, approval, acknowledged_sha256=None, report_path=Path(temporary) / "receipt.json",
                credential_factory=lambda *_: Credential(), artifact_verifier=lambda *_: {"version": "fixture"},
                case_runner=observed, now=lambda: clock[0],
            ))
        self.assertEqual(touched, ["LI-ADX-01", "closed"])
        self.assertEqual(report["authorization"]["origin"], "conversation-user")
        self.assertEqual(report["authorization"]["limits_basis"], "executor")
        self.assertEqual(report["authorization"]["statement"], approval["authority_statement"])
        self.assertIsNone(report["cost_usd"])
        self.assertFalse(report["passed"])

    def test_execute_without_approval_records_blocked_before_factories(self):
        touched = []
        with tempfile.TemporaryDirectory() as temporary:
            report = asyncio.run(module.run_plan(
                plan_value(), None, acknowledged_sha256=None, report_path=Path(temporary) / "receipt.json",
                credential_factory=lambda *_: touched.append("credential"),
                artifact_verifier=lambda *_: touched.append("artifact"), now=lambda: NOW,
            ))
        self.assertEqual(touched, [])
        self.assertEqual(report["counts"]["BLOCKED"], 2)
        self.assertFalse(report["passed"])

    def test_execute_closes_credential_and_retains_unrun_tail_after_failure(self):
        plan = plan_value()
        approval = approval_value(plan)
        touched = []

        class Credential:
            def close(self):
                touched.append("closed")

        async def fail(case, **kwargs):
            kwargs["before_call"]()
            touched.append(case["case_id"])
            return {"outcome": "FAIL", "attempts": 1, "evidence_class": "live", "error_code": "oracle_mismatch"}

        with tempfile.TemporaryDirectory() as temporary:
            report = asyncio.run(module.run_plan(
                plan, approval, acknowledged_sha256=module.digest(approval), report_path=Path(temporary) / "receipt.json",
                credential_factory=lambda *_: Credential(), artifact_verifier=lambda *_: {"version": "fixture"},
                case_runner=fail, now=lambda: NOW,
            ))
        self.assertEqual(touched, ["LI-ADX-01", "closed"])
        self.assertEqual(report["counts"]["FAIL"], 1)
        self.assertEqual(report["counts"]["NOT_RUN"], 1)
        self.assertFalse(report["passed"])

    def test_report_collision_refuses_before_credentials(self):
        touched = []
        plan = plan_value()
        approval = approval_value(plan)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            path.write_text("existing evidence")
            with self.assertRaises(module.LiveRefusal):
                asyncio.run(module.run_plan(plan, approval, acknowledged_sha256=module.digest(approval), report_path=path,
                                            credential_factory=lambda *_: touched.append(True), now=lambda: NOW))
            self.assertEqual(path.read_text(), "existing evidence")
        self.assertEqual(touched, [])

    def test_interrupted_case_preserves_unknown_attempts_and_unrun_tail(self):
        plan = plan_value()
        approval = approval_value(plan)

        class Credential:
            def close(self):
                pass

        async def interrupted(case, **kwargs):
            kwargs["before_call"]()
            raise RuntimeError("private provider payload")

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            report = asyncio.run(module.run_plan(plan, approval, acknowledged_sha256=module.digest(approval),
                                                report_path=path, credential_factory=lambda *_: Credential(),
                                                artifact_verifier=lambda *_: {}, case_runner=interrupted, now=lambda: NOW))
            self.assertNotIn("private provider", path.read_text())
        self.assertIsNone(report["cases"][0]["attempts"])
        self.assertEqual(report["cases"][0]["attempts_unknown_reason"], "interrupted_or_unreported")
        self.assertEqual(report["counts"]["NOT_RUN"], 1)
        self.assertEqual(report["attempted"], 1)

    def test_plan_has_no_credential_or_cloud_side_effect_and_reports_missing_approval(self):
        plan = module.validate_plan(plan_value())
        report = module.describe_plan(plan)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["plan_sha256"], module.digest(plan))
        self.assertEqual(report["operations"], ["query"])
        self.assertNotIn("print", json.dumps(report))

    def test_approval_is_exact_expiring_and_has_no_write_permission(self):
        plan = module.validate_plan(plan_value())
        approval = approval_value(plan)
        validated = module.validate_approval(plan, approval, acknowledged_sha256=module.digest(approval), now=NOW)
        self.assertEqual(validated["approval_reference"], approval["approval_reference"])
        for change in ({"plan_sha256": "b" * 64}, {"resource_id": "different"},
                       {"principal_id": TENANT}, {"expires_at": NOW.isoformat()},
                       {"not_before": (NOW + timedelta(seconds=1)).isoformat()},
                       {"operations": ["query", "delete"]}, {"max_cost_usd": None}):
            candidate = {**approval, **change}
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_approval(plan, candidate, acknowledged_sha256=module.digest(candidate), now=NOW)
        with self.assertRaises(module.LiveRefusal):
            module.validate_approval(plan, approval, acknowledged_sha256="c" * 64, now=NOW)
        with self.assertRaises(module.LiveRefusal):
            module.validate_approval(plan, None, acknowledged_sha256=None, now=NOW)

    def test_unknown_secret_and_mismatched_target_configuration_refuse(self):
        for change in ({"credential": "must-not-appear"}, {"schema_version": True},
                       {"retention": "delete-source"}, {"data_classification": "unreviewed"}):
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal) as failure:
                module.validate_plan({**plan_value(), **change})
            self.assertNotIn("must-not-appear", str(failure.exception))
        for change in ({"endpoint": "https://fixture.kusto.windows.net/?sig=private"},
                       {"service": "gremlin"}, {"database": "Another"},
                       {"subscription_id": TENANT}):
            plan = plan_value()
            plan["target"].update(change)
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_plan(plan)

    def test_case_inventory_is_unique_and_bounded_with_explicit_expected_results(self):
        for change in ({"max_calls": 0}, {"max_calls": True}, {"timeout_seconds": float("inf")},
                       {"max_rows": 0}, {"max_output_bytes": -1}):
            plan = plan_value()
            plan["limits"].update(change)
            with self.subTest(change=change), self.assertRaises(module.LiveRefusal):
                module.validate_plan(plan)
        for mode in ("duplicate", "no-oracle", "write", "too-many"):
            plan = plan_value()
            if mode == "duplicate":
                plan["cases"].append(copy.deepcopy(plan["cases"][0]))
            elif mode == "no-oracle":
                del plan["cases"][0]["expected"]
            elif mode == "write":
                plan["cases"][0]["expression"] = ".drop table Fixture"
            else:
                plan["limits"]["max_calls"] = 1
            with self.subTest(mode=mode), self.assertRaises(module.LiveRefusal):
                module.validate_plan(plan)

    def test_budget_reserves_before_work_and_checks_expiry(self):
        ticks = [100.0]
        budget = module.CallBudget(max_calls=2, timeout_seconds=10, clock=lambda: ticks[0])
        budget.reserve()
        budget.reserve()
        with self.assertRaises(module.LiveRefusal):
            budget.reserve()
        self.assertEqual(budget.calls, 2)
        budget = module.CallBudget(max_calls=2, timeout_seconds=10, clock=lambda: ticks[0])
        ticks[0] = 111.0
        with self.assertRaises(module.LiveRefusal):
            budget.reserve()
        self.assertEqual(budget.calls, 0)

    def test_receipt_reservation_never_clobbers_and_keeps_unrun_cases(self):
        plan = module.validate_plan(plan_value())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            with module.Receipt(path, plan) as receipt:
                self.assertEqual(receipt.report["counts"]["NOT_RUN"], 2)
                with self.assertRaises(module.LiveRefusal):
                    module.Receipt(path, plan).__enter__()
                receipt.record("LI-ADX-01", "PASS_LIVE", attempts=1, row_count=1,
                               observed_sha256="d" * 64, evidence_class="live")
            saved = json.loads(path.read_text())
            self.assertEqual(saved["counts"]["PASS_LIVE"], 1)
            self.assertEqual(saved["counts"]["NOT_RUN"], 1)
            self.assertFalse(saved["passed"])
            self.assertNotIn("print", path.read_text())

    def test_report_cannot_upgrade_offline_refusal_or_secret_payload_to_live_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            with module.Receipt(Path(temporary) / "report.json", module.validate_plan(plan_value())) as receipt:
                for values in ({"evidence_class": "offline", "attempts": 1},
                               {"evidence_class": "live", "attempts": 0},
                               {"evidence_class": "live", "attempts": 1, "detail": "Bearer private"}):
                    with self.subTest(values=values), self.assertRaises(module.LiveRefusal):
                        receipt.record("LI-ADX-01", "PASS_LIVE", **values)
                receipt.record("LI-ADX-01", "PASS_REFUSAL", attempts=0, evidence_class="offline")
                self.assertFalse(receipt.report["passed"])

    def test_wheel_identity_is_verified_and_source_is_not_accepted_as_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.whl"
            path.write_bytes(b"not-a-wheel")
            artifact = {"distribution": "azdata", "version": "4.0.0a3", "wheel": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            with self.assertRaises(module.LiveRefusal):
                module.verify_artifact(artifact)


if __name__ == "__main__":
    unittest.main()