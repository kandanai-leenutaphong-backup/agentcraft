import unittest

from llm_interface import Capabilities, ConnectionConfig, Limits, LlmError, Policy


class ConfigTests(unittest.TestCase):
    def test_foundry_and_account_endpoints_select_profiles(self):
        project = ConnectionConfig("https://fixture.services.ai.azure.com/api/projects/demo", "chat")
        account = ConnectionConfig("https://fixture.openai.azure.com", "chat")
        self.assertEqual(project.provider, "foundry")
        self.assertEqual(account.provider, "azure_openai")
        self.assertEqual(account.endpoint, "https://fixture.openai.azure.com/openai/v1/")
        self.assertEqual(ConnectionConfig(account.endpoint, "chat"), account)

    def test_untrusted_or_malformed_configuration_refuses(self):
        for endpoint in ("http://fixture.invalid", "https://user:pass@fixture.invalid", "https://fixture.invalid/?x=1",
                         "https://fixture.invalid/#x", "https://fixture.invalid:444", "https://fixture.invalid/a/../b"):
            with self.subTest(endpoint=endpoint), self.assertRaises(LlmError):
                ConnectionConfig(endpoint, "chat")
        with self.assertRaises(LlmError):
            ConnectionConfig("https://other.invalid", "chat", allowed_hosts=("fixture.invalid",))
        with self.assertRaises(LlmError):
            ConnectionConfig("https://fixture.invalid", "chat", provider="foundry")

    def test_policy_is_explicit_and_snapshotted(self):
        self.assertFalse(Policy().allow_model_calls)
        granted = ["lookup"]
        policy = Policy(allow_model_calls=True, allowed_tools=granted)
        granted.append("other")
        self.assertEqual(policy.allowed_tools, frozenset({"lookup"}))
        self.assertNotEqual(policy.digest, Policy().digest)

    def test_invalid_limits_and_capabilities_refuse(self):
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(LlmError):
                Limits(timeout_seconds=value)
        with self.assertRaises(LlmError):
            Limits(max_tool_calls=True)
        with self.assertRaises(LlmError):
            Capabilities(chat="yes")