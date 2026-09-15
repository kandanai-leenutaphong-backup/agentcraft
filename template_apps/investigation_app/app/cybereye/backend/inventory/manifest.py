"""Load the data-inventory manifest and resolve its coordinates at the edge.

`control/data_inventory.yaml` declares what exists. This module is the only place
that reads it, and the only place that reads the environment on its behalf: a
coordinate is either a literal in the manifest or the value of a named environment
key, resolved once here and passed down. Nothing deeper than this asks the
environment anything.

Coordinates are validated here, not trusted. Each source type has a finite set of
coordinate names, an endpoint must be a plain `https://` service address, and a
name must look like a resource name. A coordinate is served to the browser in the
detail pane, so a coordinate carrying a SAS query, embedded credentials or a
surprise key field is refused at startup — by name, never by repeating the value.

Authentication does not travel this path at all. Every reader gets its identity
from `azure_credential()` or from an ARM key read performed at runtime; there is
no coordinate, environment key or manifest field through which a secret value
reaches a reader.

A manifest that does not parse is fatal at startup. The alternative — an inventory
that silently serves fewer sources than the repository declares — is worse, because
the missing one looks like a source nobody connected rather than a file nobody fixed.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from app.components.resource_explorer import (
    InventoryDefinitionError,
    InventoryRegistry,
    InventorySource,
    SourceBinding,
    UseCase,
)

from ..config import settings

MANIFEST_PATH = settings.app_root / "control" / "data_inventory.yaml"

#: Every source type the manifest may declare. A new one needs a probe and a wire
#: literal, so it cannot be added here alone.
SOURCE_TYPES = ("adx_table", "gremlin_graph", "search_index", "local_table")

#: Every coordinate each source type may carry. Finite because each name is a
#: parameter of one reader; anything else is a typo or something that does not
#: belong in a payload the browser is shown.
COORDINATES: Mapping[str, tuple[str, ...]] = {
    "adx_table": ("endpoint", "database", "table"),
    "gremlin_graph": ("account", "database", "graph"),
    "search_index": ("endpoint", "index"),
    "local_table": ("database", "table"),
}

#: Coordinates checked as a service address rather than as a name.
ENDPOINT_COORDINATES = frozenset({"endpoint"})

#: What a resource name may look like: an ADX database or table, a Cosmos
#: account or graph, an Azure AI Search index.
RESOURCE_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")


class ManifestError(RuntimeError):
    """The manifest is unusable. Startup fails rather than serving a partial one."""


def _require(block: Mapping[str, Any], key: str, *, where: str) -> Any:
    if key not in block:
        raise ManifestError(f"{where}: missing '{key}'")
    return block[key]


def _string_map(raw: Any, *, where: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ManifestError(f"{where}: expected a mapping")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, float)):
            raise ManifestError(f"{where}: '{key}' must map a name to a scalar")
        out[key] = str(value)
    return out


def _string_list(raw: Any, *, where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ManifestError(f"{where}: expected a list of strings")
    return tuple(raw)


def _check_coordinates(
    coordinates: Mapping[str, str], *, source_type: str, where: str
) -> None:
    """Refuse a coordinate this deployment would not serve. Values are never echoed.

    An empty value is a coordinate nobody set, which is the `unconfigured`
    report and not an error. A non-empty one has to look like what it claims
    to be before it can reach a client or a detail pane.
    """
    allowed = COORDINATES[source_type]
    for name, value in coordinates.items():
        if name not in allowed:
            raise ManifestError(
                f"{where}: coordinate {name!r} is not one of "
                f"{', '.join(allowed)} for a {source_type}"
            )
        text = value.strip()
        if not text:
            continue
        if name in ENDPOINT_COORDINATES:
            _check_endpoint(text, name=name, where=where)
        elif not RESOURCE_NAME.match(text):
            raise ManifestError(
                f"{where}: coordinate {name!r} is not a resource name "
                "(letters, digits, '.', '_' and '-'); the value is not repeated here"
            )


def _check_endpoint(value: str, *, name: str, where: str) -> None:
    """A service address and nothing else: no credentials, no path, no query.

    A SAS URL fails on its query, an embedded credential fails on its userinfo,
    and a container path fails on its path. None of the three is reported back
    with the value, because a startup log is not a place to reprint a secret
    somebody has just mistakenly configured.
    """
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
    except ValueError as exc:
        raise ManifestError(f"{where}: coordinate {name!r} is not a URL") from exc
    if parsed.scheme != "https" or not host:
        raise ManifestError(
            f"{where}: coordinate {name!r} must be an https:// service address"
        )
    if parsed.username or parsed.password:
        raise ManifestError(
            f"{where}: coordinate {name!r} carries embedded credentials; "
            "authentication is injected, never declared"
        )
    if parsed.query or parsed.fragment:
        raise ManifestError(
            f"{where}: coordinate {name!r} carries a query or fragment, which is "
            "how a shared-access signature travels; only a plain service address "
            "is accepted"
        )
    if parsed.path not in ("", "/"):
        raise ManifestError(
            f"{where}: coordinate {name!r} must be a service address with no path"
        )


def _source(block: Any, *, use_case_id: str, env: Mapping[str, str]) -> InventorySource:
    if not isinstance(block, Mapping):
        raise ManifestError(f"use case {use_case_id}: a source must be a mapping")
    source_id = str(_require(block, "id", where=f"use case {use_case_id}"))
    where = f"source {source_id}"
    source_type = str(_require(block, "type", where=where))
    if source_type not in SOURCE_TYPES:
        raise ManifestError(
            f"{where}: type must be one of {', '.join(SOURCE_TYPES)}, not {source_type!r}"
        )

    literal = _string_map(block.get("coordinates"), where=f"{where}.coordinates")
    from_env = _string_map(
        block.get("coordinates_from_env"), where=f"{where}.coordinates_from_env"
    )
    overlap = set(literal) & set(from_env)
    if overlap:
        raise ManifestError(
            f"{where}: {', '.join(sorted(overlap))} declared both literally and from the "
            "environment; one coordinate has one source"
        )

    coordinates = dict(literal)
    for name, key in from_env.items():
        coordinates[name] = str(env.get(key, "")).strip()
    _check_coordinates(coordinates, source_type=source_type, where=where)

    required = _string_list(block.get("required"), where=f"{where}.required")
    unknown = [name for name in required if name not in coordinates]
    if unknown:
        raise ManifestError(
            f"{where}: required coordinate(s) {', '.join(unknown)} are never declared"
        )

    # Environment keys an operator must set: the ones that carry coordinates, plus
    # anything else the connector needs. Declared once, reported everywhere.
    declared_settings = _string_list(block.get("settings"), where=f"{where}.settings")
    keys = tuple(dict.fromkeys((*from_env.values(), *declared_settings)))

    return InventorySource(
        source_id=source_id,
        use_case_id=use_case_id,
        name=str(_require(block, "name", where=where)),
        source_type=source_type,  # type: ignore[arg-type]
        holds=str(block.get("holds", "")).strip(),
        capabilities=_string_list(block.get("capabilities"), where=f"{where}.capabilities"),
        binding=SourceBinding(
            connector=str(_require(block, "connector", where=where)),
            coordinates=coordinates,
            required=required,
            settings=keys,
            reached_by=str(block.get("reached_by", "")).strip(),
            connector_name=str(block.get("connector_name", "")).strip(),
        ),
        provenance=" ".join(str(block.get("provenance", "")).split()),
    )


def load_registry(
    path: Path | None = None, env: Mapping[str, str] | None = None, *, include_local: bool = False
) -> InventoryRegistry:
    """Read the manifest and resolve it against the environment.

    Args:
        path: Manifest location. Defaults to `control/data_inventory.yaml`.
        env: Where environment coordinates are read from. Defaults to `os.environ`.
    """
    source_path = path or MANIFEST_PATH
    environment = os.environ if env is None else env
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"no inventory manifest at {source_path}") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"inventory manifest is not valid YAML: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ManifestError("inventory manifest must be a mapping")
    if raw.get("version") != 1:
        raise ManifestError("inventory manifest version must be 1")

    blocks = raw.get("use_cases")
    if not isinstance(blocks, list) or not blocks:
        raise ManifestError("inventory manifest declares no use cases")

    use_cases: list[UseCase] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            raise ManifestError("a use case must be a mapping")
        if type(block.get("local_only", False)) is not bool:
            raise ManifestError("local_only must be a boolean")
        if block.get("local_only") and not include_local:
            continue
        use_case_id = str(_require(block, "id", where="use case"))
        sources = block.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ManifestError(f"use case {use_case_id}: declares no sources")
        use_cases.append(
            UseCase(
                use_case_id=use_case_id,
                name=str(_require(block, "name", where=f"use case {use_case_id}")),
                summary=" ".join(str(block.get("summary", "")).split()),
                sources=tuple(
                    _source(item, use_case_id=use_case_id, env=environment)
                    for item in sources
                ),
            )
        )

    try:
        return InventoryRegistry(use_cases)
    except InventoryDefinitionError as exc:
        raise ManifestError(str(exc)) from exc


__all__ = [
    "COORDINATES",
    "ENDPOINT_COORDINATES",
    "MANIFEST_PATH",
    "RESOURCE_NAME",
    "SOURCE_TYPES",
    "ManifestError",
    "load_registry",
]
