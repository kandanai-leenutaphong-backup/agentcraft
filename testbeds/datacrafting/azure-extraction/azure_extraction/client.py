from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4
import argparse
import json
import platform
import subprocess

from azure.core import PipelineClient
from azure.core.pipeline.policies import BearerTokenCredentialPolicy, RequestIdPolicy, RetryPolicy
from azure.core.polling import LROPoller
from azure.core.polling.base_polling import LROBasePolling
from azure.core.rest import HttpRequest
from azure.identity import AzureCliCredential

from .contracts import Refusal, artifact_path, documents_from_manifest, require_content, require_method, validate_endpoint, validate_input
from .provider import CU_API_VERSION


ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


class FunctionPolling(LROBasePolling):
    def __init__(self, endpoint: str, job_id: str, limit_seconds: int = 900):
        super().__init__(timeout=2)
        self.expected_url = f"{endpoint}/api/jobs/{job_id}"
        self.deadline = monotonic() + limit_seconds
        self.last_payload = None
        self.poll_count = 0

    def request_status(self, status_link):
        if status_link != self.expected_url or urlsplit(status_link).scheme != "https":
            raise Refusal("Function polling location escaped the frozen target")
        if monotonic() >= self.deadline:
            raise TimeoutError("Function polling reached its bounded deadline; inspect the recorded job id before retrying")
        result = super().request_status(status_link)
        self.poll_count += 1
        self.last_payload = result.http_response.json()
        return result


def account_matches(config: dict) -> None:
    result = subprocess.run(
        ["az", "account", "show", "--query", "{subscriptionId:id,tenantId:tenantId,cloud:environmentName}", "-o", "json"],
        capture_output=True, text=True, check=True,
    )
    if json.loads(result.stdout) != {"subscriptionId": config["subscription_id"], "tenantId": config["tenant_id"], "cloud": config["cloud"]}:
        raise Refusal("Active Azure CLI target differs from this experiment")


def function_client(config: dict) -> PipelineClient:
    account_matches(config)
    endpoint = validate_endpoint(config["function_endpoint"], config["function_host"])
    credential = AzureCliCredential(subscription=config["subscription_id"], process_timeout=30)
    return PipelineClient(
        base_url=endpoint,
        policies=[RequestIdPolicy(), RetryPolicy(retry_total=0), BearerTokenCredentialPolicy(credential, f"api://{config['api_client_id']}/.default")],
        connection_timeout=15, read_timeout=120,
    )


def invoke(config: dict, method: str, document_id: str, payload: bytes, job_id: str, client=None) -> tuple[dict, int]:
    require_method(method)
    if document_id not in {"yallourn", "murray"}:
        raise Refusal("Unapproved document id")
    endpoint = validate_endpoint(config["function_endpoint"], config["function_host"])
    client = client or function_client(config)
    request = HttpRequest(
        "POST", f"{endpoint}/api/extract/{method}/{document_id}/{job_id}",
        headers={"Content-Type": "application/pdf", "Accept": "application/json"}, content=payload,
    )
    initial = client.send_request(request, _return_pipeline_response=True)
    response = initial.http_response
    if response.status_code not in {200, 202}:
        raise Refusal(f"Authenticated function returned HTTP {response.status_code}; no extraction success")
    first = response.json()
    if response.status_code == 200:
        return first, 0
    polling = FunctionPolling(endpoint, job_id)
    if response.headers.get("Operation-Location") != polling.expected_url:
        raise Refusal("Function supplied an unexpected operation location")
    poller = LROPoller(client, initial, lambda result: result.http_response.json(), polling)
    try:
        result = poller.result()
    except Exception:
        if isinstance(polling.last_payload, dict) and polling.last_payload.get("status") == "Failed":
            return polling.last_payload, polling.poll_count
        raise
    return result, polling.poll_count


def save_result(directory: Path, result: dict, receipt: dict) -> None:
    if isinstance(result.get("native"), dict):
        write_json(directory / "native.json", result["native"])
        receipt["outputs"]["native"] = artifact_path("native.json")
    if result.get("status") != "Succeeded":
        error = result.get("error") or {"type": "FunctionOperationFailed", "message": "Function operation did not succeed"}
        receipt["error"] = {"type": str(error.get("type", "FunctionOperationFailed"))[:160],
                            "message": str(error.get("message", "Operation failed"))[:600]}
        return
    text, markdown, pages = require_content(result["native"], receipt["method"])
    if result.get("text") != text or result.get("markdown") != markdown or result.get("pages") != pages:
        raise Refusal("Function artifacts disagree with complete native evidence")
    (directory / "content.txt").write_text(text, encoding="utf-8")
    receipt["outputs"]["text"] = artifact_path("content.txt")
    if markdown is not None:
        (directory / "content.md").write_text(markdown, encoding="utf-8")
        receipt["outputs"]["markdown"] = artifact_path("content.md")
    receipt["input"]["pages"] = pages
    receipt["status"] = "succeeded"
    receipt["provider"] = result["provider"]
    receipt["versions"].update({f"function:{key}": value for key, value in result["versions"].items()})
    receipt["warnings"].append("Native prebuilt-layout only; no generative fields, summaries, or figure descriptions requested.")


def run_cli(method: str) -> int:
    require_method(method)
    parser = argparse.ArgumentParser(description=f"Invoke authenticated Azure Function: {method}")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    allowed_root = (ROOT / method / "results").resolve()
    if directory == allowed_root or not directory.is_relative_to(allowed_root):
        parser.error("Output must be a new directory inside this method's results root")
    directory.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc)
    clock = monotonic()
    receipt = {
        "schema_version": 1, "method": method, "execution": "azure-function", "status": "failed",
        "input": {"file": args.input.name, "sha256": None, "bytes": None, "pages": None},
        "started_at": started.isoformat().replace("+00:00", "Z"), "elapsed_seconds": 0,
        "versions": {"python": platform.python_version(), "azure-core": version("azure-core"), "azure-identity": version("azure-identity")},
        "provider": {"api_version": CU_API_VERSION, "model_id": require_method(method)},
        "outputs": {"text": None, "markdown": None, "native": None}, "warnings": [], "error": None,
    }
    try:
        source_root = ROOT / "source_data"
        documents = documents_from_manifest(json.loads((source_root / "manifest.json").read_text()))
        matching = [document for document in documents.values() if (source_root / document.file).resolve() == args.input.resolve()]
        if len(matching) != 1:
            raise Refusal("Only the two immutable source_data PDFs may be uploaded")
        document = matching[0]
        payload = args.input.resolve().read_bytes()
        receipt["input"].update({"file": document.file, "sha256": sha256(payload).hexdigest(), "bytes": len(payload)})
        validate_input(payload, document)
        config = json.loads((ROOT / "deploy" / "env" / "runtime.json").read_text())
        job_id = str(uuid4())
        write_json(directory / "invocation.json", {"job_id": job_id, "method": method, "document_id": document.id,
            "function_endpoint": config["function_endpoint"], "input_sha256": document.sha256, "started_at": receipt["started_at"]})
        result, poll_count = invoke(config, method, document.id, payload, job_id)
        write_json(directory / "function.json", {key: value for key, value in result.items() if key not in {"native", "text", "markdown"}} | {"poll_count": poll_count})
        save_result(directory, result, receipt)
    except Exception as error:
        message = str(error)[:600] if isinstance(error, Refusal) else "Extraction failed; consult the recorded invocation and deployment evidence before retrying"
        receipt["error"] = {"type": type(error).__name__, "message": message}
    receipt["elapsed_seconds"] = round(monotonic() - clock, 6)
    write_json(directory / "receipt.json", receipt)
    print(json.dumps({"receipt": str(directory / "receipt.json"), "status": receipt["status"], "elapsed_seconds": receipt["elapsed_seconds"]}))
    return 0 if receipt["status"] == "succeeded" else 1