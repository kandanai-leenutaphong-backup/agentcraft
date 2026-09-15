"""The library's public surface: what resolves, what it costs to import, and what it is not.

Three things a consumer relies on and none of them are visible from a signature:

1. Importing the package costs the standard library and nothing else, so a module can
   name `ContentBounds` on a machine with no Azure SDK installed. The CRUD names resolve
   lazily and fail exactly as the connector's own package did.
2. Azure AI Search is re-exported from `template_foundations.azure_search`, not reimplemented.
   The assertion is identity: the same class object, one write path.
3. Nothing in the library imports the superseded `app.data.data_connectors` package. The
   scanner that proves it is itself proved against a fixture that does.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import template_foundations.azure_search as azure_search
import app.components.data_connector_library as library
from app.components.data_connector_library import (
    DEFAULT_BATCH,
    SEARCH_SCOPE,
    FieldSpec,
    IndexSpec,
    SearchConfig,
    SearchError,
    SearchIndexClient,
    Transport,
    render_index,
    safe_key,
    valid_index_name,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LIBRARY = REPO_ROOT / "app" / "components" / "data_connector_library"
SUPERSEDED = "app.data.data_connectors"

#: The names the superseded `adx_connector` and `gremlin_connector` barrels exported, plus
#: the four the public API returns or accepts and which a caller therefore cannot annotate
#: without. Read from those barrels, not invented here.
CONNECTOR_SURFACE = (
    "AdxClient", "AdxConfig", "AdxConnector", "AdxAuthError", "AdxConfigError", "AdxError",
    "AdxIdentifierError", "AdxIngestionError", "AdxProvisioningError", "AdxQueryError",
    "AdxTimeoutError", "AdxProvisioner", "ColumnSpec", "IngestMode", "IngestResult",
    "QueryResult", "TableSchema",
    "DEFAULT_BATCH", "PROPERTY_TEXT_LIMIT", "GremlinError", "GremlinGraph", "GremlinSettings",
    "encode_properties",
    "CrudRepository", "UpsertStrategy", "Ingestor", "ClusterInfo",
)

SEARCH_SURFACE = (
    "SearchIndexClient", "SearchConfig", "SearchConfigError", "SearchError", "FieldSpec",
    "IndexSpec", "VectorSpec", "render_index", "safe_key", "valid_index_name",
    "SEARCH_SCOPE", "Transport", "DEFAULT_SEARCH_API_VERSION",
)

# Run in a fresh interpreter with every Azure SDK and gremlinpython made unimportable, so the
# result cannot depend on what happens to be installed on the machine running the suite.
BLOCKED_SDK_PROBE = '''
import sys

BLOCKED = ("azure", "gremlin_python")


class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("blocked by probe: " + name)
        return None


for loaded in [m for m in sys.modules if m.split(".")[0] in BLOCKED]:
    del sys.modules[loaded]
sys.meta_path.insert(0, Blocker())

import app.components.data_connector_library as library

leaked = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
assert not leaked, "importing the package pulled an SDK: " + repr(leaked)

from app.components.data_connector_library import (
    ContentBounds, GraphReader, GraphTarget, KustoReader, KustoTableInspector,
    SearchConfig, SearchIndexClient, SearchReader, safe_key,
)

ContentBounds(max_rows=5)
GraphTarget(account="a", database="d", graph="g")
GraphReader(resolve=lambda target: None)
KustoReader(credential_provider=lambda: None)
KustoTableInspector(credential_provider=lambda: None)
SearchReader(credential_provider=lambda: None)
SearchIndexClient(SearchConfig(endpoint="https://svc.search.windows.net"))
safe_key("docs/a.md")

for name in ("AdxConnector", "AdxClient", "Ingestor", "GremlinGraph"):
    try:
        getattr(library, name)
    except ImportError:
        continue
    if name == "GremlinGraph":
        continue  # its module is standard library; the driver loads in __init__
    raise AssertionError(name + " resolved with azure blocked")

print("OK")
'''


def superseded_imports(tree: Path) -> list[str]:
    """Every `path:line` under ``tree`` that imports the superseded connector package."""
    found: list[str] = []
    for path in sorted(tree.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and SUPERSEDED in stripped:
                found.append(f"{path}:{number}")
    return found


class PublicSurfaceTests(unittest.TestCase):
    def test_every_declared_name_resolves(self) -> None:
        unresolved = [name for name in library.__all__ if not hasattr(library, name)]
        self.assertEqual(unresolved, [])

    def test_the_superseded_connector_surface_is_reachable_from_the_barrel(self) -> None:
        for name in CONNECTOR_SURFACE:
            with self.subTest(name=name):
                self.assertIn(name, library.__all__)
                self.assertTrue(hasattr(library, name))

    def test_the_search_surface_is_reachable_from_the_barrel(self) -> None:
        for name in SEARCH_SURFACE:
            with self.subTest(name=name):
                self.assertIn(name, library.__all__)

    def test_dir_reports_the_lazy_names_too(self) -> None:
        """Without __dir__, tab completion and inspect would show only the eager half."""
        self.assertEqual(sorted(library.__all__), sorted(dir(library)))

    def test_default_batch_is_the_gremlin_one_and_search_keeps_its_own(self) -> None:
        self.assertEqual(DEFAULT_BATCH, 20)
        self.assertEqual(azure_search.client.DEFAULT_BATCH, 50)
        self.assertNotIn("DEFAULT_BATCH", azure_search.__all__)


class LazyImportTests(unittest.TestCase):
    def test_importing_the_package_pulls_no_sdk_and_readers_still_build(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c", BLOCKED_SDK_PROBE],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("OK", completed.stdout)

    def test_an_undeclared_name_is_an_attribute_error_not_an_import(self) -> None:
        with self.assertRaises(AttributeError):
            library.NotAThing  # noqa: B018


class SearchReuseTests(unittest.TestCase):
    """One implementation. The library makes it reachable; it does not restate it."""

    def test_the_exported_objects_are_the_azure_search_objects(self) -> None:
        for name in SEARCH_SURFACE:
            with self.subTest(name=name):
                self.assertIs(getattr(library, name), getattr(azure_search, name))

    def test_no_second_write_path_was_written_here(self) -> None:
        self.assertEqual(SearchIndexClient.__module__, "template_foundations.azure_search.client")
        self.assertEqual(render_index.__module__, "template_foundations.azure_search.schema")
        defined_here = [
            f"{path}:{number}"
            for path in sorted(LIBRARY.rglob("*.py"))
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if line.startswith(("class SearchIndexClient", "def render_index", "class Transport"))
        ]
        self.assertEqual(defined_here, [])

    def test_the_scope_is_the_search_audience_not_a_local_constant(self) -> None:
        self.assertEqual(SEARCH_SCOPE, "https://search.azure.com/.default")


class FakeService:
    """Replies from a scripted queue, else an empty result. Records every request."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, Any]] = []
        self.scripted: list[tuple[int, Any]] = []

    def script(self, status: int, body: Any) -> None:
        self.scripted.append((status, body))

    def opener(self, request: Any, timeout: float) -> tuple[int, bytes]:
        body = json.loads(request.data.decode()) if request.data else None
        self.requests.append((request.get_method(), request.full_url, body))
        assert request.get_header("Authorization", "").startswith("Bearer ")
        if self.scripted:
            status, payload = self.scripted.pop(0)
            return status, b"" if payload is None else json.dumps(payload).encode()
        return 200, json.dumps({"value": []}).encode()


class FakeCredential:
    def get_token(self, scope: str) -> Any:
        return SimpleNamespace(token="probe-token", expires_on=2**31)


def client_over(service: FakeService) -> SearchIndexClient:
    return SearchIndexClient(
        SearchConfig(endpoint="https://svc.search.windows.net", max_attempts=1),
        Transport(credential=FakeCredential(), opener=service.opener, sleep=lambda _: None),
    )


def handbook() -> IndexSpec:
    return IndexSpec(
        name="handbook",
        purpose="Retrieval for operator answers.",
        fields=(
            FieldSpec("id", key=True, filterable=True),
            FieldSpec("title", searchable=True),
        ),
    )


class SearchCrudThroughTheBarrelTests(unittest.TestCase):
    """The CRUD a consumer will run, driven through the library's exports."""

    def test_create_read_and_query_an_index(self) -> None:
        service = FakeService()
        client = client_over(service)
        service.script(201, {"name": "handbook"})
        self.assertEqual(client.create_or_update_index(handbook())["name"], "handbook")

        service.script(200, {"name": "handbook", "fields": []})
        self.assertEqual(client.get_index("handbook")["name"], "handbook")

        service.script(200, {"value": [{"id": "a", "@search.score": 1.0}]})
        self.assertEqual(client.search("handbook", "credential logon", top=3)[0]["id"], "a")

        methods = [method for method, _, _ in service.requests]
        self.assertEqual(methods, ["PUT", "GET", "POST"])

    def test_an_absent_index_reads_as_none_rather_than_raising(self) -> None:
        service = FakeService()
        service.script(404, {"error": {"message": "not found"}})
        self.assertIsNone(client_over(service).get_index("handbook"))

    def test_upload_and_delete_report_what_landed(self) -> None:
        service = FakeService()
        client = client_over(service)
        service.script(200, {"value": [{"key": "a", "status": True, "statusCode": 201}]})
        uploaded = client.upload_documents("handbook", [{"id": safe_key("docs/a.md")}])
        self.assertEqual((uploaded["action"], uploaded["succeeded"], uploaded["failed"]),
                         ("mergeOrUpload", 1, 0))

        service.script(200, {"value": [{"key": "a", "status": True, "statusCode": 200}]})
        deleted = client.delete_documents("handbook", "id", ["a"])
        self.assertEqual((deleted["action"], deleted["succeeded"]), ("delete", 1))

    def test_a_207_partial_success_raises_with_the_failed_key(self) -> None:
        """The service reports per-document failure inside a 2xx; trusting the status loses data."""
        service = FakeService()
        service.script(207, {"value": [
            {"key": "a", "status": True, "statusCode": 200},
            {"key": "b", "status": False, "statusCode": 404, "errorMessage": "index not found"},
        ]})
        with self.assertRaises(SearchError) as caught:
            client_over(service).upload_documents("handbook", [{"id": "a"}, {"id": "b"}])
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.body["succeeded"], 1)
        self.assertEqual(caught.exception.body["failures"][0]["key"], "b")

    def test_an_index_name_the_service_would_reject_never_reaches_a_url(self) -> None:
        service = FakeService()
        self.assertFalse(valid_index_name("Hand_Book"))
        with self.assertRaises(azure_search.SearchConfigError):
            client_over(service).get_index("Hand_Book")
        self.assertEqual(service.requests, [])


class BoundaryTests(unittest.TestCase):
    def test_the_library_imports_nothing_from_the_superseded_package(self) -> None:
        self.assertEqual(superseded_imports(LIBRARY), [])

    def test_no_python_under_app_or_deploy_imports_the_superseded_package(self) -> None:
        offenders = [hit for tree in (REPO_ROOT / "app", REPO_ROOT / "deploy")
                     for hit in superseded_imports(tree)]
        self.assertEqual(offenders, [])

    def test_the_scanner_catches_a_tree_that_does(self) -> None:
        """A clean result means nothing until the check is shown to fail on a real violation."""
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            (tree / "clean.py").write_text(
                "from app.components.data_connector_library import AdxConnector\n", encoding="utf-8")
            (tree / "violating.py").write_text(
                "import os\nfrom app.data.data_connectors.adx_connector import AdxConnector\n",
                encoding="utf-8")
            self.assertEqual(superseded_imports(tree), [f"{tree / 'violating.py'}:2"])


if __name__ == "__main__":
    unittest.main()
