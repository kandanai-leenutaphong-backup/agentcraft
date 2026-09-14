#!/usr/bin/env python3
"""Architectural fitness — the properties that must survive every future edit.

Framework-free on purpose: ``python3 tests/fitness.py``, no venv, no plugins,
so it runs in a container, in CI, and on a machine that has never installed
this component's dependencies.

WHY EACH CHECK EXISTS
---------------------
A test proves the code does what it does today. These prove the *shape*
stays: that this component depends on one published package through its
public surface only, that the donor test bed it was learned from never
becomes a runtime dependency, that it stays a leaf below the app, and that
the bounds protecting a browsable subscription-wide tree are still there.

EVERY CHECK IS PROVEN DISCRIMINATING
------------------------------------
A fitness check that cannot fail is decoration. Each one runs twice: once
against the real tree, once against a mutated temporary copy that violates
it. If the mutation passes, the check is reported broken and this script
exits non-zero — a green check whose negative is also green is worse than no
check, because it is believed.

Nothing here mutates a live file. Mutations are built inside
``tempfile.TemporaryDirectory``.
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".ruff_cache",
    "egg-info",
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".html",
    ".css",
}

# Assembled, so this file does not trip its own checks. The names are
# placeholders for "the donor tree this component was extracted from" and
# "a sibling component of the host application": the rule is the edge, not
# any particular project's vocabulary.
DONOR_NEEDLES = ("peer" + "_agent", "peer" + "agent", "donor" + "_testbeds")
DONOR_PATH_NEEDLES = (
    "donor" + "_testbeds/",
    "import peer" + "_agent",
    "from peer" + "_agent",
    "donor/donor" + "_testbeds",
)
SIBLING_NEEDLES = (
    "host" + "_app",
    "sibling" + "_view",
    "siblingview" + "_api",
    "host" + "/app",
)

#: The heading a documentation file must put donor provenance under. Anywhere
#: else, a donor name reads as a live relationship.
PROVENANCE_HEADING = "## Provenance"

BANNED_MODULE_PREFIXES = ("azdata.",)
BANNED_MODULE_FRAGMENTS = ("azdata.live", ".deploy", ".write")
BANNED_SYMBOLS = (
    "WritePolicy",
    "ProvisionPolicy",
    "KustoIngest",
    "SearchDocuments",
    "CosmosItems",
    "GremlinElements",
)

GUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

REQUIRED_FILES = (
    "README.md",
    "CONTRACT.md",
    "contracts/tree.schema.json",
    "backend/pyproject.toml",
    "backend/src/resource_explorer_api/app.py",
    "backend/src/resource_explorer_api/nodes.py",
    "backend/src/resource_explorer_api/security.py",
    "backend/src/resource_explorer_api/tree.py",
    "backend/tests/test_nodes.py",
    "backend/tests/test_tree.py",
    "backend/tests/test_security.py",
    "backend/tests/test_contracts.py",
)

#: The azdata constraint, exactly. A component that floats its provider's
#: major version cannot be validated by the app manifest.
AZDATA_CONSTRAINT = "azdata>=3.2.0,<4"

#: Bounds and codec invariants, as literal declarations. Written as
#: (file, fragment) so a removed clamp is named, not merely counted.
BOUND_DECLARATIONS = (
    ("backend/src/resource_explorer_api/settings.py", "MAX_CHILDREN = 500"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_DETAIL_KEYS = 40"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_DETAIL_VALUE_CHARS = 500"),
    ("backend/src/resource_explorer_api/settings.py", "DISCOVERY_TIMEOUT_SECS = 15.0"),
    ("backend/src/resource_explorer_api/settings.py", "REQUEST_TIMEOUT_SECS = 20.0"),
    ("backend/src/resource_explorer_api/settings.py", "INVENTORY_TTL_SECS = 30.0"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_CONTENT_BYTES = 1_048_576"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_CONTENT_ROWS = 100"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_TEXT_CHARS = 200_000"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_SEARCH_TERM_CHARS = 200"),
    ("backend/src/resource_explorer_api/settings.py", "MAX_SEARCH_HITS = 200"),
    ("backend/src/resource_explorer_api/nodes.py", "MAX_TOKEN_CHARS = 8192"),
    ("backend/src/resource_explorer_api/nodes.py", "MAX_PATH_SEGMENTS = 4"),
    ("backend/src/resource_explorer_api/nodes.py", "MAX_PATH_SEGMENT_CHARS = 1024"),
    ("backend/src/resource_explorer_api/nodes.py", "urlsafe_b64encode"),
    ("backend/src/resource_explorer_api/nodes.py", "raise InvalidNode"),
    ("backend/src/resource_explorer_api/tree.py", "max_children"),
    ("backend/src/resource_explorer_api/tree.py", "max_content_bytes"),
)


def walk(root: Path) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        found.append(path)
    return found


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def provenance_lines(text: str) -> set[int]:
    """Line numbers inside a ``## Provenance`` section of a markdown file."""
    inside = False
    allowed: set[int] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            inside = line.strip() == PROVENANCE_HEADING
            continue
        if inside:
            allowed.add(number)
    return allowed


# ----------------------------------------------------------------------
# The checks.
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Where a check looks. Swapped for a temporary copy to prove a failure."""

    component: Path


def check_structural(layout: Layout) -> list[str]:
    """The files a consumer, an operator and the app manifest all need."""
    failures = [
        f"{relative} is missing"
        for relative in REQUIRED_FILES
        if not (layout.component / relative).is_file()
    ]
    pyproject = layout.component / "backend" / "pyproject.toml"
    if pyproject.is_file():
        text = read(pyproject)
        if AZDATA_CONSTRAINT not in text:
            failures.append(
                f"backend/pyproject.toml does not declare {AZDATA_CONSTRAINT!r}"
            )
        if 'name = "resource_explorer_api"' not in text:
            failures.append("backend/pyproject.toml does not publish resource_explorer_api")
        if 'version = "0.1.0"' not in text:
            failures.append("backend/pyproject.toml does not declare a version")
    schema = layout.component / "contracts" / "tree.schema.json"
    if schema.is_file() and '"schemaVersion"' not in read(schema):
        failures.append("contracts/tree.schema.json does not declare schemaVersion")
    return failures


def check_no_donor_dependency(layout: Layout) -> list[str]:
    """The test bed this was learned from is reference material, not a provider.

    Documentation may say where the idea came from, under a heading that says
    so. Code, configuration and manifests may not name it at all, and no file
    anywhere may name a path into it: provenance is a sentence, a filesystem
    path is a dependency.
    """
    failures: list[str] = []
    for path in walk(layout.component):
        text = read(path)
        allowed = provenance_lines(text) if path.suffix == ".md" else set()
        for number, line in enumerate(text.splitlines(), start=1):
            for needle in DONOR_PATH_NEEDLES:
                if needle in line:
                    failures.append(f"{path}:{number}: depends on {needle!r}")
            if number in allowed:
                continue
            for needle in DONOR_NEEDLES:
                if needle in line:
                    failures.append(f"{path}:{number}: names the donor {needle!r}")
    return sorted(set(failures))


def check_azdata_public_surface_only(layout: Layout) -> list[str]:
    """One import surface: ``from azdata import ...``.

    The module layout below the package root is the library's to change. A
    consumer reaching into it turns an internal move into a breaking change,
    and a consumer that can name a provisioner is one edit from calling one.
    """
    failures: list[str] = []
    source = layout.component / "backend" / "src"
    for path in sorted(source.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            tree = ast.parse(read(path), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path}: will not parse: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                failures += _module_failures(path, node.lineno, node.module or "")
                for alias in node.names:
                    failures += _symbol_failures(path, node.lineno, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    failures += _module_failures(path, node.lineno, alias.name)
            elif isinstance(node, ast.Attribute):
                failures += _symbol_failures(path, node.lineno, node.attr)
            elif isinstance(node, ast.Name):
                failures += _symbol_failures(path, node.lineno, node.id)
    return sorted(set(failures))


def _module_failures(path: Path, line: int, module: str) -> list[str]:
    if not module:
        return []
    found = [
        f"{path}:{line}: imports {module!r}, not the public azdata surface"
        for prefix in BANNED_MODULE_PREFIXES
        if module.startswith(prefix)
    ]
    found += [
        f"{path}:{line}: references {module!r} ({fragment!r} mutates)"
        for fragment in BANNED_MODULE_FRAGMENTS
        if fragment in module
    ]
    return found


def _symbol_failures(path: Path, line: int, name: str) -> list[str]:
    if name in BANNED_SYMBOLS or name.endswith("Provisioner"):
        return [f"{path}:{line}: names {name!r}, which mutates"]
    return []


def check_no_app_or_sibling_dependency(layout: Layout) -> list[str]:
    """The dependency edge points app -> component, and never back.

    A component that names the app cannot be tested without it; a component
    that names a sibling's private module has taken an edge the contract only
    permits through a published package.
    """
    failures: list[str] = []
    for path in walk(layout.component):
        if path.suffix == ".md":
            continue
        text = read(path)
        for needle in SIBLING_NEEDLES:
            if needle in text:
                failures.append(f"{path}: names {needle!r}")
    return sorted(set(failures))


def check_no_server_sdk_in_browser_code(layout: Layout) -> list[str]:
    """A management SDK in a bundle is a credential path in a browser.

    The frontend may not exist yet. The check still has to be here and still
    has to be discriminating, or it arrives after the code it was meant to
    constrain.
    """
    failures: list[str] = []
    for path in walk(layout.component / "frontend"):
        text = read(path)
        for needle in (
            "@azure/",
            "azure-identity",
            "management.azure.com",
            "DefaultAzureCredential",
        ):
            if needle in text:
                failures.append(f"{path}: browser code mentions {needle!r}")
        if "tests" in path.parts or ".test." in path.name or ".spec." in path.name:
            continue
        for match in GUID.findall(text):
            failures.append(f"{path}: shipped browser code embeds a GUID ({match})")
    return failures


def check_bounds_and_codec(layout: Layout) -> list[str]:
    """Every clamp on a subscription-wide browsable tree, still declared.

    These are the difference between a lazy tree and an unbounded one, and
    between an opaque node id and a parser for attacker-supplied coordinates.
    """
    failures: list[str] = []
    for relative, fragment in BOUND_DECLARATIONS:
        path = layout.component / relative
        if not path.is_file():
            failures.append(f"{relative} is missing")
            continue
        if fragment not in read(path):
            failures.append(f"{relative} no longer declares {fragment!r}")
    return failures


# ----------------------------------------------------------------------
# Mutations. Each one must make its check fail.
# ----------------------------------------------------------------------


def copy_component(tmp: Path) -> Path:
    """A real copy, so a mutation is the only difference from the real tree."""
    target = tmp / "resource_explorer"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.egg-info"),
    )
    return target


def mutate_structural(tmp: Path) -> Layout:
    component = copy_component(tmp)
    (component / "contracts" / "tree.schema.json").unlink()
    (component / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "resource_explorer_api"\ndependencies = ["azdata"]\n',
        encoding="utf-8",
    )
    return Layout(component=component)


def mutate_donor_dependency(tmp: Path) -> Layout:
    # Assembled, so writing the violation does not make this file one.
    component = copy_component(tmp)
    (component / "backend" / "src" / "resource_explorer_api" / "donor.py").write_text(
        "import sys\n"
        'sys.path.insert(0, "../../donor' + '_testbeds/peer' + '_agent/src")\n'
        "from peer" + "_agent import invoke_tool\n",
        encoding="utf-8",
    )
    (component / "README.md").write_text(
        "# Resource explorer\n\n## Operating\n\nRun the peer" + "_agent tree instead.\n",
        encoding="utf-8",
    )
    return Layout(component=component)


def mutate_azdata_private_import(tmp: Path) -> Layout:
    component = copy_component(tmp)
    (component / "backend" / "src" / "resource_explorer_api" / "leak.py").write_text(
        "from azdata.core.discover import DiscoveryScope\n"
        "from azdata.search.write import SearchDocuments\n"
        "\n"
        "def upload(client):\n"
        "    return SearchDocuments(client)\n",
        encoding="utf-8",
    )
    return Layout(component=component)


def mutate_app_dependency(tmp: Path) -> Layout:
    component = copy_component(tmp)
    (component / "backend" / "src" / "resource_explorer_api" / "shell.py").write_text(
        "from host" + "_app.shell import mount\n"
        "from sibling" + "_view.backend.src.siblingview" + "_api.cache import SnapshotCache\n",
        encoding="utf-8",
    )
    return Layout(component=component)


def mutate_browser_sdk(tmp: Path) -> Layout:
    component = copy_component(tmp)
    browser = component / "frontend" / "src"
    browser.mkdir(parents=True, exist_ok=True)
    (browser / "client.ts").write_text(
        'import { DefaultAzureCredential } from "@azure/identity";\n'
        'const sub = "11111111-2222-3333-4444-555555555555";\n',
        encoding="utf-8",
    )
    return Layout(component=component)


def mutate_bounds(tmp: Path) -> Layout:
    component = copy_component(tmp)
    settings = component / "backend" / "src" / "resource_explorer_api" / "settings.py"
    settings.write_text(
        read(settings)
        .replace("MAX_CHILDREN = 500", "MAX_CHILDREN = 10_000_000")
        .replace("MAX_CONTENT_BYTES = 1_048_576", "MAX_CONTENT_BYTES = 1 << 40"),
        encoding="utf-8",
    )
    nodes = component / "backend" / "src" / "resource_explorer_api" / "nodes.py"
    nodes.write_text(
        read(nodes).replace("MAX_TOKEN_CHARS = 8192", "MAX_TOKEN_CHARS = 1 << 30"),
        encoding="utf-8",
    )
    return Layout(component=component)


@dataclass(frozen=True)
class Check:
    number: int
    name: str
    run: Callable[[Layout], list[str]]
    mutate: Callable[[Path], Layout]


CHECKS: tuple[Check, ...] = (
    Check(1, "structural: required files, package identity, azdata constraint", check_structural, mutate_structural),
    Check(2, "the donor test bed is provenance, never a dependency", check_no_donor_dependency, mutate_donor_dependency),
    Check(3, "azdata is reached through its public top-level surface only", check_azdata_public_surface_only, mutate_azdata_private_import),
    Check(4, "no dependency on the app or a sibling component", check_no_app_or_sibling_dependency, mutate_app_dependency),
    Check(5, "no server SDK, endpoint or GUID in browser code", check_no_server_sdk_in_browser_code, mutate_browser_sdk),
    Check(6, "the tree bounds and the opaque node codec are enforced", check_bounds_and_codec, mutate_bounds),
)


def main() -> int:
    layout = Layout(component=ROOT)
    failed = 0
    undiscriminating = 0

    for check in CHECKS:
        failures = check.run(layout)
        with tempfile.TemporaryDirectory() as raw:
            mutated = check.mutate(Path(raw))
            caught = check.run(mutated)

        discriminating = bool(caught)
        status = "PASS" if not failures else "FAIL"
        proof = "proven discriminating" if discriminating else "NOT DISCRIMINATING"
        print(f"[{status}] {check.number}. {check.name} ({proof})")
        for failure in failures:
            print(f"        {failure}")
        if failures:
            failed += 1
        if not discriminating:
            undiscriminating += 1
            print("        the mutated copy did not trip this check")

    total = len(CHECKS)
    print(
        f"\n{total - failed}/{total} checks pass, "
        f"{total - undiscriminating}/{total} proven discriminating"
    )
    return 1 if (failed or undiscriminating) else 0


if __name__ == "__main__":
    sys.exit(main())
