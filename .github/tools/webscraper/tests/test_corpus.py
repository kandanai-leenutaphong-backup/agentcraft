import json
import hashlib
import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from data_collection.corpus import (
    acquire_pages, acquire_repositories, build_index, classify_family, discover_pages, feature_coverage, indexed_text,
    lfs_pointer, load_plan, page_metadata, search_index, verified_lfs_changes, verify_corpus, write_json,
)
from data_collection.models import HTTPResponse, ScrapeOptions, ScrapeResult
from data_collection.storage import save_result


class CorpusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_plan_rejects_untrusted_or_duplicate_repositories(self):
        path = self.root / "plan.json"
        for names in (["other/repository"], ["MicrosoftDocs/../bad"], ["MicrosoftDocs/docs", "microsoftdocs/docs"]):
            write_json(path, {"schema_version": 1, "families": {"docs": "Documentation"},
                              "repositories": [{"repository": name, "family": "docs"} for name in names]})
            with self.assertRaises(ValueError):
                load_plan(path)

    def test_plan_refuses_escaping_families_and_credentialed_pages(self):
        path = self.root / "plan.json"
        for family, url in (("../../outside", "https://example.test"), ("docs", "https://user:password@example.test"),
                            ("docs", "file:///etc/passwd"), ("missing", "https://example.test")):
            write_json(path, {"schema_version": 1, "families": {"docs": "Documentation"},
                              "pages": [{"url": url, "family": family}]})
            with self.assertRaises(ValueError):
                load_plan(path)
        write_json(path, {"schema_version": 1, "families": {"../../outside": "Invalid"}})
        with self.assertRaises(ValueError):
            load_plan(path)
        write_json(path, {"schema_version": 1, "families": {"docs": "Documentation"},
                          "repositories": [{"repository": "MicrosoftDocs/docs", "family": "docs"}],
                          "pages": [{"url": "https://example.test", "family": "docs"}]})
        self.assertEqual(load_plan(path)["pages"][0]["family"], "docs")

    def test_existing_origin_mismatch_is_preserved_and_recorded(self):
        destination = self.root / "sources" / "MicrosoftDocs__docs"
        destination.mkdir(parents=True)
        marker = destination / "keep.txt"
        marker.write_text("existing content")
        with patch("data_collection.corpus.git", return_value="https://github.com/other/docs.git") as command:
            summary = acquire_repositories({"repositories": [{"repository": "MicrosoftDocs/docs"}]}, self.root)
        self.assertFalse(summary["ok"])
        self.assertEqual(command.call_count, 1)
        self.assertEqual(marker.read_text(), "existing content")
        receipt = json.loads((self.root / "receipts/repositories/MicrosoftDocs__docs.json").read_text())
        self.assertIn("different origin", receipt["error"])

    def test_existing_clean_snapshot_is_pinned_without_fetching(self):
        (self.root / "sources/MicrosoftDocs__docs").mkdir(parents=True)
        write_json(self.root / "receipts/repositories/MicrosoftDocs__docs.json", {
            "ok": True, "commit": "a" * 40, "retrieved_at": "2026-09-01T00:00:00Z", "lfs_expanded": True,
        })
        replies = ["https://github.com/MicrosoftDocs/docs.git", "a" * 40, "2026-09-13T00:00:00Z", "", ""]
        with patch("data_collection.corpus.git", side_effect=replies) as command:
            summary = acquire_repositories({"repositories": [{"repository": "MicrosoftDocs/docs"}]}, self.root)
        self.assertTrue(summary["ok"])
        self.assertFalse(any("clone" in call.args[0] or "fetch" in call.args[0] for call in command.call_args_list))
        receipt = json.loads((self.root / "receipts/repositories/MicrosoftDocs__docs.json").read_text())
        self.assertEqual(receipt["commit"], "a" * 40)
        self.assertEqual(receipt["retrieved_at"], "2026-09-01T00:00:00Z")
        self.assertTrue(receipt["lfs_expanded"])

    def test_page_extraction_preserves_content_metadata_and_links(self):
        result = page_metadata('<html><head><meta name="ms.date" content="2026-09-13"></head>'
                               '<body><nav>Site navigation</nav><main><h1>Foundry</h1><p>Content</p>'
                               '<a href="models">Models</a><script>never_execute()</script></main></body></html>')
        self.assertIn("Content", result["text"])
        self.assertNotIn("never_execute", result["text"])
        self.assertNotIn("Site navigation", result["text"])
        self.assertEqual(result["headings"], ["Foundry"])
        self.assertEqual(result["metadata"]["ms.date"], "2026-09-13")
        self.assertEqual(result["links"][0]["href"], "models")

    def test_source_discovery_is_bounded_deduplicated_and_skips_includes(self):
        directory = self.root / "sources/MicrosoftDocs__azure-ai-docs/articles/foundry"
        (directory / "includes").mkdir(parents=True)
        (directory / "overview.md").write_text("# Overview")
        (directory / "new-feature.md").write_text("# New feature")
        (directory / "includes/content.md").write_text("Shared content")
        plan = {"repositories": [{"repository": "MicrosoftDocs/azure-ai-docs", "family": "01-master-indexes"}],
                "pages": [{"url": "https://learn.microsoft.com/en-us/azure/foundry/overview?tabs=python"}],
                "discovery": [{"repository": "MicrosoftDocs/azure-ai-docs", "source_prefix": "articles/foundry",
                               "base_url": "https://learn.microsoft.com/en-us/azure/foundry"}]}
        self.assertEqual(discover_pages(plan, self.root)["added"], 1)
        self.assertTrue(plan["pages"][-1]["url"].endswith("/new-feature"))
        self.assertEqual(discover_pages(plan, self.root)["added"], 0)
        plan["discovery"][0]["source_prefix"] = "../../.."
        with self.assertRaises(ValueError):
            discover_pages(plan, self.root)

    def test_pages_resume_only_verified_artifacts(self):
        url = "https://example.test/docs"
        plan = {"pages": [{"url": url, "family": "docs"}]}
        response = HTTPResponse(url, 200, {"content-type": "text/html"}, b"<h1>Verified documentation</h1>")
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=response) as request:
            first = asyncio.run(acquire_pages(plan, self.root))
            second = asyncio.run(acquire_pages(plan, self.root))
            self.assertEqual(request.await_count, 1)
            self.assertEqual(first["acquired"], 1)
            self.assertEqual(second["resumed"], 1)
            identity = hashlib.sha256(url.encode()).hexdigest()
            receipt = json.loads((self.root / f"receipts/pages/{identity}.json").read_text())
            extracted = self.root / receipt["extracted"]
            extracted.write_text("corrupted")
            recovered = asyncio.run(acquire_pages(plan, self.root))
            self.assertEqual(recovered["resumed"], 1)
            self.assertEqual(request.await_count, 1)
            self.assertIn("Verified documentation", json.loads(extracted.read_text())["text"])
            (self.root / receipt["directory"] / "page.html").write_text("corrupted")
            repaired = asyncio.run(acquire_pages(plan, self.root))
            self.assertEqual(repaired["acquired"], 1)
            self.assertEqual(request.await_count, 2)

    def test_page_resume_does_not_hide_retained_failures(self):
        url = "https://example.test/denied"
        plan = {"pages": [{"url": url, "family": "docs"}]}
        response = HTTPResponse(url, 403, {"content-type": "text/html"}, b"<h1>Denied</h1>")
        with patch("data_collection.network.Transport.request", new_callable=AsyncMock, return_value=response) as request:
            self.assertFalse(asyncio.run(acquire_pages(plan, self.root))["ok"])
            resumed = asyncio.run(acquire_pages(plan, self.root))
            self.assertFalse(resumed["ok"])
            self.assertEqual(resumed["retained_failures"], 1)
            self.assertEqual(request.await_count, 1)

    def test_index_search_and_full_hash_verification(self):
        repository = {"repository": "MicrosoftDocs/docs", "family": "docs"}
        plan = {"repositories": [repository], "families": {"docs": "Documentation"}}
        directory = self.root / "sources/MicrosoftDocs__docs"
        directory.mkdir(parents=True)
        document = directory / "agent.md"
        document.write_text("# Agent memory\n\nFoundry agent memory persists across conversations.\n")
        write_json(self.root / "receipts/repositories/MicrosoftDocs__docs.json", {
            **repository, "ok": True, "commit": "a" * 40, "commit_date": "2026-09-13", "source_url": "https://github.com/MicrosoftDocs/docs.git",
            "path": "sources/MicrosoftDocs__docs",
        })
        tree = f"100644 blob {'b' * 40} {document.stat().st_size}\tagent.md\x00"
        with patch("data_collection.corpus.git", side_effect=["a" * 40, tree]):
            summary = build_index(plan, self.root)
        self.assertEqual(summary["files"], 1)
        self.assertEqual(summary["unattempted_live_pages"], 0)
        self.assertEqual(summary["failed_live_pages"], [])
        matches = search_index(self.root, '"agent memory"')
        self.assertEqual(matches[0]["title"], "Agent memory")
        self.assertIn("Agent memory", (self.root / "features/docs/documents.md").read_text())
        plan["feature_checks"] = {"docs": [{"title": "Memory", "query": '"agent memory"'}, {"title": "Missing", "query": '"no such feature"'}]}
        coverage = feature_coverage(plan, self.root)
        self.assertEqual(coverage["matched"], 1)
        self.assertEqual(coverage["missing"], ["Missing"])
        with sqlite3.connect(self.root / "index.sqlite3") as database:
            database.execute("INSERT INTO files VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?)", (
                "MicrosoftDocs/docs", "docs", "asset.png", "https://example.test/asset.png",
                "Agent memory", "asset", 3, "unknown", "unknown", "", 0,
            ))
            database.execute("INSERT INTO text_index(text_index) VALUES('rebuild')")
        self.assertEqual(len(search_index(self.root, '"agent memory"')), 1)
        with sqlite3.connect(self.root / "index.sqlite3") as database:
            database.execute("DELETE FROM files WHERE path='asset.png'")
        with patch("data_collection.corpus.git", return_value="a" * 40):
            self.assertTrue(verify_corpus(self.root)["ok"])
            document.write_text("corrupted")
            self.assertFalse(verify_corpus(self.root)["ok"])

    def test_lfs_pointer_is_not_misreported_as_downloaded_asset(self):
        kind, text = indexed_text(Path("model.bin"), b"version https://git-lfs.github.com/spec/v1\noid sha256:fixture\nsize 123\n")
        self.assertEqual(kind, "lfs-pointer")
        self.assertEqual(text, "")

    def test_verification_includes_separate_browser_captures(self):
        build_index({"repositories": [], "families": {}}, self.root)
        capture = save_result(ScrapeResult(url="https://example.test", ok=True, html="<h1>Captured</h1>"),
                              self.root / "pages/browser-validation", ScrapeOptions())
        verification = verify_corpus(self.root)
        self.assertTrue(verification["ok"])
        self.assertEqual(verification["supplementary_captures_checked"], 1)
        (capture / "page.html").write_text("corrupted")
        self.assertFalse(verify_corpus(self.root)["ok"])

    def test_lfs_object_contract_requires_sha256_and_nonnegative_size(self):
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 123\n"
        self.assertEqual(lfs_pointer(pointer), {"sha256": "a" * 64, "bytes": 123})
        self.assertIsNone(lfs_pointer(b"ordinary content"))
        with self.assertRaises(ValueError):
            lfs_pointer(pointer.replace(b"size 123", b"size -1"))
        with self.assertRaises(ValueError):
            lfs_pointer(pointer.replace(b"a" * 64, b"invalid"))

    def test_lfs_index_differences_require_pinned_content_hashes(self):
        payload = b"GIF89a verified fixture bytes"
        asset = self.root / "image.gif"
        asset.write_bytes(payload)
        pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{hashlib.sha256(payload).hexdigest()}\nsize {len(payload)}\n"
        with patch("data_collection.corpus.git", side_effect=[str(len(pointer)), pointer]):
            self.assertTrue(verified_lfs_changes(self.root, "M  image.gif\x00"))
        asset.write_bytes(b"corrupted")
        with patch("data_collection.corpus.git", side_effect=[str(len(pointer)), pointer]):
            self.assertFalse(verified_lfs_changes(self.root, "M  image.gif\x00"))
        self.assertFalse(verified_lfs_changes(self.root, "D  image.gif\x00"))

    def test_feature_classification_keeps_safety_and_local_separate(self):
        repository = {"repository": "MicrosoftDocs/azure-ai-docs", "family": "01-master-indexes"}
        self.assertEqual(classify_family(repository, "articles/ai-services/content-safety/overview.md"), "08-trustworthy-ai")
        self.assertEqual(classify_family(repository, "articles/foundry-local/get-started.md"), "11-foundry-local")
        self.assertEqual(classify_family(repository, "articles/foundry/agents/concepts/hosted-agents.md"), "04-agents")


if __name__ == "__main__":
    unittest.main()