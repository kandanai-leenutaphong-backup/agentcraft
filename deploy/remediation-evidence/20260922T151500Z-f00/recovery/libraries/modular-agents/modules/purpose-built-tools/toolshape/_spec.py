"""ToolSpec — the tool's affordance, declared once and used everywhere.

WHY THIS EXISTS
---------------
Three artefacts have to agree about a tool: the description the model
reads, the validation the code performs, and the catalogue a human
reviews. Written separately they drift within weeks — the description
still mentions a parameter that was renamed, the validator enforces a cap
the description does not mention, and the caller learns the real rule by
failing.

A :class:`ToolSpec` is the one declaration. The description is *generated*
out of that declaration, so a parameter cannot exist without documentation,
and its documented constraint is the enforced constraint by construction.

WHAT THE FIELDS ARE FOR
-----------------------
``purpose`` — what the tool returns, in one line.

``call_when`` — the field that actually changes behaviour. A model with
six plausible tools picks by matching intent to this sentence. "Call this
first to learn what exists" and "call after find_sites, using its code"
are worth more than any amount of parameter prose, because they encode the
*order* that a naive caller gets wrong.

``returns`` — the shape, so the caller can plan a second call before
making the first.

``dedupe_on`` — the arguments that make a call identical to an earlier
one. Naming them is what lets a repeat be answered from the ledger
instead of the backend.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Every string is caller-supplied. This module renders and validates
structure; it never inspects meaning.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ._validators import Rejection, Validator


@dataclass(frozen=True)
class Param:
    """One tool parameter, with the rule the caller is told and held to.

    Args:
        name: Parameter name, matching the function signature.
        description: What the value means. State **where the value comes
            from** — "the code returned by find_sites" — or the caller will
            invent one that looks right and get an empty result
            (GOTCHAS.md G12).
        validator: The check. Its ``accepted`` text is appended to the
            generated description, so the documented form and the enforced
            form cannot diverge.
        required: When False, a missing or None value skips validation.
        default: Value substituted when absent.
    """

    name: str
    description: str
    validator: Validator | None = None
    required: bool = True
    default: Any = None

    def describe(self) -> str:
        """The caller-visible description: meaning, then accepted form."""
        parts = [self.description.strip()]
        if self.validator is not None:
            parts.append(f"Accepts {self.validator.accepted}.")
        if not self.required:
            parts.append("Optional.")
        return " ".join(p for p in parts if p)


@dataclass(frozen=True)
class ToolSpec:
    """A purpose-built tool's whole affordance.

    Args:
        name: Tool name as the caller sees it.
        purpose: One line: what it returns.
        call_when: When to reach for this tool rather than another, and in
            what order relative to its siblings.
        params: Ordered parameters.
        returns: The result shape, in one line.
        dedupe_on: Parameter names whose values identify a repeat call.
            Empty disables duplicate suppression.
        max_calls: Identical calls allowed per turn before the ledger
            answers from the transcript instead of the backend.
        cross_checks: Callables taking the validated argument dict and
            returning a Rejection or None. For rules spanning parameters.
        replaces: Optional note naming the raw capability this tool was
            promoted from. Carried into the catalogue so a reviewer can see
            which raw surfaces are now redundant (GOTCHAS.md G5).
    """

    name: str
    purpose: str
    call_when: str
    params: Sequence[Param] = field(default_factory=tuple)
    returns: str = "A table: {columns, rows, scope}."
    dedupe_on: Sequence[str] = field(default_factory=tuple)
    max_calls: int = 1
    cross_checks: Sequence[Callable[[dict], Rejection | None]] = field(
        default_factory=tuple
    )
    replaces: str = ""

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def description(self) -> str:
        """The full text a caller reads when choosing this tool.

        Purpose, then when to call, then the result shape. Parameters are
        documented per-parameter by the SDK, so they are not repeated here
        — duplicating them is how the two copies start disagreeing.
        """
        return "\n".join(
            [
                self.purpose.strip(),
                "",
                f"When to call: {self.call_when.strip()}",
                f"Returns: {self.returns.strip()}",
            ]
        )

    def validate(self, arguments: dict) -> dict | Rejection:
        """Validate and normalise a call's arguments.

        Returns the cleaned argument dict, or the first :class:`Rejection`.
        First, not all of them: a caller repairing one problem at a time
        makes progress, while a list of five failures usually produces a
        rewrite that introduces a sixth.
        """
        cleaned: dict[str, Any] = {}
        for spec_param in self.params:
            raw = arguments.get(spec_param.name, spec_param.default)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                if spec_param.required:
                    return Rejection(
                        spec_param.name,
                        "value is missing",
                        spec_param.validator.accepted
                        if spec_param.validator
                        else "a value",
                    )
                cleaned[spec_param.name] = spec_param.default
                continue
            if spec_param.validator is None:
                cleaned[spec_param.name] = raw
                continue
            result = spec_param.validator(raw, spec_param.name)
            if isinstance(result, Rejection):
                return result
            cleaned[spec_param.name] = result

        # Unknown arguments pass through untouched rather than being refused:
        # an SDK may inject its own, and refusing them would strand the call.
        for key, value in arguments.items():
            cleaned.setdefault(key, value)

        for check in self.cross_checks:
            rejection = check(cleaned)
            if rejection is not None:
                return rejection
        return cleaned

    def dedupe_key(self, arguments: dict) -> tuple:
        """The tuple identifying a repeat call, per ``dedupe_on``."""
        return tuple(
            str(arguments.get(name, "")).strip().lower() for name in self.dedupe_on
        )

    def scope_of(self, arguments: dict) -> dict:
        """The scope block echoing the call's identifying arguments."""
        return {name: arguments.get(name) for name in self.dedupe_on}


__all__ = ["Param", "ToolSpec"]
