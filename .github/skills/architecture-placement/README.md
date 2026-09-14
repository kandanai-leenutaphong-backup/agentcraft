# Architecture placement

Advisory ownership and dependency analysis, with a bundled standard-library checker.
The skill returns a placement packet; it does not implement the proposed change or authorize it.

## Use and verification

Resolve `SKILL_ROOT` to this installed directory. Python 3.10+ is required.

```bash
python3 "$SKILL_ROOT/tests/selftest.py"
python3 "$SKILL_ROOT/scripts/arch.py" --root /path/to/project
```

The checker reads the target's `architecture.json` and Python/JavaScript/TypeScript imports.
It reports overlapping ownership, undeclared edges, cycles and private-surface imports. Missing
or empty boundaries are advisory. Unresolved imports and unowned sources are reported, not proven.
It performs no writes to the target repository and requires no notebook, sibling skill or agent.

`tests/fitness.py --root /path/to/project` preserves the optional legacy harness audit. It requires
an actual legacy installation and is not this portable skill's acceptance gate.

## Dependency and provenance

Workflow and legacy fitness source were copied from `core/skills/dep/architecture-placement`.
`scripts/arch.py` was bundled from `core/tools/arch.py`; its CLI now requires an explicit target.
The bundled copy is the distribution source, not an import from the harness tool directory.
Review future refreshes explicitly. The parked originals remain unchanged.

Selftests create temporary repositories and verify a permitted graph and matching negative
cases. They do not establish architectural correctness of a consuming project. No runtime state,
MCP server or installation hook is introduced.

## Removal

Remove the skill through the plugin client or discard an explicitly vendored copy. Target
repositories, manifests and notebook records remain unchanged.