"""The ARM scope hierarchy, and the difference between exact and inherited.

WHY THIS EXISTS
---------------
Two questions look identical and are not:

* *Is there an assignment at exactly this scope?* — decidable, and what a
  plan and a read-back must both compare.
* *Does this principal have effective access here?* — inherited from any
  ancestor, possibly through a group, possibly time-bound, possibly denied.
  Not decidable from a list at one scope.

Conflating them is how a teardown reports success while a subscription-level
Owner assignment keeps every door open, and how a read-back "passes" on an
assignment the plan never made. Every comparison in this package is exact
unless the caller asked for effective access, and effective access is never
reported as complete (see :mod:`azaccess.model`, ``Completeness``).

DERIVABLE ANCESTRY ONLY
-----------------------
Ancestors are derived from the id text. Resource, resource group and
subscription are all present in the id, so those are exact. A subscription's
*management group* chain is not in the id and is not derivable — which is
precisely why effective access can never be closed from an id alone.

A SCOPE IS REFUSED, NOT REPAIRED
--------------------------------
An earlier version of this module *normalised*: it collapsed ``//`` and
stripped trailing slashes and accepted everything else, including ``?``, ``#``
and dot segments. Two consequences were reproduced. A resource name containing
``?api-version=2015-07-01&x=`` produced a list URL whose *first* api-version
won, so the caller silently drove a different API contract. And a scope whose
resource name was followed by three parent-directory segments and another
resource group passed a prefix allowlist, then resolved server-side into the
scope the allowlist existed to forbid.

So normalisation that could change the target is gone. A scope either is a
well-formed ARM id built from validated segments, or it is refused here —
before a request is built and before any allowlist is consulted. The one
repair that cannot change a target survives: trailing slashes are dropped.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from azaccess.errors import CoordinateError

LEVELS: tuple[str, ...] = (
    "management-group",
    "subscription",
    "resource-group",
    "resource",
    "child-resource",
)

#: One path segment. Conservative on purpose: ARM resource, resource-group,
#: management-group and provider names are drawn from letters, digits and
#: ``-_.()``. Anything outside that — a separator, an encoded separator, a
#: query character, whitespace — is refused rather than escaped.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._()-]{1,260}$")

#: Characters that must never appear anywhere in a scope, with the reason each
#: one is dangerous, because "invalid character" is not an actionable message.
_FORBIDDEN_CHARS: tuple[tuple[str, str], ...] = (
    ("?", "a query string would inject an api-version ahead of the real one"),
    ("#", "a fragment never reaches the server and only defeats host checks"),
    ("&", "a parameter separator has no meaning inside an ARM id"),
    ("%", "percent-encoding hides separators: %2F is '/' after the server decodes it"),
    ("\\", "a backslash is a separator to some parsers and a name character to others"),
    ("@", "userinfo syntax inside a scope only ever exists to be misread"),
    (" ", "a space would be encoded downstream and change the target"),
)

_MG_RE = re.compile(
    r"^/providers/Microsoft\.Management/managementGroups/([^/]+)$", re.I
)
_SUB_RE = re.compile(r"^/subscriptions/([^/]+)$", re.I)
_RG_RE = re.compile(r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)$", re.I)
_RES_RE = re.compile(
    r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/([^/]+)/(.+)$", re.I
)


def scope_segments(value: str) -> tuple[str, ...]:
    """The validated segments of a scope, in order."""
    return tuple(p for p in normalize_scope(value).split("/") if p)


def normalize_scope(value: str) -> str:
    """Validate an ARM id and drop trailing slashes. Case is preserved.

    Case is preserved because ARM echoes back what you sent and a diff that
    silently lowercased would print a difference that is not there. Comparison
    is case-insensitive; storage is verbatim.

    Everything else is a refusal, not a repair: ``//``, ``.``, ``..``, query
    and fragment characters, percent-encoding and control characters each name
    a *different* target once a server has parsed them, and quietly rewriting
    one into another is how a scope allowlist is defeated.
    """
    text = str(value or "").strip()
    if not text.startswith("/"):
        raise CoordinateError(f"scope must be an ARM id starting with '/': {text[:60]!r}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise CoordinateError("scope contains control characters")
    for char, why in _FORBIDDEN_CHARS:
        if char in text:
            raise CoordinateError(
                f"scope may not contain {char!r}: {why} — got {text[:80]!r}"
            )
    trimmed = text.rstrip("/")
    if not trimmed:
        raise CoordinateError("'/' is not an assignable scope")
    segments = trimmed[1:].split("/")
    for segment in segments:
        if not segment:
            raise CoordinateError(
                f"scope has an empty segment ('//'); refusing to collapse it, "
                f"because the collapsed id is a different id: {text[:80]!r}"
            )
        if segment in (".", ".."):
            raise CoordinateError(
                f"scope contains a '{segment}' segment; ARM resolves dot segments "
                f"server-side, so this id names a scope the allowlist never saw: "
                f"{text[:80]!r}"
            )
        if not _SEGMENT_RE.match(segment):
            raise CoordinateError(
                f"scope segment {segment[:40]!r} is not a valid ARM name: expected "
                f"letters, digits, '-', '_', '.' or parentheses"
            )
    return trimmed


@dataclass(frozen=True)
class Scope:
    """One ARM scope, parsed into the coordinates a plan needs."""

    value: str
    level: str
    subscription_id: str = ""
    resource_group: str = ""
    provider_namespace: str = ""
    resource_type: str = ""
    resource_name: str = ""
    management_group: str = ""

    @classmethod
    def parse(cls, value: str) -> "Scope":
        text = normalize_scope(value)
        match = _MG_RE.match(text)
        if match:
            return cls(value=text, level="management-group", management_group=match.group(1))
        match = _SUB_RE.match(text)
        if match:
            return cls(value=text, level="subscription", subscription_id=match.group(1))
        match = _RG_RE.match(text)
        if match:
            return cls(
                value=text,
                level="resource-group",
                subscription_id=match.group(1),
                resource_group=match.group(2),
            )
        match = _RES_RE.match(text)
        if match:
            namespace, tail = match.group(3), match.group(4)
            parts = tail.split("/")
            if len(parts) < 2:
                raise CoordinateError(f"resource scope is missing a name: {text}")
            level = "resource" if len(parts) == 2 else "child-resource"
            return cls(
                value=text,
                level=level,
                subscription_id=match.group(1),
                resource_group=match.group(2),
                provider_namespace=namespace,
                resource_type="/".join(parts[:-1]),
                resource_name=parts[-1],
            )
        raise CoordinateError(f"not a recognised ARM scope: {text[:80]!r}")

    def ancestors(self) -> tuple["Scope", ...]:
        """Scopes an assignment could be inherited from, derivable from the id.

        Not the whole truth by construction: a management-group chain above a
        subscription is not encoded in the id. Callers reporting effective
        access must say so rather than implying closure.
        """
        out: list[Scope] = []
        if self.level in ("resource", "child-resource"):
            parts = self.value.split("/")
            # Walk child segments back to the top-level resource.
            while len(parts) > 9:
                parts = parts[:-2]
                out.append(Scope.parse("/".join(parts)))
        if self.resource_group:
            out.append(
                Scope.parse(
                    f"/subscriptions/{self.subscription_id}"
                    f"/resourceGroups/{self.resource_group}"
                )
            )
        if self.subscription_id:
            out.append(Scope.parse(f"/subscriptions/{self.subscription_id}"))
        seen: set[str] = {self.value.lower()}
        unique: list[Scope] = []
        for scope in out:
            if scope.value.lower() not in seen:
                seen.add(scope.value.lower())
                unique.append(scope)
        return tuple(unique)

    def is_exact(self, other: "Scope | str") -> bool:
        """True only when the two ids name the same scope."""
        value = other.value if isinstance(other, Scope) else normalize_scope(other)
        return self.value.lower() == value.lower()

    def contains(self, other: "Scope | str") -> bool:
        """True when ``other`` is at or beneath this scope.

        Compared segment by segment, not by string prefix: ``/…/rg-app`` is not
        an ancestor of ``/…/rg-application`` and a prefix test says it is.
        """
        child = other if isinstance(other, Scope) else Scope.parse(other)
        return contains_segments(self.value, child.value)

    def describe(self) -> dict[str, str]:
        return {"scope": self.value, "level": self.level}


def contains_segments(ancestor: str, candidate: str) -> bool:
    """True when ``candidate`` is at or beneath ``ancestor``, by segment.

    Both sides are validated first, so this can never be asked about a string
    that ARM would resolve into something else.
    """
    parent = [s.lower() for s in scope_segments(ancestor)]
    child = [s.lower() for s in scope_segments(candidate)]
    if len(child) < len(parent):
        return False
    return child[: len(parent)] == parent


def scope_depth(value: str) -> int:
    """Segment count, used to order a plan broad-to-narrow."""
    return len(scope_segments(value))


__all__ = ["LEVELS", "Scope", "contains_segments", "normalize_scope",
           "scope_depth", "scope_segments"]
