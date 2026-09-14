---
name: protocol-restructure
description: "Use when a working codebase has legacy directories, duplicate implementations or an unclear shape and must be consolidated without breaking it: salvage before deletion, a measured target architecture, reversible batches, extensibility proved on one real source. Requires authorization; moves and deletes files."
metadata:
  protocol: protocol-restructure
---

# Protocol: restructure

Rearchitecting a working system is the easiest way to break one. This protocol makes the change
measurable instead of hopeful: the target shape is declared before anything moves, the gap is
counted, and the count goes to zero.

Composes with [protocol-garbage-collect](../protocol-garbage-collect/SKILL.md) for proving death,
[architecture-placement](../../skills/architecture-placement/SKILL.md) for contested placement, and
[capability-first modularization](../protocol-capability-modularization/SKILL.md) for functional cataloguing and reuse.
The [architecture principles](../../instructions/architecture-principles.instructions.md) govern dependencies.

## When it earns its cost

A named area that is understood, runs today, and is about to receive work its current shape would
make expensive — a new data source, a second adapter, a second consumer. Restructure to absorb a
specific pressure, never to satisfy taste.

Skip it when the pressure is hypothetical, when nothing runs green today, or when the area is one
module under one owner. Moving files is not progress.

## Authorization and reversibility

Moving and deleting needs explicit user authorization and a restorable baseline. Record the
current revision and preserve unrelated edits; never commit, stage, stash, reset, or revert
someone else's work implicitly. Existing approval covers the named set, not a set that grows later.

## Steps

### 1. Baseline the green

Record the exact commands that pass **now** — build, typecheck, tests, the acceptance journey — with
their output and duration. Without this, "did I break it" is unanswerable for the rest of the
protocol. If nothing passes now, stop: fix that first, as its own work.

### 2. Salvage before deleting

One recorded verdict per doomed file or directory:

```
| Path | Verdict | Destination |
```

`moved` with its new home, `superseded-by` with the replacement that already does it better,
`captured` with the notebook note carrying its durable knowledge, or `discarded` with the reason.
**No file dies unaccounted.** The value in a legacy directory is usually one function, one constant
table, or one hard-won workaround; losing it is the expensive part of a cleanup.

Salvage now; delete in step 7. Keeping the doomed source in the tree until the new shape is green is
what makes recovery cheap.

### 3. Diagnose the crossed wires

Name each defect with evidence at path and line, not adjectives:

| Smell | How it is proven |
| --- | --- |
| Dependency cycle | `arch.py` observed cycle, or the import chain |
| Two implementations of one capability | both paths, and the caller split between them |
| God module | fan-in from `arch.py --hotspots`; a module most of the system imports |
| Configuration read deep | environment access below the composition root |
| Reaching past a surface | an import of another boundary's internals |
| Registered but never invoked | present in a registry with no call path |
| Branching on caller identity | a callee that behaves differently per caller |

Report a smell you will not fix as a residual rather than fixing it silently.

### 4. Declare the target before moving anything

Describe the current graph first: boundaries, owned paths, allowed edges and public surfaces.
Keep the target and its remaining migration steps distinct. Where `architecture.json` exists,
update it to describe each landed batch, not an unimplemented wish. Run the existing graph checker:

```bash
python3 .github/tools/arch.py
```

The observed violations and unmigrated consumers form the work plan. Keep structural declarations
reviewable separately from content churn. The checker proves supported imports, not behavioral
equivalence; record unknown dynamic edges and use the workflow acceptance checks too.

### 5. Move in reversible batches

Each batch is one coherent boundary. Keep mechanical relocation separate from content fixes where
that improves review. Run the step-1 commands after every batch. A red batch stops expansion: repair
the local defect or undo only that batch's own changes when safe. Never mix a behavior change into
a move, and never discard unrelated work to restore a green baseline.

### 6. Connect one, if the pressure was a new source

"Modular" stays unfalsifiable until something new goes in. Where the restructure was done to absorb
a new data source, adapter, or provider, connecting the first real instance is the cheapest proof
the seam exists. Where the pressure was something else, say so and skip this step.

**Connected is not consumed.** Connecting a source means reachable, proven against the real thing,
documented, and findable later. It does not mean a feature uses it. The deliverable is an available
option. Forcing the new source through the product couples an unproven dependency to shipped
behaviour and turns housekeeping into a feature change nobody asked for.

Done, for one connection:

| Deliverable | Test of it |
| --- | --- |
| Adapter at the declared extension point | nothing outside that point changed |
| Proof against the real source | a test that fetched real data, with its output recorded |
| Credential path | how it authenticates, by identity or vault reference, never a stored secret |
| Shape | the fields it returns, and which are guaranteed |
| Quirks | rate limits, pagination, freshness, the failure it returns when unavailable |
| Findability | registered where a future reader will look, and answerable by `find.py` |

Then record what the change touched:

- every file created or changed;
- whether any lie outside the declared extension point.

A change confined to the extension point proves the seam. A change that also edits the core, the
composition root and three call sites proves the seam is not there yet, whatever the folder names
suggest.

An unused connection still costs something: without upkeep it rots into a broken adapter that looks
available. Give it the cheapest liveness check that would actually fail and an owning boundary, or
record the source as documented-but-not-connected with what it would take.

### 7. Delete, then reconcile

Only now, and only the set authorized in step 2. Then close the surfaces describing the system, in
the same change:

- `deploy/deploy.sh` and `deploy/README.md` if any path, name or step moved;
- `ARCHITECTURE_OVERVIEW.md` for the new boundaries and dependency direction;
- the register of connected sources, so what is available is answerable by reading rather than by
  investigation;
- the owning `README.md` and `CONTRACT.md` for each boundary that changed shape;
- the project `README.md` for what now exists and what is left.

A restructure leaving the documentation describing the old shape has moved the problem into the
docs.

## Gates

- Step 1 evidence exists, or the protocol does not start.
- No file is deleted without a step-2 verdict.
- The step-1 commands pass after every batch, not only at the end.
- `arch.py` violations are zero, or each survivor is a named, accepted residual.
- A connected source, where one was connected, is documented, tested against the real thing, and
  findable — and is **not** wired into a feature to demonstrate that it works.

## Records

- The procedure, if refined: `type: method`.
- A resulting rule that should bind future work: `type: principle`.
- The new topology, once green: `type: architecture`, with boundaries and their edges.
- Each connected source: `type: architecture`, carrying adapter path, shape, credential path and
  quirks, so "can we get X" is answered by a search rather than an investigation.
- The run itself, its salvage table, burn-down and residuals: its `work-issue` note.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
