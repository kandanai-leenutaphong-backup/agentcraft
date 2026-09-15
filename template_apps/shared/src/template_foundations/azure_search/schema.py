"""Index shape: what an index holds and how it is searched.

Rendering is deterministic. A non-deterministic render makes every index read as
changed on every comparison.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .config import SearchConfigError, valid_index_name

#: Fixed because they are internal cross-references inside a rendered definition.
VECTOR_PROFILE = "vector-profile"
VECTOR_ALGORITHM = "hnsw-config"
SEMANTIC_CONFIG = "semantic-config"

#: Document keys accept only these characters; a path separator is the usual offender.
_UNSAFE_KEY = re.compile(r"[^A-Za-z0-9_\-=]")

_EDM = {
    "string": "Edm.String",
    "int": "Edm.Int32",
    "long": "Edm.Int64",
    "double": "Edm.Double",
    "bool": "Edm.Boolean",
    "datetime": "Edm.DateTimeOffset",
    "string_collection": "Collection(Edm.String)",
}


def safe_key(value: str) -> str:
    """A document key the service accepts, deterministic so a reload overwrites."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{_UNSAFE_KEY.sub('_', value)[:100]}-{digest}"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field. Only the properties that change behaviour are exposed."""

    name: str
    type: str = "string"
    key: bool = False
    searchable: bool = False
    filterable: bool = False
    sortable: bool = False
    facetable: bool = False
    retrievable: bool = True

    def render(self) -> dict[str, Any]:
        edm = _EDM.get(self.type)
        if edm is None:
            raise SearchConfigError(f"unknown field type {self.type!r}; use one of {sorted(_EDM)}")
        return {
            "name": self.name,
            "type": edm,
            "key": self.key,
            "searchable": self.searchable and edm in ("Edm.String", "Collection(Edm.String)"),
            "filterable": self.filterable,
            "sortable": self.sortable,
            "facetable": self.facetable,
            "retrievable": self.retrievable,
        }


@dataclass(frozen=True, slots=True)
class VectorSpec:
    """A vector field: its name, its width, and the field whose text it embeds."""

    name: str
    dimensions: int
    content_field: str

    def __post_init__(self) -> None:
        if self.dimensions < 1:
            raise SearchConfigError("dimensions must be positive")


@dataclass(frozen=True, slots=True)
class IndexSpec:
    """One index: what it holds, what it is for, and how it is searched.

    ``purpose`` is required. An index nobody can describe is an index nobody can
    decide to keep or delete.
    """

    name: str
    purpose: str
    fields: tuple[FieldSpec, ...]
    vector: VectorSpec | None = None
    semantic_title_field: str = ""
    semantic_content_fields: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not valid_index_name(self.name):
            raise SearchConfigError(
                f"index name {self.name!r} must be lowercase letters, digits and single dashes"
            )
        if not self.purpose.strip():
            raise SearchConfigError("purpose must not be empty")
        if not self.fields:
            raise SearchConfigError("an index needs at least one field")
        keys = [f.name for f in self.fields if f.key]
        if len(keys) != 1:
            raise SearchConfigError(f"exactly one key field is required, found {len(keys)}")
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise SearchConfigError("field names must be unique")
        if self.vector is not None:
            if self.vector.name in names:
                raise SearchConfigError(f"vector field {self.vector.name!r} collides with a declared field")
            if self.vector.content_field not in names:
                raise SearchConfigError(f"vector content_field {self.vector.content_field!r} is not a declared field")

    @property
    def key_field(self) -> str:
        return next(f.name for f in self.fields if f.key)


def render_index(spec: IndexSpec) -> dict[str, Any]:
    """The exact JSON the service is sent for a create-or-update."""
    fields = [f.render() for f in spec.fields]
    definition: dict[str, Any] = {"name": spec.name, "fields": fields}

    if spec.vector is not None:
        fields.append({
            "name": spec.vector.name,
            "type": "Collection(Edm.Single)",
            "searchable": True,
            # Thousands of floats per document, useless to a caller, and returning
            # them dominates the response.
            "retrievable": False,
            "filterable": False,
            "sortable": False,
            "facetable": False,
            "dimensions": spec.vector.dimensions,
            "vectorSearchProfile": VECTOR_PROFILE,
        })
        definition["vectorSearch"] = {
            # Written explicitly so an index does not change shape when service
            # defaults change.
            "algorithms": [{
                "name": VECTOR_ALGORITHM,
                "kind": "hnsw",
                "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"},
            }],
            "profiles": [{"name": VECTOR_PROFILE, "algorithm": VECTOR_ALGORITHM}],
        }

    if spec.semantic_content_fields:
        prioritized: dict[str, Any] = {
            "prioritizedContentFields": [{"fieldName": n} for n in spec.semantic_content_fields],
            "prioritizedKeywordsFields": [],
        }
        if spec.semantic_title_field:
            prioritized["titleField"] = {"fieldName": spec.semantic_title_field}
        definition["semantic"] = {
            "configurations": [{"name": SEMANTIC_CONFIG, "prioritizedFields": prioritized}]
        }

    return definition
