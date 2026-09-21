import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from azdata import ContentValue, ItemResult, OperationResult, ResourceAddress, VerificationResult

from app.cybereye.backend.agents.cosmos_state import CosmosOwnerDocuments

OWNER = hashlib.sha256(b"owner").hexdigest()


def result(status="success", content=None, version=None, verified=False):
    return OperationResult("test", "read", "cosmos", ResourceAddress({"database": "db", "container": "state"}),
        status, items=(ItemResult(0, None, status, ContentValue(content) if content is not None else None,
        version=version, verification=VerificationResult("content", "content", "satisfied" if verified else "not_requested")),))


def adapter(connector):
    return CosmosOwnerDocuments(endpoint="https://test.documents.azure.com", database="db", container="state",
        namespace="agents", credential_factory=lambda: SimpleNamespace(close=AsyncMock()),
        connector_factory=lambda *args, **kwargs: connector)


def test_public_connector_requests_require_partition_cas_and_readback():
    connector = SimpleNamespace(read=AsyncMock(side_effect=[result("not_found"),
        result(content={"id": "agents", "owner": OWNER, "documents": {"v": "value"}}, version="etag")]),
        create=AsyncMock(return_value=result(verified=True)), update=AsyncMock(return_value=result("conflict")), aclose=AsyncMock())
    state = adapter(connector)
    try:
        assert state.load(OWNER) == ({}, None)
        assert state.compare_exchange(OWNER, None, {"v": "value"})
        assert state.load(OWNER) == ({"v": "value"}, "etag")
        assert not state.compare_exchange(OWNER, "old", {"v": "new"})
        created = connector.create.call_args.args[0]
        updated = connector.update.call_args.args[0]
        assert created.requirements.guarantees == ("create_if_absent",)
        assert created.records[0].key.partition == OWNER
        assert updated.records[0].expected_version == "old"
        assert updated.requirements.guarantees == ("conditional_version",)
        assert updated.verification.kind == "content"
    finally:
        state.close()
    connector.aclose.assert_awaited_once()


@pytest.mark.parametrize("reply", [result("failed"), result("unknown"),
    result(content={"id": "agents", "owner": "foreign", "documents": {}}, version="etag")])
def test_unavailable_unknown_foreign_never_become_empty_state(reply):
    connector = SimpleNamespace(read=AsyncMock(return_value=reply), aclose=AsyncMock())
    state = adapter(connector)
    try:
        with pytest.raises(OSError):
            state.load(OWNER)
    finally:
        state.close()


@pytest.mark.parametrize("reply", [result("unknown"), result("failed"), result()])
def test_unverified_write_never_reports_success(reply):
    connector = SimpleNamespace(create=AsyncMock(return_value=reply), aclose=AsyncMock())
    state = adapter(connector)
    try:
        with pytest.raises(OSError, match="write_not_verified"):
            state.compare_exchange(OWNER, None, {"record": "value"})
    finally:
        state.close()


def test_capacity_and_partition_refuse_before_io():
    connector = SimpleNamespace(create=AsyncMock(), read=AsyncMock(), aclose=AsyncMock())
    state = adapter(connector)
    try:
        with pytest.raises(ValueError, match="invalid_owner_partition"):
            state.load("foreign")
        with pytest.raises(OSError, match="capacity_exceeded"):
            state.compare_exchange(OWNER, None, {"record": "x" * 1_500_001})
        connector.create.assert_not_called()
        connector.read.assert_not_called()
    finally:
        state.close()