import unittest
from dataclasses import FrozenInstanceError

from azdata import (
    ConfigurationError, ConnectorConfig, ContentValue, Limits, Policy, RecordInput,
    RecordKey, ResourceAddress, UpsertRequest,
)


class ValueTests(unittest.TestCase):
    def test_requests_snapshot_nested_data(self):
        payload = {"title": "original", "nested": {"tags": ["one"]}}
        request = UpsertRequest(mode="merge", records=[RecordInput(RecordKey({"id": "one"}), ContentValue(payload))])
        payload["nested"]["tags"].append("two")
        self.assertEqual(request.records[0].content.data["nested"]["tags"], ("one",))
        with self.assertRaises(TypeError):
            request.records[0].content.data["title"] = "changed"
        with self.assertRaises(FrozenInstanceError):
            request.mode = "replace"

    def test_repr_excludes_record_contents(self):
        request = UpsertRequest(mode="merge", records=[RecordInput(RecordKey({"id": "one"}), ContentValue({"secret": "private-payload"}))])
        self.assertNotIn("private-payload", repr(request))

    def test_policy_denies_writes_and_validates_grants(self):
        policy = Policy(principal="fixture")
        self.assertEqual(policy.grants, {"read", "query"})
        with self.assertRaises(ConfigurationError):
            Policy(principal="fixture", grants={"all"})

    def test_invalid_limits_do_not_become_valid_integers(self):
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                Policy(principal="fixture", limits=Limits(max_items=value))

    def test_request_limits_cannot_raise_policy_ceilings(self):
        self.assertFalse(Limits(max_items=101).within(Limits()))
        self.assertTrue(Limits(max_items=10).within(Limits()))

    def test_config_requires_explicit_endpoint_allowlist(self):
        target = ResourceAddress({"index": "fixture"})
        for endpoint, hosts in (("http://unit.search.windows.net", ("unit.search.windows.net",)),
                                ("https://unit.search.windows.net", ()),
                                ("https://unit.search.windows.net", ("different.example",)),
                                ("https://user:password@unit.search.windows.net", ("unit.search.windows.net",))):
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigurationError):
                ConnectorConfig(endpoint, target, hosts)

    def test_config_snapshots_scope_without_network(self):
        coordinates = {"index": "fixture"}
        config = ConnectorConfig("https://unit.search.windows.net/", ResourceAddress(coordinates), ("unit.search.windows.net",))
        coordinates["index"] = "another"
        self.assertEqual(config.target.coordinates["index"], "fixture")
        self.assertEqual(config.endpoint, "https://unit.search.windows.net")


if __name__ == "__main__":
    unittest.main()