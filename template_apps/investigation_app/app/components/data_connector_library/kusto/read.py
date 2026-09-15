"""Kusto response shaping.

Adopted as a partial copy. Upstream ``azdata/kusto/read.py`` also carries
``KqlConnector`` and ``KqlTarget``, a gated query connector this repository
does not adopt: the ADX query path is ``kusto/connector.py`` beside this file,
gated for CyberEye in ``app/cybereye/backend/adx_service.py``, and a second one
would be a second place for the read-only gate to drift. Only the response
shaper the content plane calls is kept. See ``PROVENANCE.md``.

DEPENDENCIES
------------
Standard library. The response object is whatever ``azure-kusto-data``
returned; nothing is imported here.
"""

from __future__ import annotations

from typing import Any


def shape_kusto_response(response: Any) -> dict[str, list]:
    """Turn a Kusto response into ``{"columns": [...], "rows": [...]}``.

    Columns become ``{name, type}``; rows become dicts keyed by column
    name. Values exposing ``isoformat`` are converted to strings here
    rather than at serialisation time, so the result is plain JSON data
    that any consumer can hold, log or re-serialise.
    """
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
        return {"columns": [], "rows": []}

    columns = [{"name": c.column_name, "type": c.column_type} for c in primary.columns]
    rows: list[dict[str, Any]] = []
    for row in primary:
        record: dict[str, Any] = {}
        for col in primary.columns:
            value = row[col.column_name]
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            record[col.column_name] = value
        rows.append(record)
    return {"columns": columns, "rows": rows}


__all__ = ["shape_kusto_response"]
