import json
import tempfile
from types import SimpleNamespace
import unittest

from foundry_ops.core import (BoundExceededError, EvidenceLedger, RefusedError, UnresolvedIntentError,
                              VerificationError)
from foundry_ops.data import (dataset_version_label, eval_file_source, list_auto_datasets, optimization_dataset,
                              project_jsonl, readback_dataset, register_jsonl_dataset)
from foundry_ops.evaluation import agent_run_request, run_agent_eval
from foundry_ops.optimization import optimization_job

from fakes import Model, ResourceNotFoundError

ARM = "/subscriptions/p/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct"
HOST = "https://acct.blob.core.windows.net"
SAS = "sig=SECRETSIG"
ROWS = [{"query": "q1", "ground_truth": "a1", "case": "ok"}, {"query": "q2", "ground_truth": "a2", "zone": "Z"}]
PREFIX = "azureai://accounts/a/projects/p/data/"


class Container:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def upload_blob(self, *, name, data, overwrite, max_concurrency):
        assert overwrite is False and max_concurrency == 1
        if name in self.store.blobs:
            raise RuntimeError("BlobAlreadyExists")
        self.store.blobs[name] = bytes(data)
        return SimpleNamespace(url=f"{HOST}/cont/{name}")

    def get_blob_client(self, name):
        data = self.store.blobs[name]
        return SimpleNamespace(get_blob_properties=lambda: SimpleNamespace(size=len(data)),
                               download_blob=lambda offset, length, max_concurrency: SimpleNamespace(
                                   readall=lambda: data[offset:offset + length]))


class Datasets:
    def __init__(self):
        self.versions, self.blobs, self.calls, self.listing = {}, {}, [], []

    def _reference(self):
        credential = SimpleNamespace(sas_uri=f"{HOST}/cont?{SAS}", type="SAS")
        return SimpleNamespace(blob_uri=f"{HOST}/cont/pre", storage_account_arm_id=ARM, credential=credential)

    def get(self, *, name, version):
        self.calls.append(("get", name, version))
        if (name, version) not in self.versions:
            raise ResourceNotFoundError("Could not find asset")
        return self.versions[(name, version)]

    def pending_upload(self, *, name, version, pending_upload_request):
        self.calls.append(("pending_upload", name, version, pending_upload_request))
        return SimpleNamespace(blob_reference=self._reference())

    def create_or_update(self, *, name, version, dataset_version):
        self.calls.append(("create_or_update", name, version, dataset_version))
        model = SimpleNamespace(id=f"{PREFIX}{name}/versions/{version}", data_uri=dataset_version["dataUri"],
                                tags=dataset_version.get("tags"))
        self.versions[(name, version)] = model
        return model

    def get_credentials(self, *, name, version):
        self.calls.append(("get_credentials", name, version))
        return SimpleNamespace(blob_reference=self._reference())

    def list(self):
        return iter(self.listing)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(self.temp.name)
        self.datasets = Datasets()
        self.project = SimpleNamespace(datasets=self.datasets)
        self.factory = lambda sas: Container(self.datasets)

    def tearDown(self):
        self.temp.cleanup()

    def register(self, **changes):
        options = {"name": "train", "rows": ROWS, "fields": ["query", "ground_truth"],
                   "container_factory": self.factory, **changes}
        return register_jsonl_dataset(self.project, self.ledger, **options)

    def test_project_jsonl_is_canonical_and_projected(self):
        data = project_jsonl(ROWS, fields=["query", "ground_truth"])
        self.assertEqual(data, b'{"ground_truth":"a1","query":"q1"}\n{"ground_truth":"a2","query":"q2"}\n')
        self.assertEqual(project_jsonl([{"b": 1, "a": 2}]), b'{"a":2,"b":1}\n')
        for rows, fields in (([], None), ({"query": "q"}, None), ([{"x": 1}], ["query"]), (ROWS, []),
                             (ROWS, ["query", "query"]), ([{"q": float("nan")}], None), (["text"], None)):
            with self.assertRaises(RefusedError):
                project_jsonl(rows, fields=fields)

    def test_version_label(self):
        sha = "a" * 64
        self.assertEqual(dataset_version_label(sha), "sha256-" + "a" * 32)
        self.assertLessEqual(len(dataset_version_label(sha)), 50)
        for bad in ("A" * 64, "a" * 63, None, "sha256-" + "a" * 64):
            with self.assertRaises(RefusedError):
                dataset_version_label(bad)

    def test_register_stages_then_reads_back(self):
        result = self.register()
        data = project_jsonl(ROWS, fields=["query", "ground_truth"])
        from foundry_ops.core import sha256_hex
        self.assertEqual(result["sha256"], sha256_hex(data))
        self.assertEqual(result["version"], dataset_version_label(result["sha256"]))
        self.assertEqual((result["bytes"], result["rows"], result["reused"]), (len(data), 2, False))
        self.assertEqual(result["id"], f"{PREFIX}train/versions/{result['version']}")
        self.assertEqual(result["data_uri"], f"{HOST}/cont/pre/train.jsonl")
        self.assertEqual(self.datasets.blobs["pre/train.jsonl"], data)
        operations = [call[0] for call in self.datasets.calls]
        self.assertEqual(operations, ["get", "pending_upload", "create_or_update", "get", "get_credentials"])
        body = self.datasets.calls[2][3]
        self.assertEqual(body, {"type": "uri_file", "dataUri": result["data_uri"], "tags": {"sha256": result["sha256"]}})
        key = f"dataset-train-{result['version']}"
        for stage in ("upload", "blob", "registration"):
            self.assertTrue(self.ledger.exists(f"{key}-{stage}-intent.json"))
        self.assertEqual(self.ledger.read(f"{key}-result.json")["id"], result["id"])

    def test_reuse_identical_and_refuse_different_bytes(self):
        first = self.register()
        again = self.register()
        self.assertTrue(again["reused"])
        self.assertEqual({k: v for k, v in again.items() if k != "reused"},
                         {k: v for k, v in first.items() if k != "reused"})
        self.assertEqual([call[0] for call in self.datasets.calls].count("pending_upload"), 1)
        with self.assertRaises(VerificationError) as caught:
            self.register(rows=[{"query": "other"}], version=first["version"])
        self.assertEqual(caught.exception.code, "dataset_sha_mismatch")

    def test_version_over_fifty_refused_before_any_call(self):
        with self.assertRaises(RefusedError):
            self.register(version="v" * 51)
        with self.assertRaises(RefusedError):
            self.register(version="bad/version")
        self.assertEqual(self.datasets.calls, [])

    def test_sas_never_persisted(self):
        result = self.register()
        self.register()
        self.assertNotIn("sig=", json.dumps(result))
        for name in self.ledger.list():
            self.assertNotIn(b"SECRETSIG", self.ledger.path(name).read_bytes(), name)
            self.assertNotIn(b"sig=", self.ledger.path(name).read_bytes(), name)

    def test_dangling_intent_refuses_replay(self):
        failing = lambda sas: (_ for _ in ()).throw(RuntimeError("transport"))
        with self.assertRaises(RuntimeError):
            self.register(container_factory=failing)
        with self.assertRaises(UnresolvedIntentError):
            self.register()
        self.assertEqual([call[0] for call in self.datasets.calls].count("pending_upload"), 1)

    def test_readback_refusals(self):
        result = self.register()
        options = {"name": "train", "version": result["version"], "container_factory": self.factory}
        read = readback_dataset(self.project, expected_sha256=result["sha256"], **options)
        self.assertEqual((read["remote_bytes_verified"], read["bytes"], read["id"]), (True, result["bytes"], result["id"]))
        self.assertNotIn("sig=", json.dumps(read))
        with self.assertRaises(RefusedError) as caught:
            readback_dataset(self.project, name="train", version="sha256-" + "0" * 32, expected_sha256=result["sha256"],
                             container_factory=self.factory)
        self.assertEqual(caught.exception.code, "dataset_not_found")
        with self.assertRaises(VerificationError):
            readback_dataset(self.project, expected_sha256="b" * 64, **options)
        self.datasets.blobs["pre/train.jsonl"] += b"x"
        self.datasets.versions[("train", result["version"])].tags = None
        with self.assertRaises(VerificationError):
            readback_dataset(self.project, expected_sha256=result["sha256"], **options)
        with self.assertRaises(BoundExceededError):
            readback_dataset(self.project, expected_sha256=result["sha256"], max_bytes=4, **options)

    def test_foreign_storage_refused(self):
        foreign = SimpleNamespace(blob_uri="https://evil.example/cont/pre", storage_account_arm_id=ARM,
                                  credential=SimpleNamespace(sas_uri=f"{HOST}/cont?{SAS}"))
        self.datasets._reference = lambda: foreign
        with self.assertRaises(VerificationError):
            self.register()
        self.assertEqual(self.datasets.blobs, {})

    def test_reference_shapes_and_request_parity(self):
        ref = self.register()
        self.assertEqual(eval_file_source(ref), {"type": "file_id", "id": ref["id"]})
        self.assertEqual(optimization_dataset(ref), {"type": "reference", "name": "train", "version": ref["version"]})
        request = agent_run_request("e", name="n", agent_name="a", agent_version="3", dataset=ref)
        self.assertEqual(request["data_source"]["source"], eval_file_source(ref))
        job = optimization_job("a", "1", train_dataset=ref, validation_dataset=ref, evaluators=[{"name": "x", "version": "1"}],
                               optimization_model="m", max_candidates=3)
        self.assertEqual(job["inputs"]["train_dataset"], optimization_dataset(ref))
        self.assertEqual(job["inputs"]["validation_dataset"], optimization_dataset(ref))
        mixed = optimization_job("a", "1", train_dataset=ref, validation_items=[{"query": "q"}],
                                 evaluators=[{"name": "x", "version": "1"}], optimization_model="m", max_candidates=1)
        self.assertEqual(mixed["inputs"]["validation_dataset"]["type"], "inline")
        for bad in ({"name": "train"}, {"name": "train", "version": "v" * 51}, {"version": "1"}):
            with self.assertRaises(RefusedError):
                optimization_dataset(bad)
        for bad in ({"id": "file-123"}, {}):
            with self.assertRaises(RefusedError):
                eval_file_source(bad)

    def test_mutually_exclusive_sources(self):
        ref = {"id": PREFIX + "v/versions/1", "name": "v", "version": "1", "rows": 2}
        for sources in ({}, {"items": [{"query": "q"}], "dataset": ref}, {"file_id": "f", "dataset": ref},
                        {"items": [{"query": "q"}], "file_id": "f"}, {"dataset": {"id": "file-1"}}):
            with self.assertRaises(RefusedError):
                agent_run_request("e", name="n", agent_name="a", agent_version="3", **sources)
        evaluator = [{"name": "x", "version": "1"}]
        for splits in ({"train_items": [{"query": "q"}], "train_dataset": ref, "validation_dataset": ref},
                       {"validation_dataset": ref}, {"train_dataset": {"name": "v"}, "validation_dataset": ref}):
            with self.assertRaises(RefusedError):
                optimization_job("a", "1", evaluators=evaluator, optimization_model="m", max_candidates=1, **splits)
        common = {"key": "k", "name": "n", "agent_name": "a", "agent_version": "3",
                  "testing_criteria": [{"name": "c", "type": "azure_ai_evaluator"}]}
        for sources in ({}, {"items": [{"query": "q"}], "dataset": ref}, {"dataset": ref},
                        {"dataset": dict(ref, rows=None), "item_schema": {"type": "object"}}):
            with self.assertRaises(RefusedError):
                run_agent_eval(None, self.ledger, **common, **sources)

    def test_list_auto_datasets_read_only(self):
        self.datasets.listing = [
            Model(name="eval-data-2026-09-24_093244_bd1ff_UTC", version="1", id="i1", systemData={"createdAt": "t"}),
            Model(name="opt-inline-640e", version="1", id="i2", description="Auto-created"),
            Model(name="agentcraft-pkg-e2e-train", version="sha256-x", id="i3")]
        found = list_auto_datasets(self.project)
        self.assertEqual([item["name"] for item in found], ["eval-data-2026-09-24_093244_bd1ff_UTC", "opt-inline-640e"])
        self.assertEqual(found[0]["created_at"], "t")
        self.assertEqual([item["name"] for item in list_auto_datasets(self.project, prefixes=("opt-inline-",))],
                         ["opt-inline-640e"])
        with self.assertRaises(BoundExceededError):
            list_auto_datasets(self.project, limit=2)
        with self.assertRaises(RefusedError):
            list_auto_datasets(self.project, prefixes=())
        self.assertEqual(self.datasets.calls, [])


if __name__ == "__main__":
    unittest.main()
