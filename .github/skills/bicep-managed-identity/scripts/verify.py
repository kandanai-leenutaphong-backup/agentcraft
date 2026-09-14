#!/usr/bin/env python3
"""verify — assert the live permission surface matches what was deployed.

A successful deployment is not proof that the access exists. Two things routinely
break that assumption:

    - **A policy rewrote it.** An Azure Policy ``Modify`` effect can alter or
      revert a property *after* the control plane returns success. The
      deployment reports Succeeded and the resource does not match the template
      (GOTCHAS.md G12).
    - **Something else granted it.** An assignment created out of band — by a
      person, a portal click, another pipeline — is invisible to the template and
      survives it. Extra access is exactly as much of a finding as missing
      access, and nothing else reports it.

Reads the deployment's ``grants`` output and compares it to the live
assignments, in both directions.

    python3 scripts/verify.py -g <resource-group> -n <deployment-name>
    python3 scripts/verify.py -g <rg> -n <deployment> --strict   # extras fail

Exit codes: 0 the surface matches, 1 it does not, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

# Role definition GUID -> readable name, for the report. Kept in step with
# bicep/roles.bicep; the selftest does not enforce that, so treat a missing name
# as cosmetic rather than as a failure.
ROLE_NAMES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9": "User Access Administrator",
    "7ca78c08-252a-4471-8644-bb5ff32d4ba0": "Search Service Contributor",
    "8ebe5a00-799e-43f5-93ac-243d3dce84a7": "Search Index Data Contributor",
    "1407120a-92aa-4202-b7e9-c0e197c71c8f": "Search Index Data Reader",
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd": "Cognitive Services OpenAI User",
    "a97b65f3-24c7-4388-baec-2e87135dc908": "Cognitive Services User",
    "ba92f5b4-2d11-453d-a403-e96b0029c9fe": "Storage Blob Data Contributor",
    "4633458b-17de-408a-b874-0445c86b69e6": "Key Vault Secrets User",
}

# Roles that should never appear on a workload identity scoped to one resource.
# Finding one means either the template is wrong or somebody granted it by hand.
DANGEROUS = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",  # Owner
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9",  # User Access Administrator
}


def run(*args: str) -> str:
    """Run an Azure CLI command and return stdout, or exit with its error."""
    result = subprocess.run(["az", *args], capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"  az {' '.join(args[:3])} failed: {result.stderr.strip()[:400]}")
        sys.exit(1)
    return result.stdout.strip()


def role_name(role_id: str) -> str:
    """Readable role name, falling back to the GUID."""
    return ROLE_NAMES.get(role_id.lower(), role_id)


def deployment_grants(group: str, name: str) -> list[dict]:
    """The grants the deployment declared it made."""
    raw = run("deployment", "group", "show", "-g", group, "-n", name,
              "--query", "properties.outputs.grants.value", "-o", "json")
    return json.loads(raw or "[]")


def live_assignments(principal_id: str) -> list[dict]:
    """Every assignment the principal holds, at any scope."""
    raw = run("role", "assignment", "list", "--assignee", principal_id, "--all",
              "--query",
              "[].{role:roleDefinitionId,scope:scope,description:description,name:name}",
              "-o", "json")
    assignments = json.loads(raw or "[]")
    for assignment in assignments:
        assignment["roleId"] = assignment["role"].rsplit("/", 1)[-1].lower()
    return assignments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-g", "--group", required=True)
    parser.add_argument("-n", "--deployment", required=True)
    parser.add_argument("--strict", action="store_true",
                        help="treat access the template did not declare as a failure")
    args = parser.parse_args()

    declared = deployment_grants(args.group, args.deployment)
    if not declared:
        print("  the deployment declared no grants")
        return 1

    principals = {g["principalId"] for g in declared}
    problems = 0

    for principal in sorted(principals):
        print(f"\nprincipal {principal}")
        live = live_assignments(principal)
        live_pairs = {(a["roleId"], a["scope"].lower()) for a in live}

        expected = [g for g in declared if g["principalId"] == principal]
        for grant in expected:
            role_id = grant["roleDefinitionId"].lower()
            match = [a for a in live
                     if a["roleId"] == role_id
                     and grant["scopeName"].lower() in a["scope"].lower()]
            if match:
                reason = match[0].get("description") or "(no reason recorded)"
                print(f"  ok   {role_name(role_id)} on {grant['scopeName']}")
                print(f"       reason: {reason}")
            else:
                # G12: the deployment said Succeeded, so if the grant is absent
                # something removed or rewrote it afterwards.
                print(f"  FAIL {role_name(role_id)} on {grant['scopeName']} "
                      f"— declared but NOT present")
                print(f"       the deployment reported success, so check for an "
                      f"Azure Policy Modify effect in the Activity Log")
                problems += 1

        expected_pairs = {
            (g["roleDefinitionId"].lower(),)
            for g in expected
        }
        for assignment in live:
            if assignment["roleId"] in DANGEROUS:
                print(f"  FAIL {role_name(assignment['roleId'])} at "
                      f"{assignment['scope']}")
                print("       a workload identity should never hold this")
                problems += 1
                continue
            if (assignment["roleId"],) not in expected_pairs:
                label = "FAIL" if args.strict else "warn"
                print(f"  {label} {role_name(assignment['roleId'])} at "
                      f"{assignment['scope']}")
                print("       held, but not declared by this template — granted "
                      "out of band, or left over from a previous shape")
                if args.strict:
                    problems += 1

    print()
    if problems:
        print(f"MISMATCH: {problems} problem(s) between the template and the "
              f"live permission surface")
        return 1
    print("MATCH: every declared grant exists, and nothing dangerous was found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
