from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .contracts import (
    ConfigurationError, ConnectorConfig, ContentValue, EVIDENCE, ErrorInfo, ItemResult,
    Limits, ProvisionRequest, RecordInput, RecordKey, Request, Requirements, SchemaRequest,
    Verification, VerificationResult, plain, serialized,
)
from .transport import OperationFault


def json_bytes(value: Any) -> bytes:
    def validate(item: Any, depth: int = 0) -> None:
        if depth > 32:
            raise OperationFault("invalid", "content_too_deep")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if isinstance(item, Mapping) and all(type(key) is str for key in item):
            for child in item.values():
                validate(child, depth + 1)
            return
        if isinstance(item, (tuple, list)):
            for child in item:
                validate(child, depth + 1)
            return
        raise OperationFault("invalid", "non_json_value")
    validate(value)
    try:
        return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise OperationFault("invalid", "non_json_value") from None


def content_bytes(value: ContentValue) -> bytes:
    if value.kind == "bytes" and isinstance(value.data, bytes):
        return value.data
    return json_bytes(serialized(value.data) if value.kind in {"entity", "row", "table"} else value.data)


def validate_request(operation: str, request: Request, limits: Limits, key_field: str,
                     partition_field: str | None, *, key_fields=None, content_kinds=("json",), scalar_keys=False) -> None:
    if (not isinstance(request.request_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request.request_id)):
        raise OperationFault("invalid", "invalid_request_id")
    if not isinstance(request.requirements, Requirements) or not isinstance(request.requirements.guarantees, tuple) or not all(
            isinstance(value, str) for value in request.requirements.guarantees):
        raise OperationFault("invalid", "invalid_requirements")
    verification = request.verification
    if (not isinstance(verification, Verification) or not isinstance(verification.kind, str) or verification.kind not in EVIDENCE
            or type(verification.attempts) is not int or not 1 <= verification.attempts <= 20
            or isinstance(verification.interval_seconds, bool) or not isinstance(verification.interval_seconds, (int, float))
            or not math.isfinite(verification.interval_seconds) or not 0 <= verification.interval_seconds <= 5):
        raise OperationFault("invalid", "invalid_verification")
    if not isinstance(request.service_options, Mapping):
        raise OperationFault("invalid", "invalid_service_options")
    total_bytes = len(json_bytes(request.service_options))
    records = getattr(request, "records", ())
    keys = getattr(request, "keys", ())
    if not isinstance(records, tuple) or not isinstance(keys, tuple) or len(records or keys) > limits.max_items:
        raise OperationFault("invalid", "item_limit")
    identifiers = set()
    required_keys = key_fields or (key_field,)
    for item in records or keys:
        if records and not isinstance(item, RecordInput):
            raise OperationFault("invalid", "invalid_record")
        key = item.key if records else item
        if (not isinstance(key, RecordKey) or not isinstance(key.parts, Mapping) or set(key.parts) != set(required_keys)
            or any(not isinstance(value, str) or not value or len(value) > 1024 for value in key.parts.values()) and not scalar_keys
            or scalar_keys and any(type(value) not in (str, int) or value == "" for value in key.parts.values())):
            raise OperationFault("invalid", "invalid_record_key")
        if partition_field:
            if key.partition is None or type(key.partition) not in (str, int, float, bool):
                raise OperationFault("invalid", "partition_required")
            json_bytes(key.partition)
        elif key.partition is not None:
            raise OperationFault("invalid", "unexpected_partition")
        identifier = json_bytes([key.parts, key.partition])
        total_bytes += len(identifier)
        if operation != "read" and identifier in identifiers:
            raise OperationFault("invalid", "duplicate_mutation_key")
        identifiers.add(identifier)
        if records:
            if not isinstance(item.content, ContentValue) or item.content.kind not in content_kinds:
                raise OperationFault("unsupported", "content_form_unsupported")
            content = item.content.data
            if item.content.kind == "bytes" and not isinstance(content, bytes):
                raise OperationFault("invalid", "bytes_required")
            if item.content.kind != "bytes" and not isinstance(content, Mapping):
                raise OperationFault("invalid", "document_required")
            if isinstance(content, Mapping) and (any(name in content and content[name] != key.parts[name] for name in required_keys)
                    or partition_field in content and json_bytes(content[partition_field]) != json_bytes(key.partition)):
                raise OperationFault("invalid", "content_key_mismatch")
            if item.expected_version is not None and (not isinstance(item.expected_version, str)
                    or not 1 <= len(item.expected_version) <= 256 or item.expected_version == "*"
                    or any(character in item.expected_version for character in "\r\n")):
                raise OperationFault("invalid", "invalid_precondition")
            total_bytes += len(content_bytes(item.content))
    if hasattr(request, "mode") and request.mode not in ("merge", "replace"):
        raise OperationFault("invalid", "invalid_mode")
    if hasattr(request, "missing") and request.missing not in ("ok", "error"):
        raise OperationFault("invalid", "invalid_missing_policy")
    if hasattr(request, "projection") and (not isinstance(request.projection, tuple)
            or not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_/]*", name) for name in request.projection)):
        raise OperationFault("invalid", "invalid_projection")
    if hasattr(request, "projection"):
        total_bytes += len(json_bytes(request.projection))
        if any("/" in name for name in request.projection):
            raise OperationFault("unsupported", "nested_projection_unsupported")
    if hasattr(request, "expected_versions"):
        versions = request.expected_versions
        if (not isinstance(versions, tuple) or versions and len(versions) != len(keys)
                or any(value is not None and (not isinstance(value, str) or not value or len(value) > 256
                   or value == "*" or "\n" in value or "\r" in value) for value in versions)):
            raise OperationFault("invalid", "invalid_preconditions")
    if operation == "query":
        if (not isinstance(request.expression, str) or not request.expression.strip() or len(request.expression) > 12000
                or not isinstance(request.dialect, str) or not isinstance(request.parameters, Mapping)):
            raise OperationFault("invalid", "invalid_query")
        total_bytes += len(json_bytes([request.expression, request.parameters, request.projection]))
    if operation == "ingest":
        if not isinstance(request.content, ContentValue) or request.content.kind not in content_kinds:
            raise OperationFault("unsupported", "content_form_unsupported")
        total_bytes += len(content_bytes(request.content))
    if operation == "schema":
        if request.action not in ("list", "read", "create", "update", "delete"):
            raise OperationFault("invalid", "invalid_schema_action")
        total_bytes += len(json_bytes(request.definition))
        if request.expected_version is not None and (not isinstance(request.expected_version, str)
                or not 1 <= len(request.expected_version) <= 256 or any(character in request.expected_version for character in "\r\n")):
            raise OperationFault("invalid", "invalid_precondition")
    if operation == "provision":
        if request.action not in ("plan", "read", "create", "update", "delete"):
            raise OperationFault("invalid", "invalid_provision_action")
        total_bytes += len(json_bytes(request.specification))
    if total_bytes > limits.max_input_bytes:
        raise OperationFault("invalid", "input_byte_limit")


def evidence_satisfies(actual: str, minimum: str) -> bool:
    return minimum == "none" or actual == minimum or minimum == "acknowledgment" and actual != "none" or minimum == "presence" and actual == "content"


def aggregate(items: tuple[ItemResult, ...]) -> str:
    statuses = {item.status for item in items}
    if not statuses:
        return "success"
    if len(statuses) == 1:
        status = next(iter(statuses))
        return "failed" if status == "not_attempted" else status
    return "partial"


def failure_item(index: int, key: RecordKey | None, fault: OperationFault, *, mutation: bool = False) -> ItemResult:
    return ItemResult(index, key, fault.status, error=ErrorInfo(fault.code, fault.status),
                      effect="unknown" if mutation and fault.status == "unknown" else "none")


def record_body(record: RecordInput, key_field: str, partition_field: str | None = None) -> dict:
    content = plain(record.content.data)
    content[key_field] = record.key.parts[key_field]
    if partition_field:
        content[partition_field] = record.key.partition
    return content


def bounded_items(items: tuple[ItemResult, ...], limit: int, *, query: bool) -> tuple[tuple[ItemResult, ...], bool]:
    size = 0
    output = []
    truncated = False
    for item in items:
        content_size = len(content_bytes(item.content)) if item.content is not None else 0
        if size + content_size > limit:
            truncated = True
            if query:
                break
            output.append(replace(item, content=None, status="failed", error=ErrorInfo("output_byte_limit", "failed")))
            continue
        size += content_size
        output.append(item)
    return tuple(output), truncated


def confirmation_digest(service: str, config: ConnectorConfig, request: SchemaRequest | ProvisionRequest) -> str:
    if (not isinstance(service, str) or not isinstance(config, ConnectorConfig)
            or not isinstance(request, (SchemaRequest, ProvisionRequest))):
        raise ConfigurationError("confirmation requires a service, connector configuration and administrative request")
    definition = request.definition if isinstance(request, SchemaRequest) else request.specification
    return hashlib.sha256(json_bytes([service, config.endpoint, config.target.coordinates,
                                     request.action, request.expected_version, definition])).hexdigest()


def matches_projection(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return isinstance(actual, Mapping) and all(name in actual and matches_projection(actual[name], value) for name, value in expected.items())
    if isinstance(expected, (list, tuple)):
        return (isinstance(actual, (list, tuple)) and len(actual) == len(expected)
                and all(matches_projection(left, right) for left, right in zip(actual, expected)))
    return json_bytes(actual) == json_bytes(expected)


async def verify_item(item: ItemResult, context, options: Verification, evidence: str, lookup, compare=None) -> ItemResult:
    for attempt in range(options.attempts):
        try:
            content = await lookup()
            satisfied = evidence == "presence" or evidence == "content" and compare(content)
        except OperationFault as fault:
            if fault.status != "not_found":
                return replace(item, status="unknown", error=ErrorInfo("verification_unavailable", fault.status),
                               verification=VerificationResult(evidence, "acknowledgment", "unknown", attempt + 1))
            satisfied = evidence == "absence"
        if satisfied:
            return replace(item, verification=VerificationResult(evidence, evidence, "satisfied", attempt + 1))
        if attempt + 1 < options.attempts:
            if options.interval_seconds >= context.deadline - time.monotonic():
                break
            await asyncio.sleep(options.interval_seconds)
    return replace(item, status="pending", verification=VerificationResult(evidence, "acknowledgment", "pending", attempt + 1))


class Continuations:
    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)

    def encode(self, cursor: str, binding: bytes) -> str:
        payload = json_bytes({"cursor": cursor, "binding": hashlib.sha256(binding).hexdigest()})
        if len(payload) > 16000:
            raise OperationFault("failed", "continuation_too_large")
        signature = hmac.digest(self._secret, payload, "sha256")
        return base64.urlsafe_b64encode(signature + payload).decode()

    def decode(self, token: str, binding: bytes) -> str:
        try:
            if not isinstance(token, str) or len(token) > 24000:
                raise ValueError()
            raw = base64.b64decode(token, altchars=b"-_", validate=True)
            signature, payload = raw[:32], raw[32:]
            if not hmac.compare_digest(signature, hmac.digest(self._secret, payload, "sha256")):
                raise ValueError()
            value = json.loads(payload)
            if value["binding"] != hashlib.sha256(binding).hexdigest() or not isinstance(value["cursor"], str):
                raise ValueError()
            return value["cursor"]
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise OperationFault("invalid", "invalid_continuation") from None