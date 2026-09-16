"""Node ids — an opaque, query-safe token that decodes to one allowlisted call.

ADAPTED from `resource_explorer_api/nodes.py`. See `PROVENANCE.md`.

WHY OPAQUE
----------
A node id has to survive identifiers containing ``/``, ``:``, spaces and
unicode. A delimiter-joined id cannot: the first name with the delimiter in
it either breaks parsing or forces an escaping scheme nobody agrees on.
Base64url of canonical JSON is query-safe by construction and round-trips
anything.

WHAT IT MEANS
-------------
The token is not a location in a tree; it is the arguments of one call plus
the kind of the node itself::

    {"v": 1, "s": "inventory", "l": <level>, "p": [<ids>], "k": <kind>}

``root`` is the one literal id.

WHY THE COORDINATES ARE IDENTIFIERS AND NEVER ENDPOINTS
--------------------------------------------------------
This is the difference between this codec and the one it was adapted from.
Upstream carried an ARM resource id in ``p[0]`` and derived every service
coordinate from it, which is right for a browser over a whole subscription.
Here a token carries **only a use-case id and a source id**, and every
endpoint, database, table, graph and index name is looked up server-side in
the registry. A forged token can therefore name a source that does not
exist — which is rejected — but it can never name a cluster, a database or a
table, because there is nowhere in the token to put one.

WHY EVERY REJECTION IS HERE AND NOT AT THE HANDLER
--------------------------------------------------
This module is pure: no I/O, no settings, no reader object. It is handed a
string and answers yes or no. That makes every rejection row directly
testable without a server, and it keeps the handler unable to accept a token
the codec would refuse.

Depth is intrinsically bounded: ``l`` must be a declared level, levels are
finite, and ``p`` is capped, so no crafted id can walk deeper than
``source``.

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
#: Far larger than two identifiers need, and still a hard ceiling.
MAX_TOKEN_CHARS = 4096

#: A use-case id and a source id. Two is the whole hierarchy.
MAX_PATH_SEGMENTS = 2

#: One segment. Identifiers are short by construction; this is the ceiling,
#: not the expectation.
MAX_PATH_SEGMENT_CHARS = 128

_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_-]+$")

#: The one service this codec addresses. Kept as a field rather than dropped
#: so that a second inventory service could be added without a schema break.
SERVICE = "inventory"

#: Every kind the wire contract declares.
NODE_KINDS: tuple[str, ...] = ("root", "use_case", "source")

#: The addressable coordinates. ``root`` is absent: it is expanded only by
#: the literal root id, so nothing may mint a token for it.
LEVELS_BY_SERVICE: dict[str, tuple[str, ...]] = {
    SERVICE: ("use_case", "source"),
}

#: Which kinds may legally appear at a ``(service, level)`` coordinate. A
#: token whose kind disagrees with its coordinate is malformed even though
#: every field is individually valid — that mismatch is exactly what a
#: hand-crafted id looks like.
KINDS_BY_COORDINATE: dict[tuple[str, str], frozenset[str]] = {
    (SERVICE, "use_case"): frozenset({"use_case"}),
    (SERVICE, "source"): frozenset({"source"}),
}

#: How many path segments each level requires. Exact, not a maximum: a
#: ``source`` token with one segment is missing its use case, and a
#: ``use_case`` token with two is carrying something nobody put there.
SEGMENTS_BY_LEVEL: dict[str, int] = {"use_case": 1, "source": 2}

#: A leaf has no children. Asking to expand one answers ``empty`` without a
#: registry walk, which is also true. A source still has *contents*: having
#: nothing below you and having nothing to say are different facts.
LEAF_KINDS: frozenset[str] = frozenset({"source"})

#: Which kinds have contents.
CONTENT_KINDS: frozenset[str] = frozenset({"source"})


class InvalidNode(Exception):
    """The token is not one this server minted. The reason never leaves here."""


@dataclass(frozen=True, slots=True)
class NodeRef:
    """One call, decoded. Identifiers only."""

    service: str
    level: str
    path: tuple[str, ...]
    kind: str

    @property
    def is_leaf(self) -> bool:
        return self.kind in LEAF_KINDS

    @property
    def has_content(self) -> bool:
        return self.kind in CONTENT_KINDS

    @property
    def use_case_id(self) -> str:
        return self.path[0] if self.path else ""

    @property
    def source_id(self) -> str:
        return self.path[1] if len(self.path) > 1 else ""


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


def use_case_node(use_case_id: str) -> str:
    """The token that expands one use case."""
    return encode_node(
        NodeRef(service=SERVICE, level="use_case", path=(use_case_id,), kind="use_case")
    )


def source_node(use_case_id: str, source_id: str) -> str:
    """The token that addresses one source inside one use case."""
    return encode_node(
        NodeRef(
            service=SERVICE,
            level="source",
            path=(use_case_id, source_id),
            kind="source",
        )
    )


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
        if not segment:
            raise InvalidNode("empty path segment")
    if len(path) != SEGMENTS_BY_LEVEL[level]:
        raise InvalidNode("path arity")

    return NodeRef(service=service, level=level, path=tuple(path), kind=kind)


def token_digest(token: str) -> str:
    """A short SHA-256 prefix. Loggable; the token itself is not."""
    return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()[:12]


__all__ = [
    "CONTENT_KINDS",
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
    "SEGMENTS_BY_LEVEL",
    "SERVICE",
    "decode_node",
    "encode_node",
    "is_root",
    "source_node",
    "token_digest",
    "use_case_node",
]
