from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID
import re

from azure.core import PipelineClient
from azure.core.pipeline.policies import BearerTokenCredentialPolicy, RetryPolicy
from azure.core.rest import HttpRequest

from .contracts import Refusal, require_method, validate_endpoint


CU_API_VERSION = "2025-11-01"
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


class ProviderError(RuntimeError):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", code) else "ProviderRequestFailed"
        super().__init__(f"Native service HTTP {status_code}: {self.code}")


def canonical_job_id(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as error:
        raise Refusal("Job and operation identifiers must be canonical UUIDs") from error
    return value


class NativeProvider:
    def __init__(self, credential: Any, cu_host: str, send: Any = None):
        self.service_endpoint = validate_endpoint(f"https://{cu_host}", cu_host)
        self.client = PipelineClient(
            base_url=self.service_endpoint,
            policies=[RetryPolicy(retry_total=0), BearerTokenCredentialPolicy(credential, COGNITIVE_SCOPE)],
            connection_timeout=15,
            read_timeout=90,
        )
        self.send = send or self.client.send_request

    def descriptor(self, method: str) -> dict:
        model_id = require_method(method)
        return {
            "api_version": CU_API_VERSION,
            "model_id": model_id,
        }

    def endpoint(self, method: str) -> str:
        require_method(method)
        return self.service_endpoint

    def operation_path(self, method: str, operation_id: str) -> str:
        require_method(method)
        canonical_job_id(operation_id)
        return f"/contentunderstanding/analyzerResults/{operation_id}"

    def operation_id(self, method: str, location: str) -> str:
        parsed = urlsplit(location)
        endpoint = urlsplit(self.endpoint(method))
        operation_id = canonical_job_id(parsed.path.rsplit("/", 1)[-1])
        if (
            parsed.scheme != endpoint.scheme
            or parsed.netloc != endpoint.netloc
            or parsed.path != self.operation_path(method, operation_id)
            or parse_qs(parsed.query) != {"api-version": [self.descriptor(method)["api_version"]]}
            or parsed.fragment
        ):
            raise Refusal("Native operation location escaped the frozen service target")
        return operation_id

    def checked(self, request: HttpRequest, expected: set[int]):
        response = self.send(request)
        if response.status_code not in expected:
            try:
                code = response.json().get("error", {}).get("code", "ProviderRequestFailed")
            except (ValueError, AttributeError):
                code = "ProviderRequestFailed"
            raise ProviderError(response.status_code, code)
        return response

    def begin(self, method: str, payload: bytes) -> str:
        descriptor = self.descriptor(method)
        path = f"/contentunderstanding/analyzers/{descriptor['model_id']}:analyzeBinary"
        query = f"api-version={descriptor['api_version']}"
        request = HttpRequest(
            "POST", f"{self.endpoint(method)}{path}?{query}",
            headers={"Content-Type": "application/pdf", "Accept": "application/json"}, content=payload,
        )
        response = self.checked(request, {202})
        return self.operation_id(method, response.headers.get("Operation-Location", ""))

    def poll(self, method: str, operation_id: str) -> dict:
        url = f"{self.endpoint(method)}{self.operation_path(method, operation_id)}?api-version={self.descriptor(method)['api_version']}"
        response = self.checked(HttpRequest("GET", url, headers={"Accept": "application/json", "x-ms-diagnostics": "true"}), {200})
        native = response.json()
        if not isinstance(native, dict) or str(native.get("status", "")).lower() not in {"notstarted", "running", "succeeded", "failed", "canceled"}:
            raise Refusal("Native service returned an unknown operation state")
        return native