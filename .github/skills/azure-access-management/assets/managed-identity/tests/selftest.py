#!/usr/bin/env python3
"""selftest — proves this box's templates are what they claim, without deploying.

Infrastructure cannot be selftested the way a library can: the artefact *is* the
side effect, and there is no fake Azure to substitute. So acceptance here is a
different shape, stated plainly rather than pretended away:

    1. **Invariants over the compiled template.** The ARM JSON in ``build/`` is
       committed and asserted against — deterministic assignment names, a
       principal type on every grant, a written reason on every grant, no
       secret-reading functions, no hardcoded principals.
    2. **Render-and-diff.** When the Bicep compiler is available, the templates
       are recompiled and compared to the committed output. A drift means the
       sources changed without the reviewed artefact being regenerated.

    What this cannot prove is that the deployment succeeds. That is
    ``scripts/deploy.sh`` against a real subscription, and ``scripts/verify.py``
    afterwards.

Run:  python3 tests/selftest.py    (exit 0 = the templates hold)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BICEP = ROOT / "bicep"
BUILD = ROOT / "build" / "main.json"

_PASS = 0
_FAIL = 0

# A role assignment's name must be derived from the triple that identifies it.
# Anything else is either non-idempotent or collides on redeploy (GOTCHAS.md G1).
_GUID_NAME = re.compile(r"\[guid\(", re.I)

# Functions that read secret material. None of them belongs in a template whose
# entire purpose is to avoid secrets (GOTCHAS.md G10).
_SECRET_FUNCTIONS = ("listkeys", "listsecrets", "listadminkeys",
                     "listconnectionstrings", "listaccountsas", "listservicesas")

# A well-formed role definition GUID.
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record one assertion."""
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ok   {label}")
    else:
        _FAIL += 1
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def walk(node, path="") -> list[tuple[str, dict]]:
    """Yield every resource object anywhere in a template, including nested
    deployments, with the path it was found at."""
    found: list[tuple[str, dict]] = []
    if isinstance(node, dict):
        for resource in _resource_list(node.get("resources")):
            found.append((path, resource))
            nested = (resource.get("properties", {})
                      .get("template", {}))
            if nested:
                found.extend(walk(nested, f"{path}/{resource.get('name', '?')}"))
    return found


def _resource_list(resources) -> list[dict]:
    """ARM resources are a list in one schema version and a dict in another."""
    if isinstance(resources, list):
        return [r for r in resources if isinstance(r, dict)]
    if isinstance(resources, dict):
        return [r for r in resources.values() if isinstance(r, dict)]
    return []


# ── checks ──────────────────────────────────────────────────────────────────


def test_sources_present() -> None:
    print("\nsources")
    check("main template present", (BICEP / "main.bicep").is_file())
    check("roles file present", (BICEP / "roles.bicep").is_file())
    check("identity module present", (BICEP / "modules" / "identity.bicep").is_file())
    check("compiled artefact committed", BUILD.is_file(),
            "run az bicep build --file bicep/main.bicep --outfile build/main.json")


def test_role_catalogue() -> None:
    print("\nrole catalogue")
    text = (BICEP / "roles.bicep").read_text(encoding="utf-8")
    entries = dict(re.findall(r"^\s+(\w+):\s+'([0-9a-f-]{36})'", text, re.M))
    check("roles are defined", len(entries) >= 10)
    check("every id is a well-formed GUID",
          all(_GUID.match(v) for v in entries.values()),
          str([k for k, v in entries.items() if not _GUID.match(v)]))
    duplicates = [v for v in entries.values() if list(entries.values()).count(v) > 1]
    check("no role id is listed twice", not duplicates, str(set(duplicates)))
    check("exported for compile-time import", "@export()" in text)

    # The two that are most often conflated, and the reason G3 exists.
    check("search control-plane and data-plane roles are distinct",
          entries.get("searchServiceContributor")
          != entries.get("searchIndexDataContributor"))
    check("data-plane storage roles are present, not just Contributor",
          "storageBlobDataContributor" in entries)


def test_no_literal_guids_in_templates() -> None:
    print("\nreviewability")
    for path in sorted(BICEP.rglob("*.bicep")):
        if path.name == "roles.bicep":
            continue
        text = path.read_text(encoding="utf-8")
        # Ignore GUIDs inside comments: a gotcha reference may cite one.
        code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))
        literals = re.findall(r"'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                              r"[0-9a-f]{4}-[0-9a-f]{12}'", code)
        check(f"{path.name} contains no literal role GUID", not literals,
              str(literals))


def test_compiled_assignments() -> None:
    print("\nrole assignments (compiled)")
    template = json.loads(BUILD.read_text(encoding="utf-8"))
    resources = walk(template)
    assignments = [
        (path, r) for path, r in resources
        if str(r.get("type", "")).lower() == "microsoft.authorization/roleassignments"
    ]
    check("assignments are present in the compiled output", len(assignments) >= 3,
          f"found {len(assignments)}")

    for path, assignment in assignments:
        label = f"{path}/{assignment.get('name', '?')[:40]}"
        name = str(assignment.get("name", ""))
        check(f"G1 deterministic name: {label[:60]}", bool(_GUID_NAME.search(name)),
              f"name is {name[:80]!r}")

        properties = assignment.get("properties", {})
        check(f"G4 principalType set: {label[:60]}",
              bool(properties.get("principalType")))
        check(f"role id via subscriptionResourceId: {label[:60]}",
              "subscriptionResourceId" in str(properties.get("roleDefinitionId", "")))
        check(f"a written reason is attached: {label[:60]}",
              bool(str(properties.get("description", "")).strip()))


def test_no_secrets() -> None:
    print("\nsecrets (G10)")
    sources = list(BICEP.rglob("*.bicep")) + [BUILD]
    for path in sorted(sources):
        text = path.read_text(encoding="utf-8").lower()
        used = [fn for fn in _SECRET_FUNCTIONS if fn + "(" in text]
        check(f"{path.name} reads no secret material", not used, str(used))

    text = BUILD.read_text(encoding="utf-8")
    check("no @secure() parameters are needed at all", "securestring" not in text.lower())

    template = json.loads(text)
    outputs = template.get("outputs", {})
    check("outputs carry ids, never credentials",
          not any(k.lower().endswith(("key", "secret", "password", "connectionstring"))
                  for k in outputs))
    check("the identity's principal id is an output",
          "principalId" in outputs)
    check("the grant list is an output, for the verifier",
          "grants" in outputs)


def test_no_hardcoded_environment() -> None:
    print("\nportability")
    for path in sorted(BICEP.rglob("*.bicep")):
        text = path.read_text(encoding="utf-8")
        code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))
        check(f"{path.name} hardcodes no subscription id",
              "/subscriptions/" not in code)
        check(f"{path.name} hardcodes no tenant domain",
              ".onmicrosoft.com" not in code)

    main = (BICEP / "main.bicep").read_text(encoding="utf-8")
    check("location defaults to the resource group's",
          "resourceGroup().location" in main)
    check("G9 cross-group grants are supported by scoping the module",
          "scope: resourceGroup(" in main)
    check("grants are conditional, so an unused target is skipped",
          main.count("= if (") >= 3)


def test_scope_is_narrow() -> None:
    print("\nleast privilege (G5)")
    template = json.loads(BUILD.read_text(encoding="utf-8"))
    check("no subscription-scope deployment",
          template.get("$schema", "").endswith("deploymentTemplate.json#"),
          "this template is resource-group scoped by design")

    # Which roles are actually GRANTED, not merely catalogued. The role map is
    # compiled into the template, so searching the whole document would report
    # every role the catalogue names as if it were assigned.
    granted = _granted_role_ids(template)
    check("granted roles were resolved", bool(granted), "found none to check")
    check("Owner is not granted anywhere",
          "8e3af657-a8ff-443c-a75c-2fe8c4bcb635" not in granted)
    check("User Access Administrator is not granted anywhere",
          "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9" not in granted)
    check("Contributor is not granted anywhere",
          "b24988ac-6180-42a0-ab88-20f7382dd24c" not in granted)

    main = (BICEP / "main.bicep").read_text(encoding="utf-8")
    check("every grant names a specific resource, not a group",
          "searchServiceName:" in main and "accountName:" in main)


def _granted_role_ids(template: dict) -> set[str]:
    """Role definition GUIDs reaching an actual assignment.

    The compiler passes the role as ``variables('roleIds').<name>`` rather than
    as a literal, so the catalogue has to be resolved. Searching the raw
    document instead would report every role the catalogue *names* as though it
    were granted — which is the difference between a permission review and a
    list of roles that exist.
    """
    catalogue = template.get("variables", {}).get("roleIds", {})
    granted: set[str] = set()
    text = json.dumps(template)

    for value in re.findall(r'"roleDefinitionId"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"', text):
        granted.update(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                                  r"[0-9a-f]{4}-[0-9a-f]{12}", value))
        for name in re.findall(r"variables\('roleIds'\)\.(\w+)", value):
            resolved = catalogue.get(name)
            if resolved:
                granted.add(resolved)

    for _, resource in walk(template):
        if str(resource.get("type", "")).lower() != "microsoft.authorization/roleassignments":
            continue
        expression = str(resource.get("properties", {}).get("roleDefinitionId", ""))
        granted.update(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                                  r"[0-9a-f]{4}-[0-9a-f]{12}", expression))
    return granted


def test_render_and_diff() -> None:
    print("\nrender-and-diff")
    if not shutil.which("az"):
        check("bicep compiler available (skipped — az not installed)", True)
        return
    with tempfile.TemporaryDirectory() as raw:
        target = Path(raw) / "main.json"
        result = subprocess.run(
            ["az", "bicep", "build", "--file", str(BICEP / "main.bicep"),
             "--outfile", str(target)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            check("templates compile", False, result.stderr.strip()[-300:])
            return
        check("templates compile", True)

        fresh = json.loads(target.read_text(encoding="utf-8"))
        committed = json.loads(BUILD.read_text(encoding="utf-8"))
        # The compiler stamps a build version into metadata; comparing it would
        # make every compiler upgrade look like a template change.
        for document in (fresh, committed):
            document.get("metadata", {}).pop("_generator", None)
        check("committed artefact matches the sources",
              fresh == committed,
              "run: az bicep build --file bicep/main.bicep --outfile build/main.json")


def main() -> int:
    print("bicep-managed-identity selftest")
    test_sources_present()
    if not BUILD.is_file():
        print("\nno compiled artefact; cannot continue")
        return 1
    test_role_catalogue()
    test_no_literal_guids_in_templates()
    test_compiled_assignments()
    test_no_secrets()
    test_no_hardcoded_environment()
    test_scope_is_narrow()
    test_render_and_diff()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    if _FAIL:
        print("SELFTEST FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
