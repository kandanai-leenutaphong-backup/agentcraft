"""Per-event-family extraction of ontology nodes and edges from the unified export.

Every extractor reads only fields the archived profiling note
``note-20260831T073018Z-fca574fa`` established as populated for
that family. Nothing infers a subtype from a name shape: account and asset classes come
from a direct source flag or stay a labelled candidate.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .canonical import (
    account_key, account_realm, address_key, address_scope, clean, dns_key, host_parts,
    is_reverse_lookup, is_sid, looks_like_machine_account, parse_identity_blob,
    registrable_suffix, short_host, slug,
)
from .model import Graph

#: Session ids the export uses as a null placeholder rather than a real session handle.
PLACEHOLDER_SESSIONS = frozenset({"0x0", "0x3e7", "0x3e4", "0x3e5"})

WIN_EVENT_MEANING = {
    "4624": "successful logon",
    "4648": "logon with explicit credentials",
    "4768": "Kerberos TGT requested",
    "4769": "Kerberos service ticket requested",
    "4776": "credential validation",
}

#: Tool names the privileged-session payload is checked for, matching the scanner rule.
SOFTWARE_MARKERS = ("winPEAS", "peass-ng", "mimikatz", "BloodHound", "SharpHound", "PsExec")


def _vault_records(value: str | None) -> dict[str, str]:
    """Flatten CyberArk's ``{"record":[{"key":..,"value":..}]}`` payload into a mapping."""
    text = clean(value)
    if not text.startswith("{"):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    records = parsed.get("record") if isinstance(parsed, dict) else None
    if not isinstance(records, list):
        return {}
    return {clean(str(item.get("key", ""))): clean(str(item.get("value", "")))
            for item in records if isinstance(item, dict)}


def _host(graph: Graph, raw: str, when: str, *, source: str) -> str:
    """Upsert a Host from any observed hostname spelling; returns its node id or ''."""
    key, domain = host_parts(raw)
    if not key:
        return ""
    node_id = slug("host", key)
    node = graph.node("Host", node_id, key, resolution="heuristic_shortname_projection")
    observed = clean(raw)
    if observed.startswith("{"):
        parsed = parse_identity_blob(observed)
        observed = parsed.get("original_name", "") or parsed.get("name", "")
    node.observe("observed_names", observed)
    node.observe("name_sources", source)
    if "." in observed:
        node.observe("fqdns", observed)
    if domain:
        node.observe("domains", domain)
    node.touch(when)
    return node_id


def _identity(graph: Graph, name: str, domain: str, when: str, *, machine_flag: str = "") -> str:
    key = account_key(name, domain)
    if not key:
        return ""
    node_id = slug("identity", key)
    node = graph.node("Identity", node_id, clean(name).split("@")[0] or key)
    realm = account_realm(name, domain)
    node.observe("observed_names", clean(name))
    node.observe("domains", realm)
    # Only a direct source flag establishes a machine account; the suffix stays a candidate.
    if machine_flag.upper() == "TRUE":
        node.props["account_class"] = "machine_account"
        node.props["account_class_basis"] = "source is_machine_account flag"
    elif node.props.get("account_class") != "machine_account":
        if looks_like_machine_account(name):
            node.props["account_class"] = "machine_account_candidate"
            node.props["account_class_basis"] = "dollar-suffixed name only"
        else:
            node.props.setdefault("account_class", "account_observed")
            node.props.setdefault("account_class_basis", "no authoritative class in the export")
    node.touch(when)
    return node_id


def _address(graph: Graph, raw: str, when: str, *, role: str) -> str:
    key = address_key(raw)
    if not key:
        return ""
    node_id = slug("ip", key)
    node = graph.node("IpAddress", node_id, key, scope=address_scope(key))
    node.observe("roles", role)
    node.touch(when)
    return node_id


def _dns(graph: Graph, raw: str, when: str) -> str:
    key = dns_key(raw)
    if not key or address_key(key):
        return ""
    node_id = slug("dns", key)
    node = graph.node(
        "DnsName", node_id, key,
        registrable=registrable_suffix(key),
        lookup_kind="reverse" if is_reverse_lookup(key) else "forward",
        qualified="." in key,
    )
    node.touch(when)
    return node_id


def _sensor(graph: Graph, row: dict[str, str], when: str) -> str:
    key = clean(row.get("sensor_id"))
    if not key:
        return ""
    node_id = slug("sensor", key.casefold())
    node = graph.node("Sensor", node_id, key, sensor_type=clean(row.get("sensor_type")))
    node.observe("products", clean(row.get("product")))
    node.touch(when)
    return node_id


def extract_auth(graph: Graph, row: dict[str, str], when: str) -> None:
    """Windows and ETW authentication: 4624/4648/4768/4769/4776."""
    event_id = clean(row.get("win_event_id"))
    target_blob = parse_identity_blob(row.get("target_user"))
    account = clean(row.get("target_user_name")) or target_blob.get("name", "")
    domain = clean(row.get("target_domain_name")) or target_blob.get("domain", "")
    identity = _identity(graph, account, domain, when, machine_flag=clean(row.get("is_machine_account")))
    host = _host(graph, row.get("target_host") or row.get("target_host_name") or row.get("hostname"),
                 when, source="auth target")

    if identity and host:
        edge = graph.edge("AUTHENTICATED_TO", identity, host)
        edge.observe("win_event_ids", event_id)
        edge.observe("logon_types", clean(row.get("logon_type")))
        edge.observe("auth_protocols", clean(row.get("auth_protocol")))
        edge.observe("results", clean(row.get("action_result")))
        if event_id in WIN_EVENT_MEANING:
            edge.observe("meanings", WIN_EVENT_MEANING[event_id])
        edge.touch(when)

    source_ip = _address(graph, row.get("source_address"), when, role="authentication source")
    if identity and source_ip:
        edge = graph.edge("SIGNED_IN_FROM", identity, source_ip)
        edge.observe("win_event_ids", event_id)
        edge.touch(when)
    if host and source_ip:
        graph.edge("HAS_ADDRESS", host, source_ip, basis="co-observed on an authentication event").touch(when)

    service = clean(row.get("service_name"))
    if service and identity:
        sid = clean(row.get("service_sid"))
        node_id = slug("krb", service.casefold())
        node = graph.node("KerberosService", node_id, service, sid=sid if is_sid(sid) else "")
        node.observe("win_event_ids", event_id)
        node.touch(when)
        edge = graph.edge("REQUESTED_SERVICE", identity, node_id)
        edge.observe("win_event_ids", event_id)
        edge.touch(when)

    _session(graph, row, when, identity, host, session_type="windows_logon")


def _session(graph: Graph, row: dict[str, str], when: str, identity: str, host: str,
             *, session_type: str) -> str:
    raw = clean(row.get("session_id"))
    if not raw or raw.casefold() in PLACEHOLDER_SESSIONS or is_sid(raw):
        if raw:
            graph.drop("session_id placeholder or SID")
        return ""
    product = clean(row.get("product"))
    node_id = slug("session", session_type, product.casefold(), raw.casefold())
    node = graph.node("Session", node_id, raw, session_type=session_type, product=product)
    node.touch(when)
    if identity:
        graph.edge("OPENED_SESSION", identity, node_id).touch(when)
    if host:
        graph.edge("SESSION_ON_HOST", node_id, host).touch(when)
    return node_id


def extract_dns(graph: Graph, row: dict[str, str], when: str) -> None:
    name = _dns(graph, row.get("query_name"), when)
    if not name:
        graph.drop("dns row without a usable query_name")
        return
    node = graph.nodes[name]
    node.observe("query_types", clean(row.get("query_type")))
    node.observe("response_codes", clean(row.get("response_code")))

    client = _address(graph, row.get("source_address"), when, role="dns client")
    resolver = _address(graph, row.get("destination_address"), when, role="dns resolver")
    host = _host(graph, row.get("hostname"), when, source="dns client host")

    if client:
        graph.edge("QUERIED", client, name).touch(when)
    if host:
        graph.edge("QUERIED", host, name).touch(when)
        if client:
            graph.edge("HAS_ADDRESS", host, client, basis="co-observed on a DNS query").touch(when)
    if resolver:
        graph.edge("RESOLVED_BY", name, resolver).touch(when)


def extract_netflow(graph: Graph, row: dict[str, str], when: str) -> None:
    source = _address(graph, row.get("source_address"), when, role="flow source")
    destination = _address(graph, row.get("destination_address"), when, role="flow destination")
    if not source or not destination:
        graph.drop("netflow row without both endpoints")
        return
    edge = graph.edge("CONNECTED_TO", source, destination)
    edge.observe("destination_ports", clean(row.get("destination_port")))
    edge.observe("protocols", clean(row.get("protocol")))
    edge.observe("actions", clean(row.get("flow_action")))
    edge.observe("directions", clean(row.get("direction")))
    edge.touch(when)

    application = clean(row.get("application_name"))
    if application:
        node_id = slug("app", application.casefold())
        node = graph.node("Application", node_id, application)
        node.touch(when)
        used = graph.edge("USED_APPLICATION", source, node_id)
        used.observe("actions", clean(row.get("flow_action")))
        used.touch(when)


def extract_privileged(graph: Graph, row: dict[str, str], when: str) -> None:
    """CyberArk PSM: an operator identity driving a session against a target host."""
    blob = parse_identity_blob(row.get("user"))
    identity = _identity(graph, blob.get("name", "") or clean(row.get("user_name")),
                         blob.get("domain", ""), when)
    host = _host(graph, row.get("target_hostname") or row.get("target_host"), when,
                 source="privileged session target")
    source_ip = _address(graph, row.get("source_address"), when, role="privileged session source")
    records = _vault_records(row.get("additional_event_data"))

    # The vault hands the operator a second, privileged account for the target device.
    privileged = _identity(graph, records.get("duser", ""), "", when)
    if identity and privileged and privileged != identity:
        edge = graph.edge("USED_ACCOUNT", identity, privileged,
                          basis="CyberArk privileged-session record names both accounts")
        edge.observe("safes", records.get("Safe Name", ""))
        edge.touch(when)
    if privileged and host:
        edge = graph.edge("AUTHENTICATED_TO", privileged, host)
        edge.observe("meanings", "privileged session")
        edge.touch(when)

    safe = records.get("Safe Name", "")
    if safe:
        node_id = slug("safe", safe.casefold())
        node = graph.node("VaultSafe", node_id, safe, device_type=records.get("Device Type", ""))
        node.observe("objects", records.get("fname", ""))
        node.touch(when)
        for holder in (identity, privileged):
            if holder:
                graph.edge("RETRIEVED_FROM_SAFE", holder, node_id).touch(when)

    payload = row.get("original_data") or ""
    for marker in SOFTWARE_MARKERS:
        if marker.casefold() in payload.casefold():
            node_id = slug("software", marker.casefold())
            node = graph.node("SoftwareReference", node_id, marker,
                              basis="string observed in a privileged-session record",
                              established="reference only: no process execution evidence")
            node.touch(when)
            for holder in (privileged, identity):
                if holder:
                    graph.edge("REFERENCED_SOFTWARE", holder, node_id).touch(when)
                    break
            if host:
                graph.edge("REFERENCED_SOFTWARE", host, node_id).touch(when)

    session_id = _session(graph, row, when, identity, host, session_type="privileged")
    if session_id:
        graph.nodes[session_id].observe("event_names", clean(row.get("event_name")))
    elif identity and host:
        edge = graph.edge("AUTHENTICATED_TO", identity, host)
        edge.observe("meanings", "privileged session")
        edge.touch(when)
    if identity and source_ip:
        graph.edge("SIGNED_IN_FROM", identity, source_ip).touch(when)


def extract_alert(graph: Graph, row: dict[str, str], when: str) -> None:
    title = clean(row.get("title")) or clean(row.get("event_name")) or "security alert"
    node_id = slug("alert", clean(row.get("resource_id")).casefold())
    node = graph.node(
        "SecurityAlert", node_id, title,
        severity=clean(row.get("severity")),
        provider=clean(row.get("provider")),
        status=clean(row.get("status")),
        technique_ids=clean(row.get("technique_ids")),
    )
    node.touch(when)
    host = _host(graph, row.get("target_hostname") or row.get("target_host") or row.get("source_host"),
                 when, source="alert subject")
    if host:
        graph.edge("ALERT_ON_HOST", node_id, host).touch(when)
    blob = parse_identity_blob(row.get("target_user")) or parse_identity_blob(row.get("user"))
    identity = _identity(graph, blob.get("name", ""), blob.get("domain", ""), when)
    if identity:
        graph.edge("ALERT_NAMES_IDENTITY", node_id, identity).touch(when)


def extract_management(graph: Graph, row: dict[str, str], when: str) -> None:
    host = _host(graph, row.get("client_hostname_fqdn") or row.get("client_hostname") or row.get("hostname"),
                 when, source="management event client")
    blob = parse_identity_blob(row.get("user"))
    identity = _identity(graph, blob.get("name", ""), blob.get("domain", ""), when)
    if identity and host:
        edge = graph.edge("AUTHENTICATED_TO", identity, host)
        edge.observe("meanings", "management event")
        edge.touch(when)


#: (product, event_type_recovered) is the only dispatch key; both come from the export.
FAMILY_EXTRACTORS = {
    "auth": extract_auth,
    "dnsquery": extract_dns,
    "netflow": extract_netflow,
    "managementevent": extract_management,
}


def extract_row(graph: Graph, row: dict[str, str]) -> str:
    when = clean(row.get("source_time"))
    product = clean(row.get("product"))
    family = clean(row.get("event_type_recovered"))

    sensor = _sensor(graph, row, when)
    if product == "CYBERARK":
        extract_privileged(graph, row, when)
        chosen = "privileged"
    elif product == "GRAPH_ALERTS":
        extract_alert(graph, row, when)
        chosen = "alert"
    else:
        handler = FAMILY_EXTRACTORS.get(family)
        if handler is None:
            graph.drop(f"no extractor for {product}/{family}")
            return ""
        handler(graph, row, when)
        chosen = family

    if sensor:
        host = short_host(row.get("hostname") or row.get("target_host_name"))
        if host:
            graph.edge("OBSERVED_BY", slug("host", host), sensor).touch(when)
    return chosen


def prune_singleton_sessions(graph: Graph) -> int:
    """Drop Windows logon-session handles seen on exactly one event.

    Such a vertex only ever restates the AUTHENTICATED_TO edge it sits beside, so keeping it
    adds 683 leaves to a 2,000-vertex graph without adding a navigable relationship. Privileged
    sessions and any handle reused across events are retained.
    """
    doomed = {
        node_id for node_id, node in graph.nodes.items()
        if node.label == "Session"
        and node.event_count < 2
        and node.props.get("session_type") != "privileged"
    }
    graph.remove_nodes(doomed)
    return len(doomed)


def _custodied_account(object_name: str) -> str:
    """The account label from a CyberArk object name.

    Objects are named ``Root\\<platform>-<policy>-<domain>-<account>``, so the account is
    the final delimited segment. Matching any delimited word instead would make
    ``Operating System-...`` claim custody of the SYSTEM account.
    """
    tail = re.split(r"[\\/]", object_name.strip())[-1]
    return tail.rsplit("-", 1)[-1].strip()


def derive_structural_edges(graph: Graph) -> dict[str, int]:
    """Derive the timeless layer: what each thing *is*, independent of any time window.

    None of these is a claim about an instant, so they carry no time buckets and stay on
    screen before a window is chosen. Every projection-based link records how it was made
    and what would be needed to confirm it.
    """
    hosts = {node.name.casefold(): node_id for node_id, node in graph.nodes.items()
             if node.label == "Host"}
    counts: dict[str, int] = {}

    def emit(label: str, source: str, target: str, **props: Any) -> None:
        graph.edge(label, source, target, **props)
        counts[label] = counts.get(label, 0) + 1

    for node_id, node in list(graph.nodes.items()):
        if node.label == "Identity" and str(node.props.get("account_class", "")).startswith("machine_account"):
            target = hosts.get(node.name.casefold().rstrip("$"))
            if target:
                emit("POSSIBLY_SAME_AS", node_id, target,
                     basis="machine-account label matches a host label",
                     confirmed_by="none: no directory, CMDB, or object-id evidence in this export")

        elif node.label == "KerberosService":
            target = hosts.get(node.name.casefold().rstrip("$"))
            if target:
                emit("SPN_FOR_HOST", node_id, target,
                     basis="service principal label matches a host label",
                     confirmed_by="none: no service principal registration in this export")

        elif node.label == "DnsName":
            target = hosts.get(node.name.split(".", 1)[0])
            if target and node.props.get("lookup_kind") != "reverse":
                emit("RESOLVES_TO_HOST", node_id, target,
                     basis="first DNS label matches a host label",
                     confirmed_by="none: no answer record in this export ties the name to an address")

        elif node.label == "Sensor":
            target = hosts.get(node.name.split(".", 1)[0].casefold())
            if target:
                emit("MONITORS_HOST", node_id, target,
                     basis="sensor identifier matches a host label")

        elif node.label == "VaultSafe":
            # `observed` values are sets; iterate them sorted or edge insertion order,
            # and therefore the written CSV, varies with string-hash randomisation.
            for obj in sorted(node.observed.get("objects", ())):
                wanted = _custodied_account(obj).casefold()
                for account_id, item in graph.nodes.items():
                    if item.label == "Identity" and wanted and item.name.casefold() == wanted:
                        emit("CUSTODIES_ACCOUNT", node_id, account_id,
                             basis="account is the final segment of the safe object name")

    # Domain membership, stated by the export rather than guessed from a name suffix.
    for node_id, node in list(graph.nodes.items()):
        if node.label not in ("Identity", "Host"):
            continue
        for domain in sorted(node.observed.get("domains", ())):
            name = domain.strip().upper()
            if not name or name.casefold() in hosts:
                continue
            domain_id = slug("domain", name.casefold())
            graph.node("Domain", domain_id, name, basis="observed on an event as a domain or realm")
            emit("MEMBER_OF_DOMAIN", node_id, domain_id,
                 basis="account realm or host domain named by the source record")
    return counts
