from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import re

import azure.functions as func
from azure.identity import ManagedIdentityCredential

from azure_extraction.auth import AuthenticationError, JwtGate
from azure_extraction.contracts import METHODS, Refusal, documents_from_manifest, validate_endpoint
from azure_extraction.jobs import BlobJobStore, ExtractionJobs, JobConflict, MissingJob
from azure_extraction.provider import NativeProvider, ProviderError


_runtime = None


def runtime():
    global _runtime
    if _runtime is None:
        config = json.loads((Path(__file__).parent / "experiment.json").read_text())
        client_id = os.environ["AZURE_CLIENT_ID"]
        credential = ManagedIdentityCredential(client_id=client_id)
        gate = JwtGate(config["tenant_id"], config["operator_principal_id"], config["api_client_id"])
        documents = documents_from_manifest(json.loads((Path(__file__).parent / "input-manifest.json").read_text()))
        provider = NativeProvider(credential, config["cu_host"])
        store = BlobJobStore(f"https://{config['storage_name']}.blob.core.windows.net", credential)
        _runtime = (config, gate, ExtractionJobs(documents, provider, store), client_id)
    return _runtime


def response(body: dict, status: int = 200, headers: dict | None = None) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False), status_code=status, mimetype="application/json",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff", **(headers or {})},
    )


def extract(request: func.HttpRequest) -> func.HttpResponse:
    try:
        config, gate, jobs, client_id = runtime()
        claims = gate.authenticate(request.headers.get("Authorization"))
        path = urlsplit(request.url).path
        route = path.removeprefix("/api/") if path.startswith("/api/") else ""
        if request.params:
            raise Refusal("Query-supplied targets and options are not accepted")
        if request.method == "GET" and route == "health":
            return response({"status": "ready", "execution": "azure-function", "methods": METHODS,
                             "caller_principal_id": claims["oid"], "tenant_id": claims["tid"],
                             "workload_client_id": client_id})
        match = re.fullmatch(r"extract/([a-z-]+)/(yallourn|murray)/([a-f0-9-]+)", route)
        if request.method == "POST" and match:
            if request.headers.get("Content-Type", "").split(";", 1)[0] != "application/pdf":
                raise Refusal("Only application/pdf request bodies are accepted")
            method, document_id, job_id = match.groups()
            result = jobs.begin(method, document_id, job_id, request.get_body(), claims["oid"])
            endpoint = validate_endpoint(config["function_endpoint"], config["function_host"])
            status = 202 if result["status"] == "Running" else 200
            return response(result, status, {"Operation-Location": f"{endpoint}/api/jobs/{job_id}", "Retry-After": "2"})
        match = re.fullmatch(r"jobs/([a-f0-9-]+)", route)
        if request.method == "GET" and match:
            return response(jobs.poll(match.group(1), claims["oid"]), headers={"Retry-After": "2"})
        return response({"error": {"type": "NotFound", "message": "Unknown route"}}, 404)
    except AuthenticationError:
        return response({"error": {"type": "Unauthorized", "message": "Valid Entra API token required"}}, 401,
                        {"WWW-Authenticate": "Bearer"})
    except MissingJob:
        return response({"error": {"type": "NotFound", "message": "Job not found"}}, 404)
    except JobConflict as error:
        return response({"error": {"type": "Conflict", "message": str(error)}}, 409)
    except Refusal as error:
        return response({"error": {"type": "Refused", "message": str(error)}}, 403)
    except ProviderError as error:
        return response({"error": {"type": type(error).__name__, "message": str(error)}}, 502)
    except Exception as error:
        return response({"error": {"type": type(error).__name__, "message": "Extraction request failed; no empty success"}}, 500)