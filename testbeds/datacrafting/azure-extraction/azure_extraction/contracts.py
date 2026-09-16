from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID
import re


METHODS = {
    "content-understanding": "prebuilt-layout",
}
MAX_INPUT_BYTES = 1_000_000


class Refusal(ValueError):
    pass


@dataclass(frozen=True)
class Document:
    id: str
    file: str
    sha256: str
    bytes: int


def documents_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Document]:
    if manifest.get("schema_version") != 1:
        raise Refusal("Unsupported input manifest version")
    documents = {}
    for entry in manifest.get("documents", []):
        identifier = entry.get("id", "")
        filename = entry.get("file", "")
        digest = entry.get("sha256", "")
        size = entry.get("bytes", 0)
        if identifier not in {"yallourn", "murray"} or identifier in documents:
            raise Refusal("Unexpected or duplicate document id")
        if not re.fullmatch(r"[a-z0-9-]+\.pdf", filename):
            raise Refusal("Input filename must be a plain PDF filename")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise Refusal("Input SHA-256 is invalid")
        if type(size) is not int or not 0 < size <= MAX_INPUT_BYTES:
            raise Refusal("Input size exceeds experiment bounds")
        documents[identifier] = Document(identifier, filename, digest, size)
    if set(documents) != {"yallourn", "murray"}:
        raise Refusal("Exactly the two authorized documents are required")
    return documents


def validate_input(payload: bytes, document: Document) -> None:
    if len(payload) != document.bytes or len(payload) > MAX_INPUT_BYTES:
        raise Refusal("Input byte count does not match the authorized manifest")
    if not payload.startswith(b"%PDF-") or sha256(payload).hexdigest() != document.sha256:
        raise Refusal("Input PDF digest does not match the authorized manifest")


def require_method(method: str) -> str:
    if method not in METHODS:
        raise Refusal("Unknown extraction method")
    return METHODS[method]


def authorize_verified_claims(
    claims: Mapping[str, Any], tenant_id: str, principal_id: str
) -> None:
    for identifier in (tenant_id, principal_id):
        if str(UUID(identifier)) != identifier:
            raise Refusal("Authorization configuration requires canonical UUIDs")
    if claims.get("tid") != tenant_id or claims.get("oid") != principal_id:
        raise Refusal("Caller is not on the experiment tenant/principal allowlist")


def validate_endpoint(endpoint: str, expected_host: str) -> str:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or parsed.netloc != expected_host
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-z0-9.-]+", expected_host)
    ):
        raise Refusal("Endpoint does not match the frozen HTTPS target")
    return endpoint.rstrip("/")


def artifact_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or str(path) != value
        or any(ord(character) < 32 for character in value)
        or ":" in value
    ):
        raise Refusal("Artifact path must remain inside the receipt directory")
    return value


def require_content(native: Mapping[str, Any], method: str) -> tuple[str, str | None, int]:
    require_method(method)
    contents = native.get("result", {}).get("contents", [])
    if not contents or not all(isinstance(content, dict) for content in contents):
        raise Refusal("Provider returned no document contents")
    text = "\n\n".join(content.get("markdown", "") for content in contents)
    pages = sum(len(content.get("pages", [])) for content in contents)
    if not isinstance(text, str) or not text.strip() or pages == 0:
        raise Refusal("Provider returned empty text or no observed pages")
    return text, text, pages