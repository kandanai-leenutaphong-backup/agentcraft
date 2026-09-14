"""Bootstrap refuses unapproved writes and verifies the specific CSV batch offline."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mechanism"))
import bootstrap_adx as bootstrap
from adx_connector import QueryResult
from adx_connector.schema import infer_schema


class Bootstrap(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.csv = Path(temporary.name) / "sample.csv"
        self.csv.write_text('record_id,note\na,"two\nlines"\n', encoding="utf-8")
        self.arguments = ["--csv", str(self.csv), "--table", "Events", "--database", "Logs",
                          "--cluster-uri", "https://cluster.example.test", "--skip-provision"]

    def call(self, arguments: list[str], counts: tuple[int, ...] = (0, 1)):
        client = MagicMock()
        client.health.return_value = {"reachable": True, "principal": "fixture"}
        client.infer_schema_from_csv.return_value = infer_schema(self.csv, "Events")
        client.query.side_effect = [QueryResult(columns=("Count",), rows=((count,),)) for count in counts]
        client.ingestor.ingest_file.return_value = SimpleNamespace(
            mode=SimpleNamespace(value="queued"), bytes_sent=self.csv.stat().st_size, elapsed_seconds=0,
        )
        client.ingestion_failures.return_value = []
        with patch.object(bootstrap, "AdxConnector") as constructor:
            constructor.return_value.__enter__.return_value = client
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = bootstrap.main(arguments)
        return result, constructor, client

    def test_unconfirmed_and_hostile_targets_refuse_before_connecting(self) -> None:
        cases = [self.arguments, [*self.arguments, "--confirm-database", "Other"],
                 [*self.arguments, "--confirm-database", "Logs", "--recreate"],
                 [*self.arguments, "--confirm-database", "Logs", "--table", "X; .drop table Victim"]]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result, constructor, _client = self.call(arguments)
                self.assertEqual(result, 2)
                constructor.assert_not_called()

    def test_csv_records_not_physical_lines_and_content_identity(self) -> None:
        self.assertEqual(bootstrap.count_data_rows(self.csv, True), 1)
        options = {"has_header": True, "force_types": {}}
        original = bootstrap.batch_identity(self.csv, "Events", **options)
        self.csv.write_text(self.csv.read_text().replace("two", "six"), encoding="utf-8")
        self.assertNotEqual(bootstrap.batch_identity(self.csv, "Events", **options), original)

    def test_confirmed_write_reads_back_parameterized_batch(self) -> None:
        result, _constructor, client = self.call([*self.arguments, "--confirm-database", "Logs"])
        self.assertEqual(result, 0)
        client.ingestor.ingest_file.assert_called_once()
        for call in client.query.call_args_list:
            self.assertIn("set_has_element(extent_tags(), batch_tag)", call.args[0])
            self.assertTrue(call.args[1]["batch_tag"].startswith("ingest-by:"))
        client.wait_for_rows.assert_not_called()

    def test_repeated_batch_skips_only_with_exact_batch_evidence(self) -> None:
        result, _constructor, client = self.call([*self.arguments, "--confirm-database", "Logs"], (1,))
        self.assertEqual(result, 0)
        client.ingestor.ingest_file.assert_not_called()
        result, _constructor, client = self.call([*self.arguments, "--confirm-database", "Logs"], (2,))
        self.assertEqual(result, 1)
        client.ingestor.ingest_file.assert_not_called()

    def test_expected_count_and_recreation_are_explicit(self) -> None:
        result, constructor, _client = self.call([*self.arguments, "--confirm-database", "Logs", "--expect-rows", "0"])
        self.assertEqual(result, 2)
        constructor.assert_not_called()
        result, _constructor, client = self.call([*self.arguments, "--confirm-database", "Logs", "--recreate", "--confirm-table", "Events"])
        self.assertEqual(result, 0)
        client.command.assert_called_once_with(".drop table Events ifexists")


if __name__ == "__main__":
    unittest.main(verbosity=2)