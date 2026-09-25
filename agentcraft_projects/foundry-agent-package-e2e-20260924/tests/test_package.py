"""S1 offline evidence: the agent package's tools agree with the frozen oracle on every dataset row."""

import asyncio
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT / "agent"
REPOSITORY = PROJECT.parents[1]
TEMPLATE_APP = REPOSITORY / "template_apps/foundry_hosted_agent/app"
# Same import roots as template deploy.sh sets on PYTHONPATH.
RUNTIME_PATHS = (TEMPLATE_APP, REPOSITORY / "libraries/llm-interface/src", REPOSITORY / "libraries/framework-core/src",
                 REPOSITORY / "libraries/modular-agents/modules/agent-config-build")
BASELINE_INSTRUCTIONS_SHA256 = "f8c33ae443446aaa586032812f2b69bf25ac348fd6e41e40429973db5270e8cf"
JOURNEYS = {"pq-verification-001": ("TOTAL_CENTS=5160", [("lookup_zone", None), ("quote_parcel", None)]),
            "pq-verification-003": ("TOTAL_CENTS=1605", [("lookup_zone", None), ("quote_parcel", None)]),
            "pq-verification-007": ("ERROR=E_ZONE_UNKNOWN", [("lookup_zone", "E_ZONE_UNKNOWN")]),
            "pq-verification-002": ("ERROR=E_WEIGHT_LIMIT", [("lookup_zone", None),
                                                             ("quote_parcel", "E_WEIGHT_LIMIT")])}


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_file("parcel_reference", PROJECT / "dataset/reference.py")
tools = load_file("parcel_package_tools", PACKAGE / "parcel_tools.py")


def rows():
    return [json.loads(line) for split in ("train", "validation", "verification")
            for line in (PROJECT / f"dataset/{split}.jsonl").read_text().splitlines() if line.strip()]


def run_package(zone_code, weight_grams, express):
    """(answer, [(tool, error_code or None)]) following the tool order the instructions prescribe."""
    try:
        zone = tools.lookup_zone(zone_code)
    except tools.ZoneUnknownError as error:
        return f"ERROR={error.error_code}", [("lookup_zone", error.error_code)]
    try:
        quote = tools.quote_parcel(weight_grams, zone["rate_cents_per_kg"], zone["base_fee_cents"], express)
    except (tools.WeightLimitError, tools.WeightInvalidError) as error:
        return f"ERROR={error.error_code}", [("lookup_zone", None), ("quote_parcel", error.error_code)]
    return f"TOTAL_CENTS={quote['total_cents']}", [("lookup_zone", None), ("quote_parcel", None)]


class OracleAgreementTests(unittest.TestCase):
    def test_all_rows_answers_codes_and_tools_agree(self):
        dataset = rows()
        self.assertEqual(len(dataset), 54)
        for row in dataset:
            with self.subTest(row=row["id"]):
                answer, calls = run_package(row["zone"], row["weight_grams"], row["express"])
                self.assertEqual(answer, reference.expected_answer(row["zone"], row["weight_grams"], row["express"]))
                self.assertEqual(answer, row["ground_truth"])
                self.assertEqual([name for name, _ in calls], row["expected_tools"])
                self.assertEqual([name for name, _ in calls], reference.expected_tools(row["zone"]))

    def test_raw_tool_results_agree(self):
        for row in rows():
            with self.subTest(row=row["id"]):
                if row["zone"] not in reference.ZONES:
                    continue
                zone = tools.lookup_zone(row["zone"])
                self.assertEqual(zone, reference.lookup_zone(row["zone"]))
                if row["weight_grams"] <= reference.MAX_WEIGHT_GRAMS:
                    self.assertEqual(
                        tools.quote_parcel(row["weight_grams"], zone["rate_cents_per_kg"], zone["base_fee_cents"],
                                           row["express"]),
                        reference.quote_parcel(row["weight_grams"], zone["rate_cents_per_kg"],
                                               zone["base_fee_cents"], row["express"]))

    def test_tables_and_declared_codes_match_oracle(self):
        self.assertEqual(tools.ZONES, reference.ZONES)
        self.assertEqual(tools.MAX_WEIGHT_GRAMS, reference.MAX_WEIGHT_GRAMS)
        self.assertEqual(tools.ERROR_CODES, reference.ERRORS)
        for zone in reference.UNKNOWN_ZONES + ("", "z-alpha", None, 7):
            with self.subTest(zone=zone), self.assertRaises(tools.ZoneUnknownError):
                tools.lookup_zone(zone)

    def test_invalid_weight_agrees(self):
        for weight in (0, -1, True, 1.5, "500", None, reference.MAX_WEIGHT_GRAMS + 1):
            with self.subTest(weight=weight):
                with self.assertRaises(reference.QuoteError) as expected:
                    reference.quote_parcel(weight, 410, 250, False)
                with self.assertRaises((tools.WeightInvalidError, tools.WeightLimitError)) as actual:
                    tools.quote_parcel(weight, 410, 250, False)
                self.assertEqual(actual.exception.error_code, expected.exception.code)

    def test_journeys(self):
        by_id = {row["id"]: row for row in rows()}
        for row_id, (answer, calls) in JOURNEYS.items():
            with self.subTest(journey=row_id):
                row = by_id[row_id]
                self.assertEqual(run_package(row["zone"], row["weight_grams"], row["express"]), (answer, calls))


class PackageTests(unittest.TestCase):
    def test_prompt_bytes_equal_constitution_pin(self):
        prompt = (PACKAGE / "prompts/agent.md").read_bytes()
        self.assertEqual(prompt, (PROJECT / "design/baseline-instructions.md").read_bytes())
        self.assertEqual(hashlib.sha256(prompt).hexdigest(), BASELINE_INSTRUCTIONS_SHA256)

    def test_package_is_standalone(self):
        source = (PACKAGE / "parcel_tools.py").read_text()
        self.assertNotIn("reference", source)
        self.assertEqual(sorted(p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
                                if p.is_file() and "__pycache__" not in p.parts),
                         ["configuration.yaml", "parcel_tools.py", "prompts/agent.md"])

    def test_template_runtime_loads_exactly_the_listed_tools(self):
        for path in RUNTIME_PATHS:
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        import tool_calls
        from composition import load_spec, package_manifest
        from llm_interface import ToolCall

        spec = load_spec(package=PACKAGE)
        self.assertEqual((spec.name, spec.model), ("agentcraft-pkg-e2e-parcel", "gpt-5.6-luna"))
        self.assertEqual([tool.__name__ for tool in spec.tools], ["lookup_zone", "quote_parcel"])
        # agentconfig.load_instructions strips surrounding whitespace; file bytes carry the pin.
        self.assertEqual(spec.instructions, (PACKAGE / "prompts/agent.md").read_text().strip())
        manifest = package_manifest(PACKAGE)
        self.assertEqual(set(manifest["files"]), {"configuration.yaml", "parcel_tools.py", "prompts/agent.md"})

        recorder = tool_calls.ToolCallRecorder(spec.tools)
        lookup = {tool.__name__: tool for tool in recorder.tools}["lookup_zone"]

        async def call():
            self.assertTrue(recorder.authorize(ToolCall("lookup_zone", {"zone_code": "Z-OMEGA"}, call_id="c1")))
            return await lookup(zone_code="Z-OMEGA")

        self.assertEqual(asyncio.run(call()),
                         {"error": {"code": "E_ZONE_UNKNOWN", "message": "destination zone is not served"}})
        self.assertEqual((recorder.records["c1"]["status"], recorder.records["c1"]["error_code"]),
                         ("error", "E_ZONE_UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
