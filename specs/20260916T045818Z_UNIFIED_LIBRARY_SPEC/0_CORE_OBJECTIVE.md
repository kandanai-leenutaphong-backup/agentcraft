# 0. Core Objective

**Overriding objective: deliver a smaller skill surface, one coherent library framework
and effective documentation through fast, concrete, verified results.**
Direction recorded: 2026-09-16. Implementation has not started under this specification.

This chapter takes precedence over every other chapter, proposed architecture, package
layout, execution batch and source plan in this specification. Where a detailed plan adds
work without advancing these results, simplify that plan. Safety, data protection and
explicit execution authority are not waived.

## Six Binding Objectives

### CO-1. Supersede Skill-Owned Implementations

Bring retained reusable functionality, contracts, tests, examples and operational guidance
from `.github/skills` into their canonical library owners. Substantially reduce the content
and number of files under skills. Keep only useful thin discovery/procedure entries;
merge redundant entries and use aliases where needed. Do not move a duplicate into another
runtime tree or hide it in a generated source bundle.

**Target:** zero independently maintained capability runtimes under skills, and at least
50% fewer shipped files and 50% fewer logical content bytes under `.github/skills` against
one frozen pre-migration baseline. These are acceptance targets, not measured results.
Count source, guidance, tests, examples, assets and shipped generated entries in both
inventories; exclude installed environments, dependency caches and unshipped build output
identically. Record exclusions. Removing caches alone does not meet the target. Retained
behavior/tests/notices must have owners; operational data is never a removal candidate.

### CO-2. Make The Unified Interface Easy To Learn And Navigate

Produce effective repository documentation governing the selected library interface:
one entry point, accurate shared conventions, capability references and executable task
examples. Do not create a second knowledge tree inside a website or skill package.

**Target:** every retained public capability has a current reference and at least one
working public-API example; every advertised local documentation link resolves. An
independent reader can reach each agreed common task in at most three navigation steps
and complete its setup, result inspection, failure recovery and cleanup from the docs.
No unverified claim that a future or retired API is currently supported.

### CO-3. Deliver One Framework And One Coherent Standard

All retained runtime libraries adhere to the same applicable F1-F8 standard. Applications,
skills and MCP adapters follow the selected library contracts, not the reverse. Provide
one supported installation/composition path while retaining useful specialized typed APIs.

**Target:** 100% of retained runtime packages have an explicit conformance result for
each applicable standard; zero undocumented deviations, duplicate runtime owners or
legacy-only compatibility engines. A stateless/UI capability can mark an irrelevant
requirement not applicable with a concrete reason; this is not an exemption from shared
meaning. Research-only material is labeled, not counted as implemented framework support.
The selected combined profile installs outside the checkout and completes its real workflow.

### CO-4. Avoid Overengineering

Prefer reuse, deletion, direct native APIs and the smallest implementation that delivers
the selected result. One standard does not require one universal result wrapper, one
base class, one package per skill or all-to-all dependencies.

**Target:** every new runtime abstraction/package has a named immediate consumer and
removes demonstrated duplication or enforces a required shared invariant. Otherwise do
not add it. Proposed core types, profile counts and directory names in later chapters
are not a scaffolding quota. No unused facade, speculative plugin system, duplicate
catalogue or independent retry/tool/lifecycle engine is a completed deliverable.

### CO-5. Bound Every Chapter By A Measurable Result

Each chapter states its objective, completion evidence, scope ceiling and stop condition.
Those fields bind its work; implementation batches inherit the relevant bounds. A chapter
is not permission to explore every adjacent feature or continually enlarge acceptance.

**Target:** every chapter has those four fields. Before a block, name one deliverable,
its owned paths, the cheapest discriminating check and an effort/time bound appropriate
to that block in the existing batch record. Reuse available evidence instead of repeating
the audit. At the bound, report the result or blocker and choose a smaller step; do not
silently expand scope or extend the run. A scope change is explicit, never inferred.

### CO-6. Result First; Engineering Follows The Result

Deliver concrete results fast. Plan only enough to choose the next safe, reversible
working increment. Implement, run, observe and adjust. Do not substitute specifications,
framework infrastructure, exhaustive preparation or repeated reassurance checks for
working capability, removed duplicates and usable documentation.

**Target:** the first implementation block demonstrates one retained capability through
its canonical public library API, removes its selected old runtime and passes its focused
success/refusal check. Subsequent blocks do the same for their scoped outcomes. Build
only the prerequisite core/composition pieces needed by that result; do not complete all
of B00/B01 or a portfolio-wide test/deployment apparatus before a simple useful removal.
Stop adding work once the agreed result and its relevant required gates pass.

## Decision And Completion Rule

Before adding work, ask: **does this directly remove skill duplication, make the unified
interface usable, establish required standard conformance or prove the current result?**
If not, omit it or record a separately scoped follow-up. Existing complexity is not a
requirement; named future folders/types are not a reason to create more complexity.

Tests prove the target contract and adapted user outcome, not old API parity. Preserve
authentication, authorization, integrity, bounded execution, truthful effects and cleanup.
No fast-result claim permits fake data, disabled auth, hidden failures, unauthorized cloud
actions or deletion of user state. A required blocked gate stays blocked; an unrelated
blocker does not stop independently authorized work or restore a duplicate runtime.

Report actual before/after counts and bytes, completed capability/removal outcomes,
documentation navigation results, conformance gaps, tests and remaining blockers. Do not
claim disk/RAM/latency savings from source movement alone. Full migration completion
requires all six objectives, not merely newly named packages or completed planning.

Next: [01. Scope And Decisions](01_SCOPE_AND_DECISIONS.md).