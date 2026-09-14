"""F4 — import hygiene: this component knows one surface, ``azdata`` itself.

WHY THIS IS A TEST AND NOT A CONVENTION
---------------------------------------
``from azdata.core.discover import ...`` works. It is also a private edge:
the module layout below the package root is the library's to change, and a
consumer that reaches into it turns an internal move into a breaking change.
The public top-level surface is the contract; this test is what keeps the
distinction from eroding one convenient import at a time.

It also refuses the write and deploy planes by name. An explorer that can
name a provisioner is one edit away from being able to call one.
"""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import SOURCE_ROOT

BANNED_MODULE_FRAGMENTS = ("azdata.", "azdata_")
BANNED_SYMBOLS = (
    "WritePolicy",
    "ProvisionPolicy",
    "KustoIngest",
    "SearchDocuments",
    "CosmosItems",
    "GremlinElements",
    "Environment",
)


def sources() -> list[Path]:
    return [
        path
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def test_there_is_source_to_scan() -> None:
    """A scan over nothing passes vacuously; assert it is scanning something."""
    assert len(sources()) >= 9


def test_no_module_imports_an_azdata_submodule() -> None:
    failures: list[str] = []
    for path in sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if any(module.startswith(f) for f in BANNED_MODULE_FRAGMENTS):
                    failures.append(f"{path.name}:{node.lineno}: from {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(f) for f in BANNED_MODULE_FRAGMENTS):
                        failures.append(f"{path.name}:{node.lineno}: import {alias.name}")
    assert not failures, "\n".join(failures)


def test_no_module_names_a_mutating_symbol() -> None:
    failures: list[str] = []
    for path in sources():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name and (name in BANNED_SYMBOLS or name.endswith("Provisioner")):
                failures.append(f"{path.name}:{node.lineno}: names {name}")
    assert not failures, "\n".join(failures)


def test_no_module_imports_the_app_or_a_sibling_component() -> None:
    # Placeholder names for the host application and its sibling components:
    # the enforced rule is the dependency edge, not any project's vocabulary.
    forbidden = ("host" + "_app", "sibling" + "_view", "siblingview" + "_api", "peer" + "_agent")
    failures = [
        f"{path.name}: names {needle}"
        for path in sources()
        for needle in forbidden
        if needle in path.read_text(encoding="utf-8")
    ]
    assert not failures, "\n".join(failures)


def test_the_scan_would_catch_a_violation(tmp_path: Path) -> None:
    """The paired negative: an AST scan that cannot fail proves nothing."""
    leak = tmp_path / "leak.py"
    leak.write_text(
        "from azdata.core.discover import DiscoveryScope\n"
        "from azdata.search.write import SearchDocuments\n",
        encoding="utf-8",
    )
    tree = ast.parse(leak.read_text(encoding="utf-8"))
    modules = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert all(module.startswith("azdata.") for module in modules)
    assert "SearchDocuments" in leak.read_text(encoding="utf-8")
