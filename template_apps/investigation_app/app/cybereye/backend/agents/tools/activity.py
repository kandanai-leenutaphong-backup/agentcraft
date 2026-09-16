"""Target-specific categorical activity profiles over the bound telemetry table."""

from __future__ import annotations

from typing import Any

from .base import bind, ToolContext, WINDOW_PROPERTIES, agent_tool, object_schema, parse_window, query_envelope


def _properties(entity: str) -> dict[str, Any]:
    return {
        entity: {"type": "string", "minLength": 1, "description": f"Exact observed {entity} value."},
        **WINDOW_PROPERTIES,
        "max_rows": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Bounded result row cap."},
    }


def _params(start: str, end: str, **values: Any) -> dict[str, Any]:
    lower, upper = parse_window(start, end)
    return {"start": lower, "end": upper, **values}


@agent_tool(
    name="profile_host_activity", category="host_activity", datasource="adx",
    description="""Return a bounded categorical product/event-type profile for one observed host. Prefer this for host activity composition before considering raw KQL.""",
    parameters=object_schema(_properties("host"), ["host", "start", "end", "max_rows"]),
)
async def profile_host_activity(context: ToolContext, *, host: str, start: str, end: str,
                          max_rows: int) -> dict[str, Any]:
    query = bind("""{TABLE}
| where source_time between (start .. end)
| where tolower(target_host_name) == tolower(host)
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time)
    by product, event_type=event_type_recovered
| order by event_count desc, product asc, event_type asc""")
    result = await context.adx.parameterized(query, _params(start, end, host=host), max_rows)
    return query_envelope("profile_host_activity", "host_activity", result,
                          {"host": host, "start": start, "end": end})


@agent_tool(
    name="get_authentication_activity", category="authentication", datasource="adx",
    description="""Return bounded categorical Windows authentication activity for one host. Prefer this for logon success/failure, account, and source questions; it covers event ids 4624, 4625, and 4648.""",
    parameters=object_schema(_properties("host"), ["host", "start", "end", "max_rows"]),
)
async def get_authentication_activity(context: ToolContext, *, host: str, start: str, end: str,
                                max_rows: int) -> dict[str, Any]:
    query = bind("""{TABLE}
| where source_time between (start .. end)
| where tolower(target_host_name) == tolower(host) and win_event_id in ("4624", "4625", "4648")
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time)
    by event_id=win_event_id, account=target_user_name, source=source_address
| order by event_count desc, account asc, source asc""")
    result = await context.adx.parameterized(query, _params(start, end, host=host), max_rows)
    return query_envelope("get_authentication_activity", "authentication", result,
                          {"host": host, "start": start, "end": end})


@agent_tool(
    name="get_privileged_session_activity", category="privileged_session", datasource="adx",
    description="""Return bounded categorical CyberArk privileged-session records for one host. Prefer this for session, privileged access, and window-title evidence; text is truncated by the ADX boundary.""",
    parameters=object_schema(_properties("host"), ["host", "start", "end", "max_rows"]),
)
async def get_privileged_session_activity(context: ToolContext, *, host: str, start: str, end: str,
                                    max_rows: int) -> dict[str, Any]:
    query = bind(r'''{TABLE}
| where source_time between (start .. end)
| where product == "CYBERARK"
| extend session_host=tolower(extract(@"dhost=([^\s]+)", 1, original_data)),
         session_user=extract(@"duser=([^\s]+)", 1, original_data)
| where session_host == tolower(host)
| project source_time, resource_id, session_host, session_user, event_type_recovered,
    application_name, service_name
| order by source_time asc, resource_id asc''')
    result = await context.adx.parameterized(query, _params(start, end, host=host), max_rows)
    return query_envelope("get_privileged_session_activity", "privileged_session", result,
                          {"host": host, "start": start, "end": end})


@agent_tool(
    name="get_dns_activity", category="dns", datasource="adx",
    description="""Return bounded categorical DNS activity for one observed source address. Prefer this for domain, cadence, and DNS-volume questions before considering raw KQL.""",
    parameters=object_schema(_properties("source_address"), ["source_address", "start", "end", "max_rows"]),
)
async def get_dns_activity(context: ToolContext, *, source_address: str, start: str, end: str,
                     max_rows: int) -> dict[str, Any]:
    query = bind("""{TABLE}
| where source_time between (start .. end)
| where source_address == source_address_param and isnotempty(query_name)
| summarize request_count=count(), first_seen=min(source_time), last_seen=max(source_time)
    by query_name, event_type=event_type_recovered
| order by request_count desc, query_name asc""")
    result = await context.adx.parameterized(
        query, _params(start, end, source_address_param=source_address), max_rows,
    )
    return query_envelope("get_dns_activity", "dns", result,
                          {"source_address": source_address, "start": start, "end": end})
