"""Guardrail and envelope edge cases.

The selftest covers the main paths; these are the cases that were argued
about, got wrong once, or would be quietly dropped by a rewrite.

Run: ``python3 -m pytest tests/ -q``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata import (
    AzureDataConfig,
    ensure_limit,
    error_envelope,
    sanitize_detail,
    validate_read_only,
)
from azdata.core.guardrails import DEFAULT_MAX_QUERY_LENGTH, DEFAULT_MAX_ROWS, LANGUAGES


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_has_both_caps(language):
    assert language in DEFAULT_MAX_ROWS
    assert language in DEFAULT_MAX_QUERY_LENGTH


@pytest.mark.parametrize(
    "query",
    [
        "g.V().addV('x')",
        "g.V().addE('y')",
        "g.V().drop()",
        "g.V().property('k', 'v')",
        "g.addVertex('x')",
        "g.addEdge('y')",
    ],
)
def test_gremlin_writes_blocked(query):
    assert validate_read_only(query, "gremlin") is not None


@pytest.mark.parametrize(
    "query",
    [
        "g.V().hasLabel('device').values('name')",
        "g.V().out('connects').valueMap()",
        "g.E().count()",
    ],
)
def test_gremlin_reads_allowed(query):
    assert validate_read_only(query, "gremlin") is None


def test_kql_command_after_semicolon_is_checked():
    # A single-statement check would pass this; the split is what catches it.
    assert validate_read_only("T | take 1; .drop table T", "kql") is not None


@pytest.mark.parametrize("command", [".show tables", ".show database schema", ".show table T"])
def test_kql_readonly_commands_allowed(command):
    assert validate_read_only(command, "kql") is None


def test_kql_length_cap_is_generous():
    # Machine-generated scoring queries legitimately run to tens of
    # thousands of characters; the read-only check is the real guard.
    assert validate_read_only("T | where x == 1 " * 2000, "kql") is None


def test_cypher_string_literal_does_not_trip_the_guard():
    query = "MATCH (n) WHERE n.status = 'CREATED_BY_ADMIN' RETURN n"
    assert validate_read_only(query, "cypher") is None


def test_cypher_write_outside_a_literal_is_caught():
    assert validate_read_only("MATCH (n) DELETE n", "cypher") is not None


@pytest.mark.parametrize(
    "query,language,expected",
    [
        ("g.V()", "gremlin", "g.V().limit(3)"),
        ("g.V();", "gremlin", "g.V().limit(3)"),
        ("Events", "kql", "Events | take 3"),
        ("MATCH (n) RETURN n", "cypher", "MATCH (n) RETURN n LIMIT 3"),
        ("select * from c", "sql", "select TOP 3 * from c"),
    ],
)
def test_limit_injection(query, language, expected):
    assert ensure_limit(query, language, 3) == expected


@pytest.mark.parametrize(
    "query,language",
    [
        ("g.V().limit(9)", "gremlin"),
        ("g.V().range(0, 9)", "gremlin"),
        ("g.V().sample(9)", "gremlin"),
        ("g.V().count()", "gremlin"),
        ("Events | take 9", "kql"),
        ("Events | top 9 by t", "kql"),
        ("MATCH (n) RETURN n LIMIT 9", "cypher"),
        ("SELECT TOP 9 * FROM c", "sql"),
        ("SELECT * FROM c OFFSET 0 LIMIT 9", "sql"),
    ],
)
def test_existing_limits_are_left_alone(query, language):
    assert ensure_limit(query, language, 3) == query


def test_unknown_language_passes_through_both_functions():
    assert validate_read_only("SELECT ?s WHERE { ?s ?p ?o }", "sparql") is None
    assert ensure_limit("SELECT ?s WHERE { ?s ?p ?o }", "sparql") == (
        "SELECT ?s WHERE { ?s ?p ?o }"
    )


def test_detail_sanitisation_removes_urls_but_keeps_identifiers():
    detail = sanitize_detail(
        "failed for id ABC-123 at https://acct.documents.azure.com:443/dbs/x"
    )
    assert "ABC-123" in detail
    assert "azure.com" not in detail


def test_detail_sanitisation_coerces_non_strings():
    assert sanitize_detail(ValueError("boom")) == "boom"  # type: ignore[arg-type]


def test_envelope_is_valid_json_for_a_hostile_detail():
    payload = json.loads(error_envelope('quote " backslash \\ newline \n'))
    assert payload["error"] is True


def test_partial_service_principal_is_ignored():
    assert AzureDataConfig(tenant_id="t", client_secret="s").service_principal is None


def test_config_is_frozen():
    config = AzureDataConfig()
    with pytest.raises(Exception):
        config.max_rows = 10  # type: ignore[misc]


def test_with_overrides_returns_a_copy():
    base = AzureDataConfig(max_rows=10)
    derived = base.with_overrides(max_rows=20)
    assert (base.max_rows, derived.max_rows) == (10, 20)
