"""The synthetic fixture preserves the loaded MITRE index's document contract."""

import hashlib

from app.cybereye.backend.knowledge.keys import safe_key

from fake_search import FROZEN_KNOWLEDGE_HITS, FakeSearchIndexClient
from knowledge_documents import build_document


def test_frozen_kind_qualified_keys():
    assert safe_key("analytic:T1001") == "analytic_T1001-0bc78cde"
    assert safe_key("situation_type:T1001") == "situation_type_T1001-adaac2e0"
    for value in ("analytic:A/B?x=1", "analytic:" + "z" * 140,
                  "analytic:T\u00e9st/\u6771", "analytic:A_B", "analytic:A/B"):
        actual = safe_key(value)
        assert len(actual) <= 109
        assert actual[-8:] == hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    assert safe_key("analytic:A_B") != safe_key("analytic:A/B")


def test_frozen_hits_preserve_ties_null_absence_and_provenance():
    client = FakeSearchIndexClient(list(FROZEN_KNOWLEDGE_HITS))
    hits = client.search("mitre-attack-test", "discovery", top=2,
                         filter="doc_kind eq 'analytic'", select=("id", "title"))
    assert [hit["doc_id"] for hit in hits] == ["Z2", "A1"]
    assert [hit["@search.score"] for hit in hits] == [1.0, 1.0]
    assert hits[0]["title"] is None
    assert "title" not in hits[1]
    assert hits[0]["platforms"] == ["Windows", "Linux"]
    assert hits[0]["path"] == "analytics/z.yaml"
    assert hits[1]["commit"] == "fixture-commit"
    assert client.calls[0]["select"] == ("id", "title")


def test_projection_preserves_kind_bounds_and_provenance():
    record = {"type_id": "T1001", "label": "  Test technique  ", "definition": "x" * 9000,
              "source": "attack", "technique_ids": ["t1001"], "behaviour_class": ["ACCESS"],
              "path": "fixture.json", "commit": "fixture-commit", "license": "CC-BY-4.0",
              "source_fields": {"attack_url": "https://attack.mitre.org/techniques/T1001/"}}
    document = build_document(record)
    assert document["id"] == "situation_type_T1001-adaac2e0"
    assert document["title"] == "Test technique"
    assert document["technique_ids"] == ["T1001"]
    assert document["behaviour_class"] == ["access"]
    assert len(document["content"]) == len(document["definition"]) == 8000
    assert document["commit"] == "fixture-commit"
    assert document["license"] == "CC-BY-4.0"
    assert document["attack_url"] == record["source_fields"]["attack_url"]