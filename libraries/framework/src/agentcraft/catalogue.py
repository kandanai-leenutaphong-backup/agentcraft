"""Read installed capability metadata; repository-inspection owns task discovery."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
from typing import Any


def load_catalogue() -> dict[str, Any]:
    """Return a fresh generated snapshot without source checkout or provider access."""
    resource = resources.files("agentcraft").joinpath("capabilities.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Installed capability catalogue must declare schema_version 1")
    if not isinstance(document.get("capabilities"), list) or not isinstance(document.get("skills"), list):
        raise ValueError("Installed capability catalogue is incomplete")
    return document


def guidance_root() -> Path:
    """Return the installed, contained repository-catalogue package directory."""
    root = Path(str(resources.files("agentcraft").joinpath("guidance")))
    if not root.is_dir():
        raise FileNotFoundError("Installed Agentcraft guidance is missing; use a generated wheel installation")
    return root


def report(*, query: str | None = None, name: str | None = None,
           kind: str | None = None, limit: int = 5) -> dict[str, Any]:
    """List/search/read tasks with the existing reader's schema and integrity checks.

    Requires the declared repository-inspection tooling dependency. Unknown names,
    invalid searches and tampered or escaping guidance raise ValueError. No caller
    can supply another root, source path, credential or execution grant.
    """
    try:
        from repository_inspection.catalogue import report as catalogue_report
    except ModuleNotFoundError as error:
        if error.name in {"repository_inspection", "repository_inspection.catalogue"}:
            raise RuntimeError("Catalogue search/read requires repository-inspection from the declared agentcraft[tooling] artifact set") from error
        raise
    result = catalogue_report(guidance_root(), query=query, name=name, kind=kind, limit=limit)
    return {**result, "generation": load_catalogue()["generation"]}


__all__ = ["load_catalogue", "guidance_root", "report"]