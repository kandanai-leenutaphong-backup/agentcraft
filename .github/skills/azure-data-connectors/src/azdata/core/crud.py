"""The write plane — one CRUD contract across services that agree on nothing.

WHY THIS EXISTS
---------------
The read plane in this package is uniform because reading is uniform: send
a query, shape a result. Writing is not. Azure AI Search takes batches of
documents and returns a per-document result list. Cosmos NoSQL takes one
item at a time and needs a partition key it cannot infer. Gremlin has no
write API at all — you write by submitting a traversal that mutates.

Left alone, each caller learns three different write vocabularies, three
different partial-failure shapes, and three different ways to not notice
that a delete did nothing.

This module is the contract they share:

* **Create, Retrieve, Upload, Delete**, plus the free-form query the read
  plane already provides. Batched where the service batches, serialised
  where it does not.
* **One result envelope.** ``{"ok": true, "operation": ..., "count": ...}``
  on success, the existing ``error`` envelope on failure. Partial batch
  failure is a success envelope carrying ``failed``, never a silent drop.
* **Writes are off by default.** :class:`WritePolicy` must be handed a
  connector before it will mutate anything, and delete is a separate grant
  from write. A read-only credential is still the real boundary; this is
  the guard that fails closed at the point of use, in front of it.
* **Verification is first-class.** ``verify=True`` re-reads after the write
  and fails the operation when the resulting state is not what was asked
  for. An accepted write response is not evidence that the state changed:
  Search accepts a document and indexes it seconds later, and a delete
  against a wrong partition key succeeds while deleting nothing.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
The base knows that items have keys and that keys can be extracted; it does
not know what a key is called. ``key_field`` is a parameter and
``_key_of`` is a subclass seam, so no field name from a caller's schema
appears here.

WHAT THIS IS NOT
----------------
Not a transaction manager. Batches are chunked and submitted in order; a
chunk that fails leaves earlier chunks applied. Where a service offers real
transactional batch semantics, the service module exposes it separately.

DEPENDENCIES
------------
Standard library. SDKs load per service, in the service module.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from azdata.core.breaker import CircuitBreaker, ThrottleError, ThrottleGate
from azdata.core.envelope import error_envelope, success_envelope

logger = logging.getLogger(__name__)

# Search caps an indexing batch at 1000 documents and roughly 16 MB, and
# degrades well before either. 100 is the size at which a partial failure
# is still cheap to retry.
DEFAULT_MAX_BATCH = 100

# Search indexes asynchronously: an accepted upload is readable "soon".
# These bound the verification poll rather than the write itself.
DEFAULT_VERIFY_ATTEMPTS = 10
DEFAULT_VERIFY_DELAY_SECS = 1.0


class WriteRefused(RuntimeError):
    """A mutation was attempted that the connector's policy forbids.

    Raised rather than returned because it is a programming error, not a
    service outcome: the caller asked for something the wiring never
    granted. Connector methods catch it and return an error envelope, so
    it does not escape into a caller that only handles envelopes.
    """


class VerificationFailed(RuntimeError):
    """A write was accepted but the resulting state was not what was asked.

    The single most valuable failure in this module. See the class
    docstring of :class:`CrudConnector` for why an accepted write is not
    evidence of a changed state.
    """


@dataclass(frozen=True)
class WritePolicy:
    """What a connector instance is permitted to do. Denies by default.

    Delete is a separate grant from write because the two have different
    blast radii and are almost never needed together by the same caller.
    An ingest path writes and never deletes; a retention job deletes and
    never writes.
    """

    allow_write: bool = False
    allow_delete: bool = False
    max_batch: int = DEFAULT_MAX_BATCH
    verify_writes: bool = False
    verify_attempts: int = DEFAULT_VERIFY_ATTEMPTS
    verify_delay_secs: float = DEFAULT_VERIFY_DELAY_SECS

    def __post_init__(self) -> None:
        # A max_batch of 0 would silently write nothing while reporting
        # success on an empty chunk list.
        object.__setattr__(self, "max_batch", max(1, int(self.max_batch)))
        object.__setattr__(self, "verify_attempts", max(1, int(self.verify_attempts)))

    @classmethod
    def read_only(cls) -> "WritePolicy":
        """The default. Every mutation is refused."""
        return cls()

    @classmethod
    def writable(
        cls,
        *,
        allow_delete: bool = False,
        verify_writes: bool = True,
        max_batch: int = DEFAULT_MAX_BATCH,
    ) -> "WritePolicy":
        """Grant writes. Verification defaults on, because the point of an
        explicit write grant is that somebody cares whether it landed."""
        return cls(
            allow_write=True,
            allow_delete=allow_delete,
            max_batch=max_batch,
            verify_writes=verify_writes,
        )

    def with_overrides(self, **kwargs: Any) -> "WritePolicy":
        return replace(self, **kwargs)


def chunked(items: Sequence[Any], size: int) -> list[Sequence[Any]]:
    """Split ``items`` into chunks of at most ``size``. Never yields empty."""
    if size < 1:
        size = 1
    return [items[i : i + size] for i in range(0, len(items), size)]


class CrudConnector(ABC):
    """Create, Retrieve, Upload, Delete over one service, one envelope.

    Subclasses implement the narrow ``_do_*`` seams against their SDK and
    inherit policy enforcement, batching, breaker and gate handling,
    verification and envelope shaping.

    The write path is deliberately pessimistic. Three specific lies a
    service will tell you, all of which ``verify=True`` catches:

    * **Search** accepts an upload and returns ``succeeded=True`` per
      document before the document is retrievable. A test that reads
      immediately after writing fails intermittently and gets a ``sleep``
      bolted onto it; this polls instead, bounded.
    * **Cosmos** deletes against a partition key. Given the wrong one it
      raises 404, which a caller that treats "already gone" as success
      will swallow, leaving the item in place.
    * **Gremlin** ``drop()`` on a traversal matching nothing succeeds and
      reports nothing. The only proof of a delete is a follow-up count.
    """

    #: Service label used in breaker names, log lines and envelopes.
    service: str = "crud"

    def __init__(
        self,
        *,
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
        gate_provider: Callable[[], Any] | None = None,
        key_field: str = "id",
    ) -> None:
        self._policy = policy or WritePolicy.read_only()
        self._breaker = breaker
        self._gate_provider = gate_provider
        self._key_field = key_field

    @property
    def policy(self) -> WritePolicy:
        return self._policy

    @property
    def key_field(self) -> str:
        return self._key_field

    @property
    def breaker(self) -> CircuitBreaker | None:
        return self._breaker

    # ------------------------------------------------------------------
    # Subclass seams. Each returns raw SDK output, or raises. Envelope
    # shaping, batching and policy live in the public methods above them.
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_create(self, items: Sequence[dict]) -> list[dict]:
        """Insert ``items``, failing when a key already exists.

        Returns one per-item result dict: ``{"key": ..., "ok": bool,
        "detail": str}``.
        """

    @abstractmethod
    async def _do_upload(self, items: Sequence[dict]) -> list[dict]:
        """Insert-or-replace ``items``. Same per-item result shape."""

    @abstractmethod
    async def _do_read(self, key: Any, **kwargs: Any) -> dict | None:
        """Return the item, or None when it does not exist."""

    @abstractmethod
    async def _do_delete(self, keys: Sequence[Any], **kwargs: Any) -> list[dict]:
        """Delete by key. Same per-item result shape."""

    @abstractmethod
    async def query(self, query: str, **kwargs: Any) -> str:
        """Free-form retrieval in the service's own language.

        Returns the read plane's service-shaped payload, not an operation
        envelope: a caller projecting results should not unwrap first.
        """

    def _key_of(self, item: dict) -> Any:
        """Extract the key from an item. Override where it is composite."""
        return item.get(self._key_field)

    # ------------------------------------------------------------------
    # Public surface.
    # ------------------------------------------------------------------

    async def create(self, items: Sequence[dict], *, verify: bool | None = None) -> str:
        """Insert items that must not already exist."""
        return await self._write("create", items, self._do_create, verify)

    async def upload(self, items: Sequence[dict], *, verify: bool | None = None) -> str:
        """Insert or replace items. The idempotent write; prefer it."""
        return await self._write("upload", items, self._do_upload, verify)

    async def read(self, key: Any, **kwargs: Any) -> str:
        """Retrieve one item by key.

        A missing item is ``count: 0``, not an error: absence is a valid
        answer to a lookup and a caller should not have to parse an error
        string to distinguish it from a failure.
        """
        try:
            item = await self._guarded(lambda: self._do_read(key, **kwargs))
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("read", exc)
        return success_envelope(
            "read",
            service=self.service,
            count=1 if item is not None else 0,
            results=[item] if item is not None else [],
        )

    async def delete(
        self,
        keys: Sequence[Any],
        *,
        verify: bool | None = None,
        **kwargs: Any,
    ) -> str:
        """Delete by key. Requires ``allow_delete``, separately from write."""
        if not self._policy.allow_delete:
            return self._failure(
                "delete",
                WriteRefused(
                    f"{self.service} connector has no delete grant. Build it "
                    "with WritePolicy.writable(allow_delete=True)."
                ),
            )
        if not keys:
            return success_envelope(
                "delete", service=self.service, count=0, failed=[], verified=False
            )

        results: list[dict] = []
        try:
            for chunk in chunked(list(keys), self._policy.max_batch):
                results.extend(
                    await self._guarded(lambda c=chunk: self._do_delete(c, **kwargs))
                )
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("delete", exc)

        should_verify = self._policy.verify_writes if verify is None else verify
        if should_verify:
            try:
                await self._verify_absent(
                    [r["key"] for r in results if r.get("ok")], **kwargs
                )
            except Exception as exc:  # noqa: BLE001 - boundary
                return self._failure("delete", exc)

        return self._batch_envelope("delete", results, verified=should_verify)

    def check_breaker(self) -> None:
        """Raise when the breaker is open. Public so a caller batching many
        operations can fail fast once instead of per item."""
        if self._breaker is not None and self._breaker.is_open():
            raise RuntimeError(f"{self.service} temporarily unavailable (breaker open)")

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    async def _write(
        self,
        operation: str,
        items: Sequence[dict],
        do: Callable[[Sequence[dict]], Any],
        verify: bool | None,
    ) -> str:
        if not self._policy.allow_write:
            return self._failure(
                operation,
                WriteRefused(
                    f"{self.service} connector is read-only. Build it with "
                    "WritePolicy.writable()."
                ),
            )
        if not items:
            return success_envelope(
                operation, service=self.service, count=0, failed=[], verified=False
            )

        missing = [i for i, item in enumerate(items) if self._key_of(item) is None]
        if missing:
            return self._failure(
                operation,
                ValueError(
                    f"{len(missing)} item(s) have no '{self._key_field}' value "
                    f"(first at index {missing[0]})"
                ),
            )

        results: list[dict] = []
        try:
            for chunk in chunked(list(items), self._policy.max_batch):
                results.extend(await self._guarded(lambda c=chunk: do(c)))
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure(operation, exc)

        should_verify = self._policy.verify_writes if verify is None else verify
        if should_verify:
            written = {self._key_of(item) for item in items}
            accepted = [r["key"] for r in results if r.get("ok") and r["key"] in written]
            try:
                await self._verify_present(accepted)
            except Exception as exc:  # noqa: BLE001 - boundary
                return self._failure(operation, exc)

        return self._batch_envelope(operation, results, verified=should_verify)

    async def _verify_present(self, keys: Sequence[Any], **kwargs: Any) -> None:
        """Poll until every key reads back, or raise VerificationFailed."""
        await self._poll(keys, want_present=True, **kwargs)

    async def _verify_absent(self, keys: Sequence[Any], **kwargs: Any) -> None:
        """Poll until every key stops reading back, or raise."""
        await self._poll(keys, want_present=False, **kwargs)

    async def _poll(self, keys: Sequence[Any], *, want_present: bool, **kwargs: Any) -> None:
        outstanding = list(keys)
        for attempt in range(self._policy.verify_attempts):
            still: list[Any] = []
            for key in outstanding:
                found = await self._do_read(key, **kwargs) is not None
                if found is not want_present:
                    still.append(key)
            outstanding = still
            if not outstanding:
                return
            if attempt < self._policy.verify_attempts - 1:
                await asyncio.sleep(self._policy.verify_delay_secs)
        state = "readable" if want_present else "absent"
        raise VerificationFailed(
            f"{len(outstanding)} item(s) were accepted but never became {state} "
            f"after {self._policy.verify_attempts} checks"
        )

    async def _guarded(self, call: Callable[[], Any]) -> Any:
        """Run ``call`` behind the breaker and, when wired, the throttle gate."""
        self.check_breaker()
        gate: ThrottleGate | None = None
        if self._gate_provider is not None:
            gate = self._gate_provider()
            if hasattr(gate, "__await__"):
                gate = await gate  # type: ignore[assignment]

        if gate is None:
            return await self._recorded(call)

        was_probe = await gate.acquire()
        try:
            result = await self._recorded(call)
            await gate.record_success()
            return result
        except ThrottleError:
            raise
        except Exception as exc:
            await self._record_gate_failure(gate, exc)
            raise
        finally:
            gate.release(was_probe=was_probe)

    async def _recorded(self, call: Callable[[], Any]) -> Any:
        try:
            result = await call()
        except Exception:
            if self._breaker is not None:
                self._breaker.record_failure()
            raise
        if self._breaker is not None:
            self._breaker.record_success()
        return result

    @staticmethod
    async def _record_gate_failure(gate: ThrottleGate, exc: Exception) -> None:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status == 429:
            await gate.record_429()
        else:
            await gate.record_server_error()

    def _batch_envelope(self, operation: str, results: list[dict], *, verified: bool) -> str:
        failed = [r for r in results if not r.get("ok")]
        return success_envelope(
            operation,
            service=self.service,
            count=len(results) - len(failed),
            failed=failed,
            verified=verified,
        )

    def _failure(self, operation: str, exc: Exception) -> str:
        logger.warning(
            "azdata.%s_failed operation=%s: %s: %s",
            self.service, operation, type(exc).__name__, exc,
        )
        return error_envelope(f"{self.service} {operation} failed", exc=exc)


class IngestConnector(ABC):
    """Append rows to a store that has no update and no per-row delete.

    The narrower half of the write plane, for services where
    :class:`CrudConnector` would have to raise on two of its four
    operations. Kusto is the case that forced it: a table is an
    append-only extent store, rows are not individually addressable, and
    the closest thing to a delete is a soft-delete over a predicate run as
    a management command against the whole table. Subclassing
    ``CrudConnector`` and raising ``NotImplementedError`` from ``delete``
    would advertise a contract the service does not satisfy, so the verbs
    are simply absent here. That absence is the point.

    **Verification is by row-count delta, not by key digest.** Everywhere
    else in this package a write is verified by reading back the keys it
    was handed, because a key identifies a row. Append-only stores are the
    documented exception: there is no key to read back, and re-ingesting
    the same payload legitimately produces a second row. So ``ingest``
    counts before, counts after, and asserts the difference — which is a
    weaker claim than a digest and is stated as one in the envelope
    (``rows_before``, ``rows_after``, ``delta``) rather than hidden behind
    ``verified: true``.

    The grant model is unchanged: denied by default, and
    ``WritePolicy.writable()`` is what unlocks it.
    """

    #: Service label used in log lines and envelopes.
    service: str = "ingest"

    def __init__(
        self,
        *,
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._policy = policy or WritePolicy.read_only()
        self._breaker = breaker

    @property
    def policy(self) -> WritePolicy:
        return self._policy

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_ingest(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Append ``rows``. Raise on refusal or failure."""

    @abstractmethod
    async def count(self, target: str | None = None) -> int:
        """Rows currently in the target. ``-1`` when it cannot be read."""

    @abstractmethod
    async def query(self, query: str, **kwargs: Any) -> str:
        """Free-form retrieval in the service's own language."""

    # ------------------------------------------------------------------
    # Public surface.
    # ------------------------------------------------------------------

    async def ingest(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        verify: bool | None = None,
    ) -> str:
        """Append ``rows``, and prove the row count moved by exactly that much."""
        if not self._policy.allow_write:
            return self._failure(
                "ingest",
                WriteRefused(
                    f"{self.service} connector is read-only. Build it with "
                    "WritePolicy.writable()."
                ),
            )
        if not rows:
            return success_envelope(
                "ingest", service=self.service, count=0, verified=False
            )

        should_verify = self._policy.verify_writes if verify is None else verify
        before = -1
        try:
            if should_verify:
                before = await self.count()
            await self._do_ingest(list(rows))
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("ingest", exc)

        after = -1
        if should_verify:
            try:
                after = await self._await_delta(before, len(rows))
            except Exception as exc:  # noqa: BLE001 - boundary
                return self._failure("ingest", exc)

        return success_envelope(
            "ingest",
            service=self.service,
            count=len(rows),
            verified=should_verify,
            rows_before=before,
            rows_after=after,
            delta=(after - before) if should_verify and before >= 0 else None,
        )

    async def _await_delta(self, before: int, expected: int) -> int:
        """Poll the count until it has moved by ``expected``, or raise.

        Ingestion is asynchronous on every store that has this shape: the
        command is accepted and the rows become queryable afterwards. A
        sleep here would be a guess; this is a bounded poll that reports
        what it actually saw.
        """
        if before < 0:
            raise VerificationFailed(
                f"{self.service} row count was unreadable before the ingest, "
                "so the delta cannot be verified"
            )
        after = before
        for attempt in range(self._policy.verify_attempts):
            after = await self.count()
            if after - before == expected:
                return after
            if attempt < self._policy.verify_attempts - 1:
                await asyncio.sleep(self._policy.verify_delay_secs)
        raise VerificationFailed(
            f"{self.service} ingest of {expected} row(s) moved the count from "
            f"{before} to {after} after {self._policy.verify_attempts} checks"
        )

    def _failure(self, operation: str, exc: Exception) -> str:
        logger.warning(
            "azdata.%s_failed operation=%s: %s: %s",
            self.service, operation, type(exc).__name__, exc,
        )
        return error_envelope(f"{self.service} {operation} failed", exc=exc)


__all__ = [
    "DEFAULT_MAX_BATCH",
    "CrudConnector",
    "IngestConnector",
    "VerificationFailed",
    "WritePolicy",
    "WriteRefused",
    "chunked",
]
