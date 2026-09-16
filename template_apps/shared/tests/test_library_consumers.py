"""Both templates select canonical public async data operations."""

import ast
from pathlib import Path


def test_both_consumer_sources_select_the_same_public_owner():
    applications = Path(__file__).resolve().parents[2]
    paths = [applications / "investigation_app/app/cybereye/backend/knowledge/search.py",
             applications / "custom_optimizer/app/cybereye/backend/knowledge.py"]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        imported = {alias.name for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.ImportFrom) and node.module == "azdata"
                    for alias in node.names}
        assert {"connect", "QueryRequest", "Policy"} <= imported
        assert any(isinstance(node, ast.Await) for node in ast.walk(ast.parse(source)))