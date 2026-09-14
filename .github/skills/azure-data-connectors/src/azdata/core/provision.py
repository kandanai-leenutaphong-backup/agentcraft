"""The deploy plane — provision the resource, then prove it stayed provisioned.

WHY THIS EXISTS
---------------
This package used to say "provision with your infrastructure code", and for
a long-lived service that is still the right answer. It stops being the
right answer when an agent has to stand a service up, load it, query it and
tear it down inside one run: there is no Bicep deployment pipeline in that
loop, and shelling out to ``az`` turns every failure into a string to parse.

So this is the management plane, held to the same contract as the rest of
the package: identity not keys, failure as a value, denied by default.

**Read-back is not optional here.** ARM returns HTTP 200 with
``provisioningState: Succeeded`` for writes that an Azure Policy ``Modify``
effect silently reverts moments later. A deploy plane that trusts the
write response reports success for infrastructure that is not in the
requested state. Every :meth:`Provisioner.ensure` re-reads the resource and
compares the fields it asked for against the fields that came back, and
reports ``drift`` when they differ. That check is the reason this module is
worth having rather than a wrapper around ``begin_create_or_update``.

**Long-running operations are bounded.** The management SDKs are
synchronous and return an ``LROPoller`` whose ``result()`` blocks until the
service finishes, which for a Cosmos account is minutes and for a wedged
one is forever. :func:`await_poller` runs the poller off the event loop and
gives up at a deadline.

**Creation and deletion are separate grants.** A deploy job creates; a
teardown job deletes; almost nothing legitimately does both without saying
so. :class:`ProvisionPolicy` denies both until told otherwise.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Specs are plain dicts passed through to the SDK. This module knows a
resource has a name and a state; it does not know what any service's
schema looks like.

WHAT THIS IS NOT
----------------
Not a replacement for infrastructure-as-code, and not a state store. There
is no plan, no drift reconciliation loop and no dependency graph. It makes
one resource match one spec, and tells you when it did not.

DEPENDENCIES
------------
Standard library. The ``azure-mgmt-*`` SDK for each service loads in that
service's module, on first use.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from azdata.core.envelope import error_envelope, success_envelope

logger = logging.getLogger(__name__)

# A Cosmos account with a private endpoint routinely takes five to eight
# minutes. Fifteen is "something is wrong", not "be patient".
DEFAULT_POLL_TIMEOUT_SECS = 900.0

# Terminal ARM provisioning states, lowercased.
SUCCEEDED_STATES = frozenset({"succeeded", "online", "running", "ready"})
FAILED_STATES = frozenset({"failed", "canceled", "cancelled", "deleting"})


class ProvisionRefused(RuntimeError):
    """A create or delete was attempted that the policy forbids."""


class ProvisionDrift(RuntimeError):
    """The resource was written successfully and did not keep the value.

    Almost always an Azure Policy ``Modify`` effect at a management-group
    scope. The write is genuinely accepted; the field is genuinely
    reverted; nothing in the write response says so.
    """


@dataclass(frozen=True)
class ProvisionPolicy:
    """What a provisioner instance may do. Denies by default."""

    allow_create: bool = False
    allow_delete: bool = False
    poll_timeout_secs: float = DEFAULT_POLL_TIMEOUT_SECS
    verify_after_write: bool = True

    @classmethod
    def read_only(cls) -> "ProvisionPolicy":
        """The default. Describe and exists work; nothing mutates."""
        return cls()

    @classmethod
    def deployable(
        cls,
        *,
        allow_delete: bool = False,
        poll_timeout_secs: float = DEFAULT_POLL_TIMEOUT_SECS,
    ) -> "ProvisionPolicy":
        return cls(
            allow_create=True,
            allow_delete=allow_delete,
            poll_timeout_secs=poll_timeout_secs,
        )

    def with_overrides(self, **kwargs: Any) -> "ProvisionPolicy":
        return replace(self, **kwargs)


async def await_poller(poller: Any, timeout: float) -> Any:
    """Resolve a management-SDK ``LROPoller`` off the loop, with a deadline.

    A poller that has no ``result`` is returned unchanged, so a subclass may
    return an already-resolved object from a non-LRO call without branching.
    """
    result = getattr(poller, "result", None)
    if result is None:
        return poller
    async with asyncio.timeout(timeout):
        return await asyncio.to_thread(result)


def as_dict(model: Any) -> dict:
    """Best-effort dict view of an SDK model, without importing the SDK.

    Management models expose ``as_dict``; data-plane and fake models are
    often already mappings or plain objects.
    """
    if model is None:
        return {}
    if isinstance(model, Mapping):
        return dict(model)
    converter = getattr(model, "as_dict", None)
    if callable(converter):
        return converter()
    return {k: v for k, v in vars(model).items() if not k.startswith("_")}


def find_drift(requested: Mapping[str, Any], observed: Mapping[str, Any]) -> dict:
    """Return requested fields whose observed value differs, one level deep.

    Only keys present in ``requested`` are compared: a spec is a partial
    description and the service fills in everything else. A requested key
    absent from ``observed`` counts as drift, because a silently dropped
    setting is the failure this exists to catch.
    """
    drift: dict[str, dict] = {}
    for key, want in requested.items():
        if key not in observed:
            drift[key] = {"requested": want, "observed": None}
        elif observed[key] != want:
            drift[key] = {"requested": want, "observed": observed[key]}
    return drift


class Provisioner(ABC):
    """Make one resource match one spec, and prove it afterwards.

    Subclasses implement the ``_do_*`` seams against an ``azure-mgmt-*``
    client and inherit policy enforcement, LRO bounding, read-back
    verification and envelope shaping.
    """

    #: Human label used in envelopes and log lines, e.g. ``"search-index"``.
    resource_kind: str = "resource"

    def __init__(
        self,
        *,
        name: str,
        policy: ProvisionPolicy | None = None,
    ) -> None:
        self._name = name
        self._policy = policy or ProvisionPolicy.read_only()

    @property
    def name(self) -> str:
        return self._name

    @property
    def policy(self) -> ProvisionPolicy:
        return self._policy

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_describe(self) -> Any | None:
        """Return the live resource, or None when it does not exist."""

    @abstractmethod
    async def _do_ensure(self, spec: Mapping[str, Any]) -> Any:
        """Create or update the resource to match ``spec``.

        Return whatever the SDK returned; the base resolves a poller and
        discards the value in favour of a fresh read.
        """

    @abstractmethod
    async def _do_teardown(self) -> Any:
        """Delete the resource. Idempotent: absent is not an error."""

    def _verifiable(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """The subset of ``spec`` worth comparing after the write.

        Defaults to the whole spec. Override where the SDK normalises a
        field on the way in — a location of ``"Australia East"`` comes back
        as ``"australiaeast"`` and would otherwise read as drift.
        """
        return spec

    # ------------------------------------------------------------------
    # Public surface.
    # ------------------------------------------------------------------

    async def exists(self) -> bool:
        """True when the resource is present. Never raises."""
        try:
            return await self._do_describe() is not None
        except Exception:  # noqa: BLE001 - a probe that raises is useless
            return False

    async def describe(self) -> str:
        """Read the live resource into a success envelope."""
        try:
            live = await self._do_describe()
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("describe", exc)
        observed = as_dict(live)
        return success_envelope(
            "describe",
            resource_kind=self.resource_kind,
            name=self._name,
            present=live is not None,
            state=self._state_of(observed),
            resource=observed,
        )

    async def ensure(
        self,
        spec: Mapping[str, Any],
        *,
        verify: bool | None = None,
    ) -> str:
        """Create or update until the resource matches ``spec``. Idempotent.

        The returned envelope carries ``created`` (the resource was absent
        beforehand) and ``drift`` (fields that did not survive the write).
        A non-empty ``drift`` is reported as an error, not a warning: the
        infrastructure is not in the requested state and a caller that
        proceeds is building on a false premise.
        """
        if not self._policy.allow_create:
            return self._failure(
                "ensure",
                ProvisionRefused(
                    f"{self.resource_kind} provisioner may not create. Build it "
                    "with ProvisionPolicy.deployable()."
                ),
            )

        try:
            existed = await self._do_describe() is not None
            poller = await self._do_ensure(spec)
            await await_poller(poller, self._policy.poll_timeout_secs)
        except TimeoutError:
            return self._failure(
                "ensure",
                TimeoutError(
                    f"{self.resource_kind} '{self._name}' did not reach a terminal "
                    f"state within {self._policy.poll_timeout_secs}s"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("ensure", exc)

        should_verify = self._policy.verify_after_write if verify is None else verify
        drift: dict = {}
        observed: dict = {}
        if should_verify:
            try:
                live = await self._do_describe()
            except Exception as exc:  # noqa: BLE001 - boundary
                return self._failure("ensure", exc)
            if live is None:
                return self._failure(
                    "ensure",
                    ProvisionDrift(
                        f"{self.resource_kind} '{self._name}' was accepted but is "
                        "not readable afterwards"
                    ),
                )
            observed = as_dict(live)
            state = self._state_of(observed)
            if state and state.lower() in FAILED_STATES:
                return self._failure(
                    "ensure",
                    RuntimeError(
                        f"{self.resource_kind} '{self._name}' settled in state "
                        f"'{state}'"
                    ),
                )
            drift = find_drift(self._verifiable(spec), observed)
            if drift:
                return self._failure(
                    "ensure",
                    ProvisionDrift(
                        f"{self.resource_kind} '{self._name}' did not keep "
                        f"{sorted(drift)} after the write; suspect an Azure "
                        "Policy Modify effect"
                    ),
                )

        return success_envelope(
            "ensure",
            resource_kind=self.resource_kind,
            name=self._name,
            created=not existed,
            verified=should_verify,
            state=self._state_of(observed),
            drift=drift,
        )

    async def teardown(self, *, verify: bool | None = None) -> str:
        """Delete the resource. Requires an explicit delete grant."""
        if not self._policy.allow_delete:
            return self._failure(
                "teardown",
                ProvisionRefused(
                    f"{self.resource_kind} provisioner has no delete grant. Build "
                    "it with ProvisionPolicy.deployable(allow_delete=True)."
                ),
            )
        try:
            existed = await self._do_describe() is not None
            if existed:
                poller = await self._do_teardown()
                await await_poller(poller, self._policy.poll_timeout_secs)
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("teardown", exc)

        should_verify = self._policy.verify_after_write if verify is None else verify
        if should_verify and existed:
            try:
                if await self._do_describe() is not None:
                    return self._failure(
                        "teardown",
                        ProvisionDrift(
                            f"{self.resource_kind} '{self._name}' is still readable "
                            "after a successful delete"
                        ),
                    )
            except Exception as exc:  # noqa: BLE001 - boundary
                return self._failure("teardown", exc)

        return success_envelope(
            "teardown",
            resource_kind=self.resource_kind,
            name=self._name,
            deleted=existed,
            verified=should_verify,
        )

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    @staticmethod
    def _state_of(observed: Mapping[str, Any]) -> str:
        for key in ("provisioning_state", "provisioningState", "status", "state"):
            value = observed.get(key)
            if isinstance(value, str):
                return value
        properties = observed.get("properties")
        if isinstance(properties, Mapping):
            return Provisioner._state_of(properties)
        return ""

    def _failure(self, operation: str, exc: Exception) -> str:
        logger.warning(
            "azdata.provision_failed kind=%s name=%s operation=%s: %s: %s",
            self.resource_kind, self._name, operation, type(exc).__name__, exc,
        )
        return error_envelope(
            f"{self.resource_kind} '{self._name}' {operation} failed", exc=exc
        )


__all__ = [
    "DEFAULT_POLL_TIMEOUT_SECS",
    "FAILED_STATES",
    "SUCCEEDED_STATES",
    "ProvisionDrift",
    "ProvisionPolicy",
    "ProvisionRefused",
    "Provisioner",
    "as_dict",
    "await_poller",
    "find_drift",
]
