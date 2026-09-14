"""The registry — the allowlist of everything the inventory will ever serve.

NEW IN THIS COMPONENT. Rationale and usage: `README.md`, "The registry is the
security control".

A request can name only what is declared here: an id that is not in the
registry is rejected before any client is built, and no code path turns a
request into a coordinate. Filing is by id, never by matching labels. A
declaration carries endpoints, database, table, graph and index names and
nothing that could be a credential.

This module knows no use case, source, cluster, table or graph. Those belong
to the composing application, which builds a registry and hands it in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

#: How a source is reached. New kinds are added here and in the wire
#: contract's ``SourceType`` together; nothing infers a kind from a name.
SourceType = Literal["adx_table", "gremlin_graph", "search_index", "local_table"]

#: What a source can answer. Declared, not probed: a capability the code
#: cannot deliver is a lie the UI will repeat.
CAPABILITIES: frozenset[str] = frozenset(
    {"metadata", "row_count", "schema", "preview", "element_counts"}
)

_ID = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.-")

#: Words that make a coordinate name a credential name. Coordinates are served
#: to the client, so this is refused at build rather than filtered on the way
#: out: a component that accepts a coordinate called `sas_token` will one day
#: be handed one.
_CREDENTIAL_WORDS = frozenset(
    {
        "key", "keys", "secret", "secrets", "password", "passwd", "pwd",
        "token", "tokens", "sas", "sig", "signature", "credential",
        "credentials", "auth", "authorization", "connectionstring",
    }
)


class InventoryDefinitionError(ValueError):
    """A registry that cannot be trusted to reject a forged id. Fatal at build."""


def _names_a_credential(name: str) -> bool:
    # camelCase is split too, so `sasToken` is refused for the same reason
    # `sas_token` is.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    words = [part for part in re.split(r"[^a-z0-9]+", spaced.casefold()) if part]
    if any(word in _CREDENTIAL_WORDS for word in words):
        return True
    compact = re.sub(r"[^a-z0-9]+", "", name.casefold())
    return any(
        marker in compact
        for marker in ("connectionstring", "sastoken", "accesskey", "apikey")
    )


def _check_id(value: str, *, what: str) -> str:
    if not value or len(value) > 128:
        raise InventoryDefinitionError(f"{what} must be 1-128 characters")
    if set(value) - _ID:
        raise InventoryDefinitionError(
            f"{what} {value!r} may use lowercase letters, digits, '_', '.' and '-' only"
        )
    return value


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """How one source is reached. Coordinates and key names, never values."""

    #: Which registered reader answers for this source. A connector with no
    #: reader is reported as unavailable, not guessed at.
    connector: str
    #: Non-secret coordinates the reader needs: endpoint, database, table,
    #: graph, index. Missing ones make the source unconfigured.
    coordinates: Mapping[str, str] = field(default_factory=dict)
    #: Every coordinate that must be present for this source to be usable.
    required: tuple[str, ...] = ()
    #: Environment keys an operator sets to supply them. Names only.
    settings: tuple[str, ...] = ()
    #: Where the reader lives, for an operator reading the detail pane.
    reached_by: str = ""
    #: How the connector is displayed. Not an identifier.
    connector_name: str = ""

    @property
    def missing(self) -> tuple[str, ...]:
        """Required coordinates that are absent or empty, in declared order."""
        return tuple(
            name for name in self.required if not str(self.coordinates.get(name, "")).strip()
        )

    @property
    def is_configured(self) -> bool:
        return not self.missing


@dataclass(frozen=True, slots=True)
class InventorySource:
    """One addressable thing behind one use case."""

    source_id: str
    use_case_id: str
    name: str
    source_type: SourceType
    holds: str
    capabilities: tuple[str, ...]
    binding: SourceBinding
    #: What this data is, and what it is not. Rendered beside every preview.
    provenance: str = ""

    @property
    def is_configured(self) -> bool:
        return self.binding.is_configured

    @property
    def unconfigured_detail(self) -> str:
        missing = self.binding.missing
        if not missing:
            return ""
        keys = ", ".join(self.binding.settings) or "no environment key is declared"
        return (
            "not configured; missing coordinate(s): "
            + ", ".join(missing)
            + f". Set: {keys}"
        )


@dataclass(frozen=True, slots=True)
class UseCase:
    """One named body of work and everything filed under it."""

    use_case_id: str
    name: str
    summary: str
    sources: tuple[InventorySource, ...]


class InventoryRegistry:
    """Every id this server will accept, and nothing else.

    Construction is the validation: a registry that built is one whose ids
    are unique, whose sources agree with the use case that holds them, and
    whose capabilities are all deliverable.
    """

    def __init__(self, use_cases: Iterable[UseCase]) -> None:
        ordered = tuple(use_cases)
        by_use_case: dict[str, UseCase] = {}
        by_source: dict[str, InventorySource] = {}
        for use_case in ordered:
            _check_id(use_case.use_case_id, what="use case id")
            if use_case.use_case_id in by_use_case:
                raise InventoryDefinitionError(
                    f"duplicate use case id {use_case.use_case_id!r}"
                )
            if not use_case.name.strip():
                raise InventoryDefinitionError(
                    f"use case {use_case.use_case_id!r} has no name"
                )
            by_use_case[use_case.use_case_id] = use_case
            for source in use_case.sources:
                _check_id(source.source_id, what="source id")
                if source.source_id in by_source:
                    raise InventoryDefinitionError(
                        f"duplicate source id {source.source_id!r}"
                    )
                if source.use_case_id != use_case.use_case_id:
                    raise InventoryDefinitionError(
                        f"source {source.source_id!r} claims use case "
                        f"{source.use_case_id!r} but is declared under "
                        f"{use_case.use_case_id!r}"
                    )
                if not source.name.strip():
                    raise InventoryDefinitionError(
                        f"source {source.source_id!r} has no name"
                    )
                unknown = set(source.capabilities) - CAPABILITIES
                if unknown:
                    raise InventoryDefinitionError(
                        f"source {source.source_id!r} declares unknown "
                        f"capabilities: {', '.join(sorted(unknown))}"
                    )
                if not source.binding.connector:
                    raise InventoryDefinitionError(
                        f"source {source.source_id!r} names no connector"
                    )
                for coordinate in source.binding.coordinates:
                    if _names_a_credential(str(coordinate)):
                        # The name only. Whatever was configured under it is
                        # not repeated into an exception or a startup log.
                        raise InventoryDefinitionError(
                            f"source {source.source_id!r} declares coordinate "
                            f"{coordinate!r}, which names a credential; "
                            "coordinates are non-secret and are served to the client"
                        )
                by_source[source.source_id] = source
        if not ordered:
            raise InventoryDefinitionError("a registry declares at least one use case")
        self._use_cases = ordered
        self._by_use_case = by_use_case
        self._by_source = by_source

    @property
    def use_cases(self) -> tuple[UseCase, ...]:
        """Declaration order, which is the order the tree renders them in."""
        return self._use_cases

    def use_case(self, use_case_id: str) -> UseCase | None:
        return self._by_use_case.get(use_case_id)

    def source(self, use_case_id: str, source_id: str) -> InventorySource | None:
        """The source, only when it is genuinely filed under that use case.

        A token pairing a real source with the wrong use case answers None,
        which the caller turns into a rejection. That mismatch is what a
        hand-edited id looks like.
        """
        source = self._by_source.get(source_id)
        if source is None or source.use_case_id != use_case_id:
            return None
        return source

    def source_ids(self) -> tuple[str, ...]:
        """Every selectable source id, in declaration order."""
        return tuple(
            source.source_id
            for use_case in self._use_cases
            for source in use_case.sources
        )

    def sources(self) -> Sequence[InventorySource]:
        return tuple(
            source for use_case in self._use_cases for source in use_case.sources
        )


__all__ = [
    "CAPABILITIES",
    "InventoryDefinitionError",
    "InventoryRegistry",
    "InventorySource",
    "SourceBinding",
    "SourceType",
    "UseCase",
]
