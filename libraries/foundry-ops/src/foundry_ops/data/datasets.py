"""Native Foundry Datasets for eval and optimization data: canonical JSONL, sha-pinned versions, byte read-back.

Staged native calls (`pending_upload` -> `upload_blob(overwrite=False)` -> `create_or_update` -> `get` ->
`get_credentials` byte read-back), each mutation behind a ledger intent. SAS URLs from `pending_upload` and
`get_credentials` stay in memory; records carry query-stripped URLs only. JSON bodies are passed to the SDK
so importing this module loads no Azure package; `azure.storage.blob` is imported only when uploading or
reading back without an injected `container_factory`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from ..core.errors import BoundExceededError, RefusedError, VerificationError
from ..core.identifiers import safe_identifier, validate_version_label
from ..core.records import EvidenceLedger, sha256_hex, to_plain

DATASET_VERSION_MAX = 50
AUTO_DATASET_PREFIXES = ("opt-inline-", "eval-data-")
MAX_DATASET_BYTES = 50_000_000
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_STORAGE_ARM = re.compile(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Storage/storageAccounts/"
                          r"([a-z0-9]{3,24})", re.IGNORECASE)
_CONTAINER = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])")

ContainerFactory = Callable[[str], Any]


def project_jsonl(rows: Iterable[Mapping[str, Any]], *, fields: Iterable[str] | None = None) -> bytes:
    """Canonical JSONL: one sorted-key compact object per line; `fields` keeps only those keys present."""
    if isinstance(rows, (Mapping, str, bytes)):
        raise RefusedError("dataset_rows", "pass an iterable of row objects")
    keep = None
    if fields is not None:
        keep = list(fields)
        if not keep or any(not isinstance(name, str) or not name for name in keep) or len(set(keep)) != len(keep):
            raise RefusedError("dataset_fields", "fields must be unique non-empty names")
    lines = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RefusedError("dataset_rows", "every row must be an object")
        projected = dict(row) if keep is None else {key: row[key] for key in keep if key in row}
        if not projected:
            raise RefusedError("dataset_rows", "row is empty after projection")
        try:
            lines.append(json.dumps(projected, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        except (TypeError, ValueError) as error:
            raise RefusedError("dataset_rows", "row is not JSON-serializable") from error
    if not lines:
        raise RefusedError("dataset_rows", "at least one row required")
    return "".join(lines).encode()


def dataset_version_label(sha256_hex_value: str) -> str:
    """`sha256-<first 32 hex>`: fits the 50-character registration limit; keep the full sha as the pin."""
    if not isinstance(sha256_hex_value, str) or not _SHA256.fullmatch(sha256_hex_value):
        raise RefusedError("dataset_sha256", "sha256 must be 64 lowercase hex characters")
    return "sha256-" + sha256_hex_value[:32]


def validate_dataset_version(version: Any) -> str:
    validate_version_label(version, DATASET_VERSION_MAX, what="dataset version", code="dataset_version")
    if not _VERSION.fullmatch(version):
        raise RefusedError("dataset_version", "dataset version has unsafe characters")
    return version


def eval_file_source(ref: Mapping[str, Any]) -> dict[str, str]:
    """Eval run `source` for a registered dataset version (`azureai://...` id); rows are bare items."""
    identifier = ref.get("id") if isinstance(ref, Mapping) else None
    if not isinstance(identifier, str) or not identifier.startswith("azureai://"):
        raise RefusedError("dataset_ref", "dataset reference needs an azureai:// version id")
    return {"type": "file_id", "id": identifier}


def optimization_dataset(ref: Mapping[str, Any]) -> dict[str, str]:
    """Optimization `train_dataset`/`validation_dataset` reference; version is required (omitted = latest)."""
    if not isinstance(ref, Mapping):
        raise RefusedError("dataset_ref", "dataset reference must be a mapping")
    return {"type": "reference", "name": safe_identifier(ref.get("name"), "dataset name"),
            "version": validate_dataset_version(ref.get("version"))}


def _clean_url(url: Any) -> str:
    if not isinstance(url, str):
        raise VerificationError("storage_url", "storage URL missing")
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))


def _storage_url(url: Any, arm_id: Any) -> tuple[str, list[str]]:
    """Query-stripped https blob URL on the account named by the ARM id, plus its decoded path parts."""
    match = _STORAGE_ARM.fullmatch(arm_id) if isinstance(arm_id, str) else None
    if match is None or not isinstance(url, str) or re.search(r"[\x00-\x20\\]", url):
        raise VerificationError("storage_identity", "untrusted storage identity or URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != match[1].lower() + ".blob.core.windows.net"
            or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment):
        raise VerificationError("storage_url", "storage URL outside the named account")
    parts = unquote(parsed.path, errors="strict").strip("/").split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise VerificationError("storage_url", "unsafe storage path")
    return _clean_url(url), parts


def _container_location(reference: Any) -> dict[str, Any]:
    arm = getattr(reference, "storage_account_arm_id", None)
    credential = getattr(reference, "credential", None)
    base, base_parts = _storage_url(getattr(credential, "sas_uri", None), arm)
    if len(base_parts) != 1 or not _CONTAINER.fullmatch(base_parts[0]) or "--" in base_parts[0]:
        raise VerificationError("storage_container", "credential must identify one container")
    return {"container": base, "container_name": base_parts[0], "storage_account_arm_id": arm,
            "sas_uri": credential.sas_uri}


def _blob_name(url: Any, location: Mapping[str, Any], *, allow_container: bool = False) -> str:
    clean, parts = _storage_url(url, location["storage_account_arm_id"])
    if urlsplit(clean).hostname != urlsplit(location["container"]).hostname or parts[0] != location["container_name"] \
            or (len(parts) < 2 and not allow_container):
        raise VerificationError("storage_container", "blob outside the credential container")
    return "/".join(parts[1:])


def _default_container_factory(sas_uri: str) -> Any:
    from azure.storage.blob import ContainerClient
    return ContainerClient.from_container_url(sas_uri, retry_total=0, connection_timeout=15, read_timeout=60)


def _not_found(error: BaseException) -> bool:
    return getattr(error, "status_code", None) == 404 or type(error).__name__ in {"ResourceNotFoundError",
                                                                                   "NotFoundError"}


def _get(project: Any, name: str, version: str) -> Any | None:
    try:
        return project.datasets.get(name=name, version=version)
    except Exception as error:
        if _not_found(error):
            return None
        raise


def readback_dataset(project: Any, *, name: str, version: str, expected_sha256: str,
                     container_factory: ContainerFactory | None = None,
                     max_bytes: int = MAX_DATASET_BYTES) -> dict[str, Any]:
    """`get` + `get_credentials` + blob bytes; refuses a missing version, foreign blob or sha mismatch.

    `get_credentials` mints a SAS (POST); it is used in memory and never returned.
    """
    safe_identifier(name, "dataset name")
    validate_dataset_version(version)
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise RefusedError("dataset_sha256", "expected sha256 must be 64 lowercase hex characters")
    dataset = _get(project, name, version)
    if dataset is None:
        raise RefusedError("dataset_not_found", f"dataset version not found: {name}@{version}")
    identifier = getattr(dataset, "id", None)
    if not isinstance(identifier, str) or not identifier.endswith(f"/data/{name}/versions/{version}"):
        raise VerificationError("dataset_identity", "dataset read-back identity mismatch")
    tags = getattr(dataset, "tags", None) or {}
    if tags.get("sha256") not in (None, expected_sha256):
        raise VerificationError("dataset_sha_mismatch", "registered sha256 tag differs from expected")
    reference = project.datasets.get_credentials(name=name, version=version).blob_reference
    location = _container_location(reference)
    blob_name = _blob_name(getattr(dataset, "data_uri", None), location)
    with (container_factory or _default_container_factory)(location["sas_uri"]) as container:
        blob = container.get_blob_client(blob_name)
        size = blob.get_blob_properties().size
        if type(size) is not int or size < 0 or size > max_bytes:
            raise BoundExceededError("dataset_size", "remote dataset size missing or over bound")
        content = blob.download_blob(offset=0, length=size, max_concurrency=1).readall() if size else b""
    if len(content) != size or sha256_hex(content) != expected_sha256:
        raise VerificationError("dataset_sha_mismatch", "remote dataset bytes differ from expected sha256")
    return {"id": identifier, "name": name, "version": version, "sha256": expected_sha256, "bytes": size,
            "remote_bytes_verified": True, "data_uri": _clean_url(dataset.data_uri),
            "storage_account_arm_id": location["storage_account_arm_id"]}


def register_jsonl_dataset(project: Any, ledger: EvidenceLedger, *, name: str, rows: Iterable[Mapping[str, Any]],
                           fields: Iterable[str] | None = None, version: str | None = None,
                           description: str | None = None, container_factory: ContainerFactory | None = None,
                           max_bytes: int = MAX_DATASET_BYTES) -> dict[str, Any]:
    """Register canonical JSONL once as `name@version` (default `dataset_version_label(sha)`), then read back.

    Existing version with the same bytes -> `reused: True`; different bytes -> refused. Records
    `dataset-<name>-<version>-{upload,blob,registration}-intent.json` before each mutation; a dangling intent
    refuses (reconcile by read-back, never replay). Returns id, name, version, sha256, bytes, rows,
    data_uri, reused.
    """
    safe_identifier(name, "dataset name")
    data = project_jsonl(rows, fields=fields)
    if len(data) > max_bytes:
        raise BoundExceededError("dataset_size", "dataset exceeds byte bound")
    digest = sha256_hex(data)
    version = validate_dataset_version(version if version is not None else dataset_version_label(digest))
    key = f"dataset-{name}-{version}"
    summary = {"name": name, "version": version, "sha256": digest, "bytes": len(data), "rows": data.count(b"\n")}
    options = {"container_factory": container_factory, "max_bytes": max_bytes}

    existing = _get(project, name, version)
    if existing is not None:
        readback = readback_dataset(project, name=name, version=version, expected_sha256=digest, **options)
        result = {**summary, "id": readback["id"], "data_uri": readback["data_uri"]}
        ledger.retain(f"{key}-result.json", result, allow_identical=True)
        return {**result, "reused": True}

    ledger.intent(f"{key}-upload", summary)
    pending = project.datasets.pending_upload(name=name, version=version,
                                              pending_upload_request={"pendingUploadType": "BlobReference"})
    reference = pending.blob_reference
    location = _container_location(reference)
    prefix = _blob_name(getattr(reference, "blob_uri", None), location, allow_container=True)
    blob_name = (prefix + "/" if prefix else "") + name + ".jsonl"
    with (container_factory or _default_container_factory)(location["sas_uri"]) as container:
        ledger.intent(f"{key}-blob", {**summary, "container": location["container"], "blob_name": blob_name,
                                      "storage_account_arm_id": location["storage_account_arm_id"]})
        blob = container.upload_blob(name=blob_name, data=data, overwrite=False, max_concurrency=1)
        data_uri = _clean_url(getattr(blob, "url", None))
        if _blob_name(data_uri, location) != blob_name:
            raise VerificationError("storage_container", "uploaded blob URL does not match its name")
    ledger.intent(f"{key}-registration", {**summary, "data_uri": data_uri})
    body = {"type": "uri_file", "dataUri": data_uri, "tags": {"sha256": digest}}
    if description is not None:
        body["description"] = description
    created = project.datasets.create_or_update(name=name, version=version, dataset_version=body)
    readback = readback_dataset(project, name=name, version=version, expected_sha256=digest, **options)
    if getattr(created, "id", None) not in (None, readback["id"]):
        raise VerificationError("dataset_identity", "registration and read-back identities differ")
    result = {**summary, "id": readback["id"], "data_uri": readback["data_uri"]}
    ledger.retain(f"{key}-result.json", result)
    return {**result, "reused": False}


def list_auto_datasets(project: Any, *, prefixes: Iterable[str] = AUTO_DATASET_PREFIXES,
                       limit: int = 5000) -> list[dict[str, Any]]:
    """Read-only inventory of service-created datasets (latest versions) whose names start with `prefixes`."""
    prefixes = tuple(prefixes)
    if not prefixes or any(not isinstance(prefix, str) or not prefix for prefix in prefixes):
        raise RefusedError("dataset_prefixes", "prefixes must be non-empty strings")
    found = []
    for index, model in enumerate(project.datasets.list()):
        if index >= limit:
            raise BoundExceededError("dataset_list", "dataset listing exceeded bound; inventory incomplete")
        item = to_plain(model)
        name = item.get("name") if isinstance(item, Mapping) else None
        if isinstance(name, str) and name.startswith(prefixes):
            system = item.get("systemData") or item.get("system_data") or {}
            found.append({"name": name, "version": item.get("version"), "id": item.get("id"),
                          "description": item.get("description"),
                          "created_at": system.get("createdAt") if isinstance(system, Mapping) else None})
    return sorted(found, key=lambda entry: (entry["name"], str(entry["version"])))
