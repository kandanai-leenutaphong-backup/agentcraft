"""toolshape — purpose-built tools, and the meter that tells you which earn
their place.

WHY THIS EXISTS
---------------
Give a model a raw query interface and it will author queries. Some are
malformed, and the malformed ones cost a turn each and teach it nothing.
Give it a narrow tool for the thing it actually needs and the malformed
call becomes unrepresentable: there is no syntax to get wrong.

Measured on a live agent here: a raw graph-query tool ran at a **44% hard
error rate** — the model writing invalid traversals. Deleting it made
outcomes *worse*, because it was doing real work some of the time.
Replacing it with three shaped tools over the same backend cut error noise
**75%** and recovered the outcomes. Shape, do not delete; and measure,
because the first instinct was wrong.

That is the loop this box packages:

    shape a tool -> record every call -> measure weight -> ablate to confirm
        -> keep or revert -> repeat

TWO HALVES, ONE CONTRACT
------------------------
**Shaping.** ``ToolSpec`` + ``@purpose_built`` turn a function into a tool
with validated inputs, refusals that teach, per-turn duplicate suppression
and one tabular result shape. The description the model reads is generated
out of the spec, so it cannot drift from what the code enforces.

**Measuring.** Every call emits a ``CallRecord``. ``aggregate`` turns those
into per-tool error, refusal, duplicate and unproductive rates plus
outcome association, and flags review candidates. The classification used
by the meter is the same function that builds the envelope — the shape and
its measurement cannot disagree.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
The injection seam is the ``ToolSpec``: every string, vocabulary, column
and gate name is caller-supplied. Nothing here knows what a row means, and
call records carry no argument values.

PUBLIC SURFACE
--------------
``ToolSpec`` / ``Param`` / ``purpose_built``  — declare and wrap a tool.
``identifier`` / ``one_of`` / ``timestamp`` / ``bounded_list`` / ... — validators.
``table`` / ``refusal`` / ``failure`` / ``duplicate`` / ``classify`` — result shapes.
``turn`` / ``MemorySink`` / ``JsonlSink`` / ``set_sink`` — recording.
``aggregate`` / ``Outcome`` / ``render_markdown`` — the weight meter.
``lint`` / ``catalogue`` / ``specs_in`` — surface review.

DEPENDENCIES
------------
Standard library only. No agent SDK, no web framework, no HTTP client.

READ NEXT
---------
``SKILL.md`` to use it, ``CONTRACT.md`` for the record schema and the
ablation protocol, ``GOTCHAS.md`` when a number looks wrong, ``README.md``
for why the surface is shaped this way.
"""

from __future__ import annotations

from ._catalogue import DEFAULT_MAX_TOOLS, Finding, catalogue, json_schema, lint
from ._decorator import purpose_built, specs_in, tool_names
from ._envelope import (
    DUPLICATE,
    EMPTY,
    ERROR,
    MISSING,
    PRODUCTIVE,
    REFUSED,
    RESULT_CLASSES,
    UNPRODUCTIVE_CLASSES,
    classify,
    duplicate,
    failure,
    is_unproductive,
    refusal,
    sanitize_detail,
    table,
)
from ._ledger import (
    CallRecord,
    JsonlSink,
    MemorySink,
    NullSink,
    begin_turn,
    emit,
    end_turn,
    get_sink,
    read_records,
    record_call_once,
    set_sink,
    turn,
)
from ._spec import Param, ToolSpec
from ._stats import (
    HIGH_DUPLICATE,
    HIGH_ERROR,
    HIGH_REFUSAL,
    HIGH_UNPRODUCTIVE,
    LOW_USAGE_PCT,
    MIN_ASSOC_N,
    Outcome,
    Report,
    SIGNAL_NOISY_ASSOCIATED,
    SIGNAL_OK,
    SIGNAL_REVIEW,
    SIGNAL_STRONG,
    ToolStat,
    aggregate,
    load_outcomes,
    render_markdown,
)
from ._validators import (
    Rejection,
    Validator,
    bounded_list,
    escape_quotes,
    identifier,
    integer_range,
    label,
    one_of,
    time_window,
    timestamp,
    uuid,
)

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_MAX_TOOLS",
    "DUPLICATE",
    "EMPTY",
    "ERROR",
    "HIGH_DUPLICATE",
    "HIGH_ERROR",
    "HIGH_REFUSAL",
    "HIGH_UNPRODUCTIVE",
    "LOW_USAGE_PCT",
    "MIN_ASSOC_N",
    "MISSING",
    "PRODUCTIVE",
    "REFUSED",
    "RESULT_CLASSES",
    "SIGNAL_NOISY_ASSOCIATED",
    "SIGNAL_OK",
    "SIGNAL_REVIEW",
    "SIGNAL_STRONG",
    "UNPRODUCTIVE_CLASSES",
    "CallRecord",
    "Finding",
    "JsonlSink",
    "MemorySink",
    "NullSink",
    "Outcome",
    "Param",
    "Rejection",
    "Report",
    "ToolSpec",
    "ToolStat",
    "Validator",
    "aggregate",
    "begin_turn",
    "bounded_list",
    "catalogue",
    "classify",
    "duplicate",
    "emit",
    "end_turn",
    "escape_quotes",
    "failure",
    "get_sink",
    "identifier",
    "integer_range",
    "is_unproductive",
    "json_schema",
    "label",
    "lint",
    "load_outcomes",
    "one_of",
    "purpose_built",
    "read_records",
    "record_call_once",
    "refusal",
    "render_markdown",
    "sanitize_detail",
    "set_sink",
    "specs_in",
    "table",
    "time_window",
    "timestamp",
    "tool_names",
    "turn",
    "uuid",
]
