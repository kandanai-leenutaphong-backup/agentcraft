"""Node ids — an opaque, query-safe token that decodes to one call.

WHY OPAQUE
----------
A node id has to survive resource ids, container names, blob paths and index
names containing ``/``, ``:``, spaces and unicode. A delimiter-joined id
cannot: the first name with the delimiter in it either breaks parsing or
forces an escaping scheme nobody agrees on. Base64url of canonical JSON is
query-safe by construction and round-trips anything.

WHAT IT MEANS
-------------
The token is not a location in a tree; it is the arguments of one call plus
the kind of the node itself::

    {"v": 1, "s": <service>, "l": <level>, "p": [<coordinate strings>], "k": <kind>}

``root`` is the one literal id.

WHY THE VOCABULARY IS DECLARED HERE AND NOT READ FROM THE REGISTRY
------------------------------------------------------------------
The levels below are *this component's* addressable coordinates, not
``azdata``'s enumeration levels, and they differ deliberately: ``estate``
declares a ``properties`` level the library has no concept of, and omits the
``subscription`` level because the root is a literal id nobody mints. The
hierarchy belongs to the explorer, so its vocabulary does too.

WHY THE FIRST COORDINATE IS ALWAYS AN ARM RESOURCE ID
-----------------------------------------------------
Every data-plane branch hangs off a resource, and every per-service
coordinate a discoverer needs — subscription, resource group, account name,
search endpoint, registry login server — is derivable from that one id. One
convention means a node id stays stable when a service changes how it is
addressed, and it removes the class of bug where a token carries a stale
account name for a resource that has since moved.

WHY EVERY REJECTION IS HERE AND NOT AT THE HANDLER
--------------------------------------------------
This module is pure: no I/O, no settings, no registry object. It is handed
nothing and answers yes or no. That makes every rejection row in the contract
directly testable without a server, and it keeps the handler unable to accept
a token the codec would refuse.

Depth is intrinsically bounded: ``l`` must be a declared level, levels are
finite, and ``p`` is capped, so no crafted id can walk deeper than the
deepest declared level.

The caller must never echo the submitted token or any decoded fragment back
to the client. :func:`token_digest` exists so a rejected token can be
correlated in a debug log without becoming a reflection surface.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass

#: The one literal id. Everything else is a token.
ROOT_ID = "root"

#: Checked before decoding: a megabyte of base64 must not reach the decoder.
#: Larger than a hierarchy-only tree needed, because a coordinate is now an
#: ARM resource id or a blob path, both long by construction.
MAX_TOKEN_CHARS = 8192

#: A coordinate below a service root. Four is deeper than any declared
#: hierarchy here, so the cap can never reject a legitimate node.
MAX_PATH_SEGMENTS = 4

#: One segment. A blob name may be 1024 characters; an ARM id is shorter.
MAX_PATH_SEGMENT_CHARS = 1024

_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_-]+$")

#: Every kind the wire contract declares: structure, the universal leaf, then
#: one group per data plane.
NODE_KINDS: tuple[str, ...] = (
    "root",
    "resource_group",
    "resource_type",
    "resource",
    "collection",
    "arm_child",
    "properties",
    "blob_container",
    "blob_folder",
    "blob",
    "cosmos_database",
    "cosmos_container",
    "gremlin_database",
    "gremlin_graph",
    "kusto_database",
    "kusto_table",
    "search_index",
    "search_field",
    "log_table",
    "registry_repository",
    "registry_tag",
)

#: The addressable coordinates. A level absent here cannot appear in a token
#: even where ``azdata`` declares it: ``estate/subscription`` is expanded only
#: by the literal root id, so nothing may mint one.
LEVELS_BY_SERVICE: dict[str, tuple[str, ...]] = {
    "estate": (
        "resource_group",
        "type",
        "resource",
        "collection",
        "child",
        "properties",
    ),
    "blob": ("account", "container", "blob"),
    "cosmos": ("account", "database", "container"),
    "gremlin": ("account", "database", "graph"),
    "kusto": ("cluster", "database", "table"),
    "search": ("service", "index", "field"),
    "logs": ("workspace", "table"),
    "acr": ("registry", "repository", "tag"),
}

#: Which kinds may legally appear at a ``(service, level)`` coordinate. A
#: token whose kind disagrees with its coordinate is malformed even though
#: every field is individually valid — that mismatch is exactly what a
#: hand-crafted id looks like.
KINDS_BY_COORDINATE: dict[tuple[str, str], frozenset[str]] = {
    ("estate", "resource_group"): frozenset({"resource_group"}),
    ("estate", "type"): frozenset({"resource_type"}),
    ("estate", "resource"): frozenset({"resource"}),
    ("estate", "collection"): frozenset({"collection"}),
    ("estate", "child"): frozenset({"arm_child"}),
    ("estate", "properties"): frozenset({"properties"}),
    ("blob", "account"): frozenset({"collection"}),
    ("blob", "container"): frozenset({"blob_container", "blob_folder"}),
    ("blob", "blob"): frozenset({"blob"}),
    ("cosmos", "account"): frozenset({"collection"}),
    ("cosmos", "database"): frozenset({"cosmos_database"}),
    ("cosmos", "container"): frozenset({"cosmos_container"}),
    ("gremlin", "account"): frozenset({"collection"}),
    ("gremlin", "database"): frozenset({"gremlin_database"}),
    ("gremlin", "graph"): frozenset({"gremlin_graph"}),
    ("kusto", "cluster"): frozenset({"collection"}),
    ("kusto", "database"): frozenset({"kusto_database"}),
    ("kusto", "table"): frozenset({"kusto_table"}),
    ("search", "service"): frozenset({"collection"}),
    ("search", "index"): frozenset({"search_index"}),
    ("search", "field"): frozenset({"search_field"}),
    ("logs", "workspace"): frozenset({"collection"}),
    ("logs", "table"): frozenset({"log_table"}),
    ("acr", "registry"): frozenset({"collection"}),
    ("acr", "repository"): frozenset({"registry_repository"}),
    ("acr", "tag"): frozenset({"registry_tag"}),
}

#: A leaf has no children. Asking to expand one answers ``empty`` without a
#: discovery call, which is also true. Several still have *contents*: having
#: nothing below you and having nothing to say are different facts.
LEAF_KINDS: frozenset[str] = frozenset(
    {
        "properties",
        "blob",
        "cosmos_container",
        "gremlin_graph",
        "kusto_table",
        "search_field",
        "log_table",
        "registry_tag",
    }
)

#: Which kinds have contents, and which reader answers for them.
#: ``search_index`` is both expandable and readable — its fields are a
#: hierarchy and its documents are contents.
CONTENT_BY_KIND: dict[str, tuple[str, str]] = {
    "properties": ("estate", "properties"),
    "blob": ("blob", "blob"),
    "cosmos_container": ("cosmos", "documents"),
    "gremlin_graph": ("gremlin", "documents"),
    "kusto_table": ("kusto", "rows"),
    "search_index": ("search", "documents"),
    "log_table": ("logs", "rows"),
}


class InvalidNode(Exception):
    """The token is not one this server minted. The reason never leaves here."""


@dataclass(frozen=True, slots=True)
class NodeRef:
    """One call, decoded."""

    service: str
    level: str
    path: tuple[str, ...]
    kind: str

    @property
    def is_leaf(self) -> bool:
        return self.kind in LEAF_KINDS

    @property
    def content(self) -> tuple[str, str] | None:
        """``(service, content kind)``, or None when this node has no contents."""
        return CONTENT_BY_KIND.get(self.kind)


def encode_node(ref: NodeRef) -> str:
    """Canonical JSON, base64url, unpadded. Same ref, same token, always."""
    payload = {
        "v": 1,
        "s": ref.service,
        "l": ref.level,
        "p": list(ref.path),
        "k": ref.kind,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def is_root(token: str | None) -> bool:
    """A missing ``node`` and the literal ``root`` are the same request."""
    return token is None or token == "" or token == ROOT_ID


def decode_node(token: str) -> NodeRef:
    """Decode and validate. Raises :class:`InvalidNode`, never returns junk."""
    if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS:
        raise InvalidNode("token length")
    if not _TOKEN_CHARS.match(token):
        raise InvalidNode("token alphabet")

    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise InvalidNode("token encoding") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidNode("token payload") from exc

    if not isinstance(payload, dict):
        raise InvalidNode("payload shape")
    if payload.get("v") != 1:
        raise InvalidNode("payload version")

    service = payload.get("s")
    level = payload.get("l")
    kind = payload.get("k")
    if not isinstance(service, str) or service not in LEVELS_BY_SERVICE:
        raise InvalidNode("unknown service")
    if not isinstance(level, str) or level not in LEVELS_BY_SERVICE[service]:
        raise InvalidNode("unknown level")
    if not isinstance(kind, str) or kind not in NODE_KINDS:
        raise InvalidNode("unknown kind")
    if kind not in KINDS_BY_COORDINATE.get((service, level), frozenset()):
        raise InvalidNode("kind inconsistent with coordinate")

    path = payload.get("p", [])
    if not isinstance(path, list) or len(path) > MAX_PATH_SEGMENTS:
        raise InvalidNode("path shape")
    for segment in path:
        if not isinstance(segment, str) or len(segment) > MAX_PATH_SEGMENT_CHARS:
            raise InvalidNode("path segment")

    return NodeRef(service=service, level=level, path=tuple(path), kind=kind)


def token_digest(token: str) -> str:
    """A short SHA-256 prefix. Loggable; the token itself is not."""
    return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()[:12]


__all__ = [
    "CONTENT_BY_KIND",
    "InvalidNode",
    "KINDS_BY_COORDINATE",
    "LEAF_KINDS",
    "LEVELS_BY_SERVICE",
    "MAX_PATH_SEGMENTS",
    "MAX_PATH_SEGMENT_CHARS",
    "MAX_TOKEN_CHARS",
    "NODE_KINDS",
    "NodeRef",
    "ROOT_ID",
    "decode_node",
    "encode_node",
    "is_root",
    "token_digest",
]
