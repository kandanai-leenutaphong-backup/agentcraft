"""Catalogue and affordance lint — review the tool surface as a surface.

WHY THIS EXISTS
---------------
Tools are added one at a time and reviewed one at a time, so nobody ever
reads the set. The set is what the caller sees. Two failures follow.

**Overlap.** Two tools whose ``call_when`` sentences do not distinguish
them make every choice between them a coin flip, and the caller's failures
look like reasoning failures rather than what they are.

**Accumulation.** A tool that no agent registers still costs review time
and still ships. Four compound tools survived a surface reset here purely
because nobody re-read the list (GOTCHAS.md G5).

:func:`catalogue` renders the whole surface as one page. :func:`lint`
checks the rules that can be checked mechanically, so "this tool is well
shaped" is an exit code rather than an opinion.

WHAT LINT CANNOT CHECK
----------------------
Whether ``call_when`` is *true*, and whether two tools genuinely differ.
Those need the weight meter and a human. The linter checks that the
sentences exist, that parameters say where their values come from, and
that free-text parameters are not standing in for enumerations.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ._spec import ToolSpec

# A parameter description should say where the value comes from. These are
# the phrasings that do it; the check is a heuristic and reports a warning,
# never a failure.
_SOURCE_HINTS = (
    "from ", "returned by", "as returned", "use the", "output of",
    "listed by", "given by", "one of",
)

# Below this, a "when to call" sentence is not doing the job it exists for.
_MIN_CALL_WHEN_CHARS = 25

# A surface wider than this is worth defending explicitly: every tool is
# attention spent on every decision.
DEFAULT_MAX_TOOLS = 8


@dataclass
class Finding:
    """One lint result. ``level`` is ``error`` or ``warn``."""

    level: str
    tool: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:>5}  {self.tool}: {self.message}"


def lint(specs: Sequence[ToolSpec], *, max_tools: int = DEFAULT_MAX_TOOLS) -> list[Finding]:
    """Check a tool surface against the affordance rules.

    Errors are objective and block. Warnings need judgement.
    """
    findings: list[Finding] = []

    for spec in specs:
        if not spec.purpose.strip():
            findings.append(Finding("error", spec.name, "no purpose"))
        if len(spec.call_when.strip()) < _MIN_CALL_WHEN_CHARS:
            findings.append(
                Finding(
                    "error",
                    spec.name,
                    "call_when is missing or too short — this is the sentence "
                    "the caller chooses by",
                )
            )
        if not spec.params:
            findings.append(
                Finding("warn", spec.name, "no parameters — is this a fixed report?")
            )

        for param in spec.params:
            if not param.description.strip():
                findings.append(
                    Finding("error", spec.name, f"{param.name} has no description")
                )
                continue
            if param.validator is None:
                findings.append(
                    Finding(
                        "warn",
                        spec.name,
                        f"{param.name} has no validator — unvalidated input reaches "
                        "the backend and its failure teaches the caller nothing",
                    )
                )
            description = param.description.lower()
            if not any(hint in description for hint in _SOURCE_HINTS):
                findings.append(
                    Finding(
                        "warn",
                        spec.name,
                        f"{param.name} does not say where its value comes from — "
                        "the caller will invent one (GOTCHAS.md G12)",
                    )
                )

        if spec.params and not spec.dedupe_on:
            findings.append(
                Finding(
                    "warn",
                    spec.name,
                    "no dedupe_on — repeat calls will re-query the backend "
                    "(GOTCHAS.md G10)",
                )
            )
        for name in spec.dedupe_on:
            if spec.param(name) is None:
                findings.append(
                    Finding(
                        "error",
                        spec.name,
                        f"dedupe_on names {name!r}, which is not a parameter",
                    )
                )

    names = [s.name for s in specs]
    duplicates = {n for n in names if names.count(n) > 1}
    for name in sorted(duplicates):
        findings.append(Finding("error", name, "duplicate tool name"))

    if len(specs) > max_tools:
        findings.append(
            Finding(
                "warn",
                "<surface>",
                f"{len(specs)} tools exceeds the {max_tools} the surface is "
                "budgeted for — every tool is attention spent on every decision",
            )
        )

    return findings


def catalogue(specs: Sequence[ToolSpec], title: str = "Tool surface") -> str:
    """Render the whole surface as one reviewable page."""
    lines = [f"# {title}", "", f"{len(specs)} tools.", ""]
    lines += ["| tool | purpose | when to call |", "| --- | --- | --- |"]
    for spec in specs:
        when = spec.call_when.strip().replace("\n", " ")
        lines.append(f"| `{spec.name}` | {spec.purpose.strip()} | {when} |")

    lines += ["", "## Detail", ""]
    for spec in specs:
        lines += [f"### `{spec.name}`", "", spec.description(), ""]
        if spec.replaces:
            lines += [f"Promoted from: {spec.replaces}", ""]
        if spec.params:
            lines += ["| parameter | required | description |", "| --- | --- | --- |"]
            for param in spec.params:
                lines.append(
                    f"| `{param.name}` | {'yes' if param.required else 'no'} | "
                    f"{param.describe()} |"
                )
            lines.append("")
        if spec.dedupe_on:
            lines += [
                f"Repeat calls identified by: {', '.join(spec.dedupe_on)} "
                f"(max {spec.max_calls} per turn).",
                "",
            ]
    return "\n".join(lines) + "\n"


def json_schema(spec: ToolSpec) -> dict:
    """A JSON-schema-shaped description, for an SDK that wants one.

    Types are reported as strings because the validators are the type
    system here: a schema that claimed ``integer`` while the validator
    accepted a numeric string would be a second contract to keep in sync.
    """
    properties = {
        param.name: {"type": "string", "description": param.describe()}
        for param in spec.params
    }
    return {
        "name": spec.name,
        "description": spec.description(),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": [p.name for p in spec.params if p.required],
        },
    }


__all__ = ["DEFAULT_MAX_TOOLS", "Finding", "catalogue", "json_schema", "lint"]
