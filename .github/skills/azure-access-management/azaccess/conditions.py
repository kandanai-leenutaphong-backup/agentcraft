"""ABAC role-assignment conditions: built and serialised here, evaluated by Azure.

THE DISTINCTION THAT MATTERS
----------------------------
This package **serialises** a condition onto a role assignment and compares
conditions textually when it decides whether an observed assignment is the one
that was declared. It does **not** evaluate one. Nothing here can tell you
whether a particular request would be allowed: that decision is made by the
service handling the data-plane call, with request, resource, principal and
environment attributes this process never sees. ``UNEVALUATED_SEMANTICS`` names
``abac-role-assignment-conditions`` in every effective-access answer for exactly
that reason, and an answer that quietly assumed a condition was satisfied would
overstate access in the dangerous direction.

WHAT A CONDITION CAN AND CANNOT DO
----------------------------------
A condition only ever *narrows* the assignment it is attached to. It cannot
grant an action the role does not already carry, and an assignment whose
condition does not match a request falls back to "not allowed by this
assignment", not to "allowed unconditionally". So a condition is a safety
feature, and the failure mode is a condition that looks narrowing and is not —
which is what the refusals below exist to prevent.

THE FORM, FROM THE PUBLISHED SYNTAX
-----------------------------------
A simple condition is one targeted action and one expression::

    (
        (
            !(ActionMatches{'<action>'})
        )
        OR
        (
            <attribute> <operator> <value>
        )
    )

Read it as: if the request is not the targeted action, this condition says
nothing and the assignment applies; if it *is* the targeted action, the
expression must be true. Attribute sources are ``@Request``, ``@Resource``,
``@Principal`` and ``@Environment``.

Conditions are supported on assignments carrying Azure Blob or Queue Storage
data actions — `Storage Blob Data Reader`, `Storage Blob Data Contributor`,
`Storage Blob Data Owner` and the queue equivalents — not on management-plane
roles generally.

VERSION
-------
``conditionVersion`` is ``"2.0"``. Version 1.0 exists and is evaluated by
different rules, so the two are never interchangeable: the version is part of
an assignment's identity (:meth:`AccessDeclaration.fingerprint`) and a v1.0
assignment does not satisfy a v2.0 declaration.

Reference: Azure role assignment condition format and syntax,
https://learn.microsoft.com/azure/role-based-access-control/conditions-format
"""

from __future__ import annotations

import re
from typing import Sequence

from azaccess.errors import CoordinateError

#: The only version this package emits. See the module docstring.
CONDITION_VERSION = "2.0"

#: Versions it will accept from a caller. 1.0 is a real Azure version and is
#: refused here rather than silently re-labelled, because the evaluation rules
#: differ and the caller has to say which they wrote.
SUPPORTED_CONDITION_VERSIONS: frozenset[str] = frozenset({"2.0"})

#: The blob data actions most conditions target, spelled exactly as Azure does.
BLOB_READ_ACTION = (
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"
)
BLOB_WRITE_ACTION = (
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"
)
BLOB_DELETE_ACTION = (
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/delete"
)

#: The resource attribute naming the container an object lives in.
CONTAINER_NAME_ATTRIBUTE = (
    "@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name]"
)

#: The request attribute carrying a blob index tag value. The
#: ``<$key_case_sensitive$>`` delimiter is part of the attribute name.
def blob_tag_attribute(key: str) -> str:
    """The ``@Request`` attribute for one blob index tag key."""
    return (
        "@Request[Microsoft.Storage/storageAccounts/blobServices/containers/"
        f"blobs/tags:{_require_tag_key(key)}<$key_case_sensitive$>]"
    )


_CONTAINER_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])$")
_TAG_KEY = re.compile(r"^[A-Za-z0-9 +\-.:=_/]{1,128}$")
_ACTION = re.compile(r"^[A-Za-z0-9]+(\.[A-Za-z0-9]+)*/[A-Za-z0-9/]+$")


def container_name_condition(
    container_name: str, *, actions: Sequence[str] = (BLOB_READ_ACTION,)
) -> str:
    """A condition restricting the given actions to one container.

    The worked case: `Storage Blob Data Reader` at the storage-account scope,
    conditioned so that reading a blob is only permitted inside one container.

    >>> print(container_name_condition("blobs-example-container"))
    (
     (
      !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})
     )
     OR
     (
      @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringEquals 'blobs-example-container'
     )
    )

    The comparison is ``StringEquals``, so the value is a literal. A wildcard in
    it is refused rather than emitted: ``StringEquals 'prod*'`` matches a
    container literally named ``prod*`` and nothing else, which reads as a
    narrowing rule and behaves as a rule that never matches. Use an explicit
    ``StringLike`` expression if prefix matching is what is wanted, and say so.
    """
    name = _require_container_name(container_name)
    return _simple_condition(
        actions, f"{CONTAINER_NAME_ATTRIBUTE} StringEquals '{name}'"
    )


def blob_tag_condition(
    key: str, value: str, *, actions: Sequence[str] = (BLOB_READ_ACTION,)
) -> str:
    """A condition restricting the given actions to blobs carrying one index tag."""
    return _simple_condition(
        actions,
        f"{blob_tag_attribute(key)} StringEquals '{_require_literal(value)}'",
    )


def require_condition(condition: str, version: str = "") -> tuple[str, str]:
    """Validate a caller-authored condition and its version.

    Returns ``(condition, version)`` with the version defaulted to
    :data:`CONDITION_VERSION`. Refuses a version with no condition, an
    unsupported version, an unbalanced expression, and a quote-unbalanced one —
    the shapes that ARM rejects with a message naming a character offset and
    nothing else.

    This is a **syntactic** check on a string that will be sent. It is not an
    evaluation, and passing it says nothing about which requests the condition
    will allow.
    """
    text = str(condition or "").strip()
    wanted = str(version or "").strip()
    if not text:
        if wanted:
            raise CoordinateError(
                "a conditionVersion was given with no condition; a version "
                "alone changes nothing and hides the omission"
            )
        return "", ""
    if wanted and wanted not in SUPPORTED_CONDITION_VERSIONS:
        raise CoordinateError(
            f"condition version {wanted!r} is not one this package emits "
            f"({sorted(SUPPORTED_CONDITION_VERSIONS)}); a 1.0 expression is "
            f"evaluated by different rules and must not be relabelled as 2.0"
        )
    if text.count("(") != text.count(")"):
        raise CoordinateError(
            "condition has unbalanced parentheses; ARM answers a parse error "
            "naming a character offset and nothing else"
        )
    if text.count("'") % 2:
        raise CoordinateError("condition has an unbalanced quote")
    if "ActionMatches" not in text:
        raise CoordinateError(
            "condition targets no action (no ActionMatches{...}); an expression "
            "with no action gate applies to every action in the role and is "
            "almost never what was meant"
        )
    return text, wanted or CONDITION_VERSION


def _simple_condition(actions: Sequence[str], expression: str) -> str:
    gates = [f"  !(ActionMatches{{'{_require_action(a)}'}})" for a in actions]
    if not gates:
        raise CoordinateError("a condition must target at least one action")
    return (
        "(\n"
        " (\n"
        + "\n  AND\n".join(gates)
        + "\n )\n"
        " OR\n"
        " (\n"
        f"  {expression}\n"
        " )\n"
        ")"
    )


def _require_action(action: str) -> str:
    text = str(action or "").strip()
    if "*" in text or "?" in text:
        raise CoordinateError(
            f"refusing to build a condition around the wildcard action "
            f"{text!r}: a wildcard changes which requests the expression gates, "
            f"and getting that backwards silently widens the assignment. Name "
            f"the exact data actions"
        )
    if not _ACTION.match(text):
        raise CoordinateError(
            f"{text!r} is not an Azure action of the form "
            f"'Microsoft.Storage/storageAccounts/.../read'"
        )
    return text


def _require_container_name(name: str) -> str:
    text = str(name or "").strip()
    if not _CONTAINER_NAME.match(text):
        raise CoordinateError(
            f"{text!r} is not a valid blob container name (3-63 characters, "
            f"lowercase letters, digits and hyphens); wildcards and quotes are "
            f"refused because StringEquals compares literals"
        )
    return text


def _require_tag_key(key: str) -> str:
    text = str(key or "").strip()
    if not _TAG_KEY.match(text):
        raise CoordinateError(f"{text!r} is not a usable blob index tag key")
    return text


def _require_literal(value: str) -> str:
    text = str(value or "")
    if "'" in text or "\n" in text or "\r" in text:
        raise CoordinateError(
            "a condition literal may not contain a quote or a newline; the "
            "expression is a string and there is nothing to escape into"
        )
    return text


__all__ = [
    "BLOB_DELETE_ACTION",
    "BLOB_READ_ACTION",
    "BLOB_WRITE_ACTION",
    "CONDITION_VERSION",
    "CONTAINER_NAME_ATTRIBUTE",
    "SUPPORTED_CONDITION_VERSIONS",
    "blob_tag_attribute",
    "blob_tag_condition",
    "container_name_condition",
    "require_condition",
]
