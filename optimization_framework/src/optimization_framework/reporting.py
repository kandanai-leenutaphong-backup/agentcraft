"""Portable exports preserve failed/incomplete evidence and escape untrusted text."""

import csv
import html
import io
import json

from .contracts import Refusal


def _cell(value: object) -> str:
    result = str(value)
    if result.lstrip().startswith(("=", "+", "-", "@")) or result.startswith(("\t", "\r", "\n")):
        return "'" + result
    return result


def render(run: dict, format: str = "json") -> tuple[bytes, str]:
    serialized = json.dumps(run, indent=2, ensure_ascii=True, allow_nan=False)
    if format == "json":
        return (serialized + "\n").encode(), "application/json; charset=utf-8"
    if format == "html":
        title = html.escape(run["task_name"])
        content = ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
                   "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                   f"<title>{title}</title><h1>{title}</h1>"
                   f"<p>{html.escape(run['evidence_class'])}: {html.escape(run['decision'])}</p>"
                   f"<pre>{html.escape(serialized)}</pre></html>")
        return content.encode(), "text/html; charset=utf-8"
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["record_type", "id", "name", "status", "detail", "record_json"])
        sections = {"run": [run], "metric": [{"name": name, "value": value}
                                               for name, value in run["metrics"].items()],
                    "candidate": run["candidates"], "event": run["events"],
                    "feedback": run["feedback"], "restoration": run["restorations"]}
        for kind, records in sections.items():
            for record in records:
                values = [kind, record.get("id", ""), record.get("name", ""), record.get("status", ""),
                          record.get("text", record.get("detail", "")),
                          json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False)]
                writer.writerow([_cell(value) for value in values])
        return stream.getvalue().encode(), "text/csv; charset=utf-8"
    raise Refusal("unsupported_report_format")