"""A fake Azure AI Search index for the retrieval tests.

Retrieval is Azure AI Search only, so a test that exercises it either reaches the live
service or drives a double. This is the double: it holds documents in memory, applies the
subset of OData the tools actually emit (`doc_kind eq`, and `field/any(v: search.in(...))`),
and ranks by naive term overlap so ordering is deterministic without pretending to be the
service's scorer.

It exists to prove the seam's behaviour — filters, relaxation, envelopes, key fetch — not
to certify relevance. The live index is verified separately by `deploy/verify_search.py`.
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from search_read_adapter import safe_key
from app.cybereye.backend.knowledge import search as knowledge_search
from knowledge_documents import build_document

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.\-]*")
_IN = re.compile(r"(?P<field>[a-z_]+)/any\(v: search\.in\(v, (?P<values>.+?), ','\)\)")
_EQ = re.compile(r"(?P<field>[a-z_]+) eq '(?P<value>[^']*)'")

ENDPOINT = "https://fake-search.search.windows.net"
INDEX = "mitre-attack-test"

FROZEN_KNOWLEDGE_HITS = (
    {"id": "tie-z", "doc_id": "Z2", "doc_kind": "analytic", "title": None,
     "content": "discovery", "platforms": ["Windows", "Linux"],
     "path": "analytics/z.yaml", "commit": "fixture-commit", "license": "CC-BY-4.0",
     "attack_url": "https://attack.mitre.org/techniques/T1001/"},
    {"id": "tie-a", "doc_id": "A1", "doc_kind": "analytic", "content": "discovery",
     "platforms": [], "path": "analytics/a.yaml", "commit": "fixture-commit",
     "license": "CC-BY-4.0", "attack_url": None},
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


class SearchDown(OSError):
    """What a client raises when the network is not there."""


class FakeSearchIndexClient:
    """In-memory stand-in for the application's bounded Search read contract."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = {document["id"]: document for document in documents}
        self.calls: list[dict[str, Any]] = []
        self.offline = False

    def _guard(self) -> None:
        if self.offline:
            raise SearchDown("connection refused")

    @staticmethod
    def _matches(document: dict[str, Any], expression: str) -> bool:
        remaining = expression
        for match in _IN.finditer(expression):
            wanted = {value.strip().strip("'").replace("''", "'")
                      for value in match.group("values").split(",")}
            held = {str(value) for value in document.get(match.group("field")) or []}
            if not wanted & held:
                return False
            remaining = remaining.replace(match.group(0), "")
        for match in _EQ.finditer(remaining):
            if str(document.get(match.group("field")) or "") != match.group("value"):
                return False
        return True

    def search(self, index: str, text: str = "*", *, top: int = 10, filter: str = "",
               select: Any = None, **_: Any) -> list[dict[str, Any]]:
        self._guard()
        self.calls.append({"index": index, "text": text, "filter": filter, "top": top,
                   "select": tuple(select or ())})
        terms = set() if text.strip() == "*" else _tokens(text)
        hits = []
        for document in self.documents.values():
            if filter and not self._matches(document, filter):
                continue
            surface = _tokens(document.get("content", ""))
            score = float(len(terms & surface)) if terms else 0.0
            hits.append((score, document))
        hits.sort(key=lambda item: -item[0])
        return [dict(document, **{"@search.score": score}) for score, document in hits[:top]]

    def search_count(self, index: str, text: str = "*", *, filter: str = "") -> int:
        self._guard()
        return len(self.search(index, text, top=10_000, filter=filter))

    def get_document(self, index: str, key: str) -> dict[str, Any] | None:
        self._guard()
        document = self.documents.get(key)
        return dict(document) if document else None

    def index_exists(self, name: str) -> bool:
        self._guard()
        return name == INDEX


def install_fake_index(case: unittest.TestCase,
                       records: list[dict[str, Any]]) -> FakeSearchIndexClient:
    """Point the knowledge seam at a fake index holding these normalised records."""
    import os

    client = FakeSearchIndexClient([build_document(record) for record in records])
    previous = {key: os.environ.get(key)
                for key in ("CYBEREYE_SEARCH_ENDPOINT", "CYBEREYE_MITRE_SEARCH_INDEX")}
    os.environ["CYBEREYE_SEARCH_ENDPOINT"] = ENDPOINT
    os.environ["CYBEREYE_MITRE_SEARCH_INDEX"] = INDEX
    knowledge_search.set_client(client)

    def restore() -> None:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        knowledge_search.reset_client()

    case.addCleanup(restore)
    return client


def document_key(doc_kind: str, doc_id: str) -> str:
    return safe_key(f"{doc_kind}:{doc_id}")


__all__ = ["ENDPOINT", "INDEX", "FakeSearchIndexClient", "SearchDown", "document_key",
           "install_fake_index"]
