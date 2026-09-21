from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError
import json
import re
from threading import Thread

from azdata import (
    ConnectorConfig, ContentValue, CreateRequest, Limits, Policy, ReadRequest,
    RecordInput, RecordKey, Requirements, ResourceAddress, UpdateRequest, Verification, connect,
)


class CosmosOwnerDocuments:
    def __init__(self, *, endpoint, database, container, namespace, credential_factory, connector_factory=connect):
        from urllib.parse import urlsplit

        if namespace not in {"agents", "profiles"}:
            raise ValueError("unknown_state_namespace")
        self.namespace = namespace
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.loop.run_forever, name=f"cosmos-{namespace}", daemon=True)
        self.thread.start()
        self.closed = False

        async def initialize():
            self.credential = credential_factory()
            self.connector = connector_factory("cosmos", ConnectorConfig(endpoint,
                ResourceAddress({"database": database, "container": container}),
                (urlsplit(endpoint).hostname,), partition_key_field="owner"),
                credential=self.credential, policy=Policy("investigation-owner-state",
                    {"read", "create", "update"}, limits=Limits(timeout_seconds=30,
                    max_items=1, max_input_bytes=1_800_000, max_output_bytes=2_000_000)))

        try:
            self._run(initialize())
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
            self.loop.close()
            raise

    def _run(self, coroutine):
        if self.closed:
            coroutine.close()
            raise OSError("owner_state_closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout=40)
        except TimeoutError:
            future.cancel()
            raise OSError("owner_state_outcome_unknown") from None

    def _key(self, owner):
        if not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9]{64}", owner):
            raise ValueError("invalid_owner_partition")
        return RecordKey({"id": self.namespace}, owner)

    async def _load(self, owner):
        result = await self.connector.read(ReadRequest(keys=(self._key(owner),)))
        if len(result.items) != 1:
            raise OSError("owner_state_unavailable")
        item = result.items[0]
        if item.status == "not_found":
            return {}, None
        if result.status != "success" or item.status != "success" or item.content is None or not item.version:
            raise OSError("owner_state_unavailable")
        document = item.content.to_native()
        records = document.get("documents")
        if (document.get("owner") != owner or document.get("id") != self.namespace
                or not isinstance(records, dict)
                or any(not isinstance(key, str) or not isinstance(value, str) for key, value in records.items())):
            raise OSError("owner_state_integrity_failure")
        return records, item.version

    def load(self, owner):
        return self._run(self._load(owner))

    async def _exchange(self, owner, expected, documents):
        body = {"id": self.namespace, "owner": owner, "documents": documents}
        if len(json.dumps(body).encode()) > 1_500_000:
            raise OSError("owner_state_capacity_exceeded")
        record = RecordInput(self._key(owner), ContentValue(body), expected_version=expected)
        if expected is None:
            result = await self.connector.create(CreateRequest(records=(record,),
                requirements=Requirements(("create_if_absent",)), verification=Verification("content", attempts=1)))
        else:
            result = await self.connector.update(UpdateRequest(mode="replace", records=(record,),
                requirements=Requirements(("conditional_version",)), verification=Verification("content", attempts=1)))
        if len(result.items) == 1 and result.items[0].status == "conflict":
            return False
        if (result.status != "success" or len(result.items) != 1 or result.items[0].status != "success"
                or result.items[0].verification.state != "satisfied"):
            raise OSError("owner_state_write_not_verified")
        return True

    def compare_exchange(self, owner, expected, documents):
        return self._run(self._exchange(owner, expected, documents))

    def close(self):
        if self.closed:
            return

        async def cleanup():
            try:
                await self.connector.aclose()
            finally:
                await self.credential.close()

        try:
            self._run(cleanup())
        finally:
            self.closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise OSError("owner_state_shutdown_incomplete")
            self.loop.close()