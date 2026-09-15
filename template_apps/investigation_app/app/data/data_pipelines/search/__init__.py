"""Publishing pinned MITRE ATT&CK knowledge into one Azure AI Search index.

Read-only over the normalised corpora on disk; write-only to the one index it is named.
No telemetry is published here, by any route.
"""

from __future__ import annotations

from .documents import ANALYTIC, SITUATION_TYPE, build_document, document_key, mitre_index
from .load import LoadRefused, LoadReport, ensure_index, load_documents
from .sources import display_name, index_name, mitre_provenance, mitre_records

__all__ = [
    "ANALYTIC",
    "SITUATION_TYPE",
    "LoadRefused",
    "LoadReport",
    "build_document",
    "display_name",
    "document_key",
    "ensure_index",
    "index_name",
    "load_documents",
    "mitre_index",
    "mitre_provenance",
    "mitre_records",
]
