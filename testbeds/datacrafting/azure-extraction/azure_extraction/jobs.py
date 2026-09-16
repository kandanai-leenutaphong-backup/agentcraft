from datetime import datetime, timezone
from importlib.metadata import version
from typing import Any
import json
import platform

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceModifiedError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings

from .contracts import Refusal, require_content, require_method, validate_input
from .provider import ProviderError, canonical_job_id


class MissingJob(Refusal):
    pass


class JobConflict(Refusal):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def versions() -> dict:
    return {"python": platform.python_version(), **{name: version(name) for name in (
        "azure-core", "azure-identity", "azure-functions", "azure-storage-blob", "PyJWT"
    )}}


class BlobJobStore:
    def __init__(self, account_url: str, credential: Any):
        self.client = BlobServiceClient(account_url, credential=credential, logging_enable=False,
                                       connection_timeout=10, read_timeout=30, retry_total=2)
        self.container = self.client.get_container_client("jobs")

    def blob(self, job_id: str, filename: str):
        return self.container.get_blob_client(f"{canonical_job_id(job_id)}/{filename}")

    def create(self, state: dict) -> bool:
        try:
            self.blob(state["id"], "state.json").upload_blob(
                json.dumps(state).encode(), overwrite=False, content_settings=ContentSettings(content_type="application/json")
            )
            return True
        except ResourceExistsError:
            return False

    def read(self, job_id: str) -> tuple[dict, str]:
        try:
            download = self.blob(job_id, "state.json").download_blob()
            return json.loads(download.readall()), download.properties.etag
        except ResourceNotFoundError as error:
            raise MissingJob("Job not found") from error

    def replace(self, state: dict, etag: str) -> None:
        try:
            self.blob(state["id"], "state.json").upload_blob(
                json.dumps(state).encode(), overwrite=True, etag=etag, match_condition=MatchConditions.IfNotModified,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except ResourceModifiedError:
            current, _ = self.read(state["id"])
            if current != state:
                raise JobConflict("Job changed concurrently; read status before retrying")

    def save_native(self, job_id: str, native: dict) -> None:
        data = json.dumps(native, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            self.blob(job_id, "native.json").upload_blob(
                data, overwrite=False, content_settings=ContentSettings(content_type="application/json")
            )
        except ResourceExistsError:
            if self.native(job_id) != native:
                raise JobConflict("Existing provider evidence cannot be overwritten")

    def native(self, job_id: str) -> dict:
        return json.loads(self.blob(job_id, "native.json").download_blob().readall())


class ExtractionJobs:
    def __init__(self, documents: dict, provider: Any, store: Any):
        self.documents = documents
        self.provider = provider
        self.store = store

    def owned(self, job_id: str, principal_id: str) -> tuple[dict, str]:
        canonical_job_id(job_id)
        state, etag = self.store.read(job_id)
        if state["principal_id"] != principal_id:
            raise MissingJob("Job not found")
        return state, etag

    def begin(self, method: str, document_id: str, job_id: str, payload: bytes, principal_id: str) -> dict:
        require_method(method)
        canonical_job_id(job_id)
        if document_id not in self.documents:
            raise Refusal("Only authorized manifest document ids are accepted")
        document = self.documents[document_id]
        validate_input(payload, document)
        state = {"id": job_id, "method": method, "document_id": document_id, "principal_id": principal_id,
                 "sha256": document.sha256, "status": "Submitting", "started_at": utc_now(),
                 "provider": self.provider.descriptor(method), "versions": versions(), "error": None}
        if not self.store.create(state):
            previous, _ = self.owned(job_id, principal_id)
            if any(previous[key] != state[key] for key in ("method", "document_id", "sha256")):
                raise JobConflict("Idempotency key belongs to another extraction")
            return self.public(previous)
        state, etag = self.store.read(job_id)
        try:
            state["operation_id"] = self.provider.begin(method, payload)
            state["status"] = "Running"
        except ProviderError as error:
            state["status"] = "Failed" if error.status_code < 500 and error.status_code not in {408, 429} else "Unknown"
            state["error"] = {"type": type(error).__name__, "message": str(error)}
        except Exception as error:
            state["status"] = "Unknown"
            state["error"] = {"type": type(error).__name__, "message": "Provider submission could not be confirmed; no automatic resubmission"}
        self.store.replace(state, etag)
        return self.public(state)

    def poll(self, job_id: str, principal_id: str) -> dict:
        state, etag = self.owned(job_id, principal_id)
        if state["status"] == "Running":
            native = self.provider.poll(state["method"], state["operation_id"])
            provider_status = native["status"].lower()
            if provider_status in {"succeeded", "failed", "canceled"}:
                self.store.save_native(job_id, native)
                state["completed_at"] = utc_now()
                state["elapsed_seconds"] = (datetime.fromisoformat(state["completed_at"]) - datetime.fromisoformat(state["started_at"])).total_seconds()
                if provider_status == "succeeded":
                    try:
                        require_content(native, state["method"])
                        state["status"] = "Succeeded"
                    except Refusal as error:
                        state["status"] = "Failed"
                        state["error"] = {"type": "EmptyExtraction", "message": str(error)}
                else:
                    state["status"] = "Failed"
                    state["error"] = {"type": "ProviderOperationFailed", "message": "Native analysis did not succeed; inspect native.json"}
                self.store.replace(state, etag)
        return self.public(state)

    def public(self, state: dict) -> dict:
        response = {key: value for key, value in state.items() if key not in {"principal_id", "operation_id"}}
        if state["status"] in {"Submitting", "Unknown"}:
            response["status"] = "Failed"
            response["error"] = state["error"] or {"type": "UnconfirmedSubmission", "message": "Submission is unconfirmed; do not resubmit automatically"}
        if "completed_at" in state:
            response["native"] = self.store.native(state["id"])
        if state["status"] == "Succeeded":
            text, markdown, pages = require_content(response["native"], state["method"])
            response.update({"text": text, "markdown": markdown, "pages": pages})
        return response