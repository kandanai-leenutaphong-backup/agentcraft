"""Fabric Eventhouse / Azure Data Explorer — telemetry without authored KQL.

WHAT THE SHAPE BUYS
-------------------
KQL is the most tempting surface to hand over raw, because it is readable
and the model can nearly write it. "Nearly" is the problem: the failures
are not syntax errors so much as *silently wrong* queries — a `has` that
matches nothing because it is token-based rather than substring, a window
with no bound, a filter on a column that does not exist.

Shaped tools remove the whole class. The time window is validated as a
pair, the row cap is injected rather than requested, and the operator is
chosen from an enumeration instead of typed.

RESULT SHAPES AND THEIR CARDS
-----------------------------
`find_events`     -> {columns, rows, scope} -> `tabular` archetype
`summarise_metric`-> {metrics: [...]}       -> `metrics` archetype

Run it::

    python3 examples/azure/telemetry_kql.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backends import FakeKusto  # noqa: E402

from toolshape import (  # noqa: E402
    Param,
    ToolSpec,
    identifier,
    integer_range,
    one_of,
    purpose_built,
    time_window,
    timestamp,
)

ARCHETYPES = {"find_events": "tabular", "summarise_metric": "metrics"}

BACKEND = FakeKusto()            # real: KqlConnector(...).execute
DATABASE = "telemetry"
TABLE = "Events"
EVENT_KINDS = ("trip", "alarm", "notice")
AGGREGATIONS = ("count", "avg", "min", "max", "sum")

# Row cap injected into every query. Not a parameter: a caller asking for
# more rows than its context can hold is a request nobody benefits from.
MAX_ROWS = 500


FIND_EVENTS = ToolSpec(
    name="find_events",
    purpose="Return event records for one site inside a time window.",
    call_when=(
        "Whenever you need raw event records. Call this instead of writing a "
        "query. Use the site code returned by the site listing, and bound the "
        "window to the period you are investigating."
    ),
    params=[
        Param("site", "Site code, as returned by the site listing.",
              validator=identifier(max_len=32)),
        Param("start", "Window start, from the incident time.", validator=timestamp()),
        Param("end", "Window end, from the incident time.", validator=timestamp()),
        Param("kind", "Restrict to one event kind, one of the values listed.",
              validator=one_of(EVENT_KINDS), required=False),
    ],
    returns="A table with columns at, site, kind, value.",
    dedupe_on=("site", "start", "end", "kind"),
    # 48 hours is the widest window the backend answers inside its timeout.
    # Refusing here costs one turn; discovering it downstream costs the query.
    cross_checks=(time_window(max_hours=48),),
    replaces="query_kql",
)


@purpose_built(FIND_EVENTS)
def find_events(site: str, start: str, end: str, kind: str | None = None):
    clauses = [
        f"| where site == '{site}'",
        f"| where at between (datetime('{start}') .. datetime('{end}'))",
    ]
    if kind:
        clauses.append(f"| where kind == '{kind}'")
    query = "\n".join([TABLE, *clauses, f"| take {MAX_ROWS}"])
    shaped = BACKEND.execute(DATABASE, query)
    columns = [column["name"] for column in shaped["columns"]]
    return columns or ["at", "site", "kind", "value"], shaped["rows"]


SUMMARISE_METRIC = ToolSpec(
    name="summarise_metric",
    purpose="Return one aggregate over a numeric column, for a site and window.",
    call_when=(
        "When you need a number rather than records — how many, how high, how "
        "often. Prefer this over find_events when you are not going to read "
        "the individual rows."
    ),
    params=[
        Param("site", "Site code, as returned by the site listing.",
              validator=identifier(max_len=32)),
        Param("start", "Window start, from the incident time.", validator=timestamp()),
        Param("end", "Window end, from the incident time.", validator=timestamp()),
        Param("aggregation", "How to summarise, one of the values listed.",
              validator=one_of(AGGREGATIONS)),
        Param("bucket_hours", "Optional bucket size for a per-period breakdown.",
              validator=integer_range(1, 24), required=False),
    ],
    returns="{metrics: [{label, value, unit}]}",
    dedupe_on=("site", "start", "end", "aggregation", "bucket_hours"),
    cross_checks=(time_window(max_hours=48),),
    replaces="query_kql",
)


@purpose_built(SUMMARISE_METRIC)
def summarise_metric(
    site: str, start: str, end: str, aggregation: str, bucket_hours: int | None = None
):
    """Returns a metrics dict — a number deserves a number's card, not a table."""
    query = (
        f"{TABLE}\n| where site == '{site}'\n"
        f"| where at between (datetime('{start}') .. datetime('{end}'))\n"
        f"| summarize {aggregation}(value)"
    )
    shaped = BACKEND.execute(DATABASE, query)
    rows = shaped["rows"]
    values = [row["value"] for row in rows if isinstance(row.get("value"), (int, float))]

    if not values:
        return {"metrics": [], "scope": {"site": site, "start": start, "end": end}}

    computed = {
        "count": len(values),
        "avg": round(sum(values) / len(values), 3),
        "min": min(values),
        "max": max(values),
        "sum": round(sum(values), 3),
    }[aggregation]
    metrics = [
        {"label": aggregation, "value": computed},
        {"label": "records", "value": len(values)},
    ]
    if bucket_hours:
        metrics.append({"label": "bucket", "value": bucket_hours, "unit": "h"})
    return {"metrics": metrics, "scope": {"site": site, "start": start, "end": end}}


WINDOW = ("2026-04-15T09:00:00", "2026-04-15T11:00:00")


def demo() -> list[str]:
    return [
        find_events(site="SITE_A", start=WINDOW[0], end=WINDOW[1]),
        find_events(site="SITE_A", start=WINDOW[0], end=WINDOW[1], kind="trip"),
        find_events(site="SITE_A", start=WINDOW[1], end=WINDOW[0]),        # refused
        find_events(site="SITE_NONE", start=WINDOW[0], end=WINDOW[1]),     # empty
        summarise_metric(site="SITE_A", start=WINDOW[0], end=WINDOW[1], aggregation="avg"),
        summarise_metric(site="SITE_A", start=WINDOW[0], end=WINDOW[1], aggregation="median"),
    ]


if __name__ == "__main__":
    for payload in demo():
        print(json.dumps(json.loads(payload), indent=2)[:400])
        print("-" * 60)
