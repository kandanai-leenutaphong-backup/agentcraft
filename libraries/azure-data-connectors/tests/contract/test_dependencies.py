import builtins
import unittest
from unittest.mock import patch

from azdata import CreateRequest, Policy, connect
from tests.contract.test_conformance import NoIO, SERVICES, config, requests


class DependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_optional_provider_refuses_before_credential_or_io(self):
        modules = {"search": "azure.search", "cosmos": "azure.cosmos", "blobs": "azure.storage.blob", "tables": "azure.data.tables",
                   "adx": "azure.kusto", "eventhouse": "azure.kusto", "graph": "aiohttp", "gremlin": "gremlin_python",
                   "sql": "mssql_python", "postgresql": "psycopg"}
        original = builtins.__import__
        for service in SERVICES:
            client = connect(service, config(service), credential=NoIO(), policy=Policy("fixture"))
            def missing(name, *args, prefix=modules[service], **kwargs):
                if name == prefix or name.startswith(prefix + "."):
                    raise ImportError("synthetic missing provider")
                return original(name, *args, **kwargs)
            with self.subTest(service=service), patch("builtins.__import__", side_effect=missing):
                result = await client.query(requests(service)["query"])
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.errors[0].code, "missing_dependency_" + service)
                self.assertEqual(result.metrics["attempts"], 0)
            await client.aclose()


if __name__ == "__main__":
    unittest.main()