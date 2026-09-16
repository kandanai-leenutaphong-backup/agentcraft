"""Azure AI Search — retrieval whose result the caller can actually read.

WHY THE PROJECTION IS MANDATORY
-------------------------------
A search index returns whatever the schema holds: chunk ids, parent ids,
embedding vectors, scoring metadata. Handing that back whole is the most
common way a retrieval tool ruins a context window — one call, twenty
fields per hit, most of them meaningless to the reader.

The tool here projects each hit down to four fields and caps the text. The
projection is *not* something this box could have guessed: which field
holds the text is the caller's schema. That is why `project_doc` is a
required argument on any search connector worth using, and why the mapping
lives in this file rather than in the tool layer.

RESULT SHAPES AND THEIR CARDS
-----------------------------
`search_knowledge` -> {results: [{title, source, score, text}], count}
                   -> `search` archetype

Run it::

    python3 examples/azure/knowledge_search.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backends import FakeSearch  # noqa: E402

from toolshape import (  # noqa: E402
    Param,
    ToolSpec,
    integer_range,
    label,
    one_of,
    purpose_built,
)

ARCHETYPES = {"search_knowledge": "search"}

BACKEND = FakeSearch()           # real: SearchConnector(...).execute
INDEXES = ("procedures", "incidents")

# The card shows title, source, score and a text snippet. Anything past the
# cap is invisible to the reader and pure cost to the context window.
TEXT_CAP = 600

# First non-empty wins. Ordered by how specific the field is to the chunk.
TEXT_FIELDS = ("chunk", "content", "text", "body")


SEARCH_KNOWLEDGE = ToolSpec(
    name="search_knowledge",
    purpose="Retrieve passages from a document index, best match first.",
    call_when=(
        "When you need written guidance, procedure or precedent rather than "
        "records. Pick the index from the listed values; ask a full question "
        "rather than keywords — the index is semantic."
    ),
    params=[
        Param("question", "The question to answer, in full.", validator=label(max_len=400)),
        Param("index", "Which corpus to search, one of the values listed.",
              validator=one_of(INDEXES)),
        Param("top_k", "How many passages to return.",
              validator=integer_range(1, 10), required=False, default=5),
    ],
    returns="{results: [{title, source, score, text}], count: N}",
    dedupe_on=("question", "index", "top_k"),
    replaces="search_raw",
)


@purpose_built(SEARCH_KNOWLEDGE)
def search_knowledge(question: str, index: str, top_k: int = 5):
    """Returns a dict: the search card wants hits, not a table of columns."""
    hits = BACKEND.search(search_text=question, index_name=index, top=top_k)
    results = [_project(hit) for hit in hits]
    return {
        "results": results,
        "count": len(results),
        "scope": {"index": index, "top_k": top_k},
    }


def _project(doc: dict) -> dict:
    """One index document -> one readable hit. The schema stops here.

    Every decision in this function is a consequence for the reader: which
    field is the text, how much of it survives, how precise the score looks.
    None of them can be defaulted by a generic tool layer.
    """
    text = next((str(doc[field]) for field in TEXT_FIELDS if doc.get(field)), "")
    return {
        "title": doc.get("title") or doc.get("filename") or "untitled",
        "source": doc.get("filename", ""),
        "score": round(float(doc.get("@search.score", 0.0)), 2),
        "text": text[:TEXT_CAP],
    }


def demo() -> list[str]:
    return [
        search_knowledge(question="how do I isolate a pump", index="procedures"),
        search_knowledge(question="anything", index="everything"),         # refused
        search_knowledge(question="nothing at all", index="procedures"),   # empty
    ]


if __name__ == "__main__":
    for payload in demo():
        print(json.dumps(json.loads(payload), indent=2)[:500])
        print("-" * 60)
