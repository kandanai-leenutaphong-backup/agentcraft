# 05. Documentation And Developer Experience

The library contract is designed for intended tasks and coherent shared semantics, not
legacy callers. Documentation makes that target usable and migration obligations explicit.
One knowledge source can serve developers, operators, maintainers and coding agents.

## Bounded Objective

- **Objective:** provide one effective path to learn, use and diagnose the unified interface,
   under [0. Core Objective](0_CORE_OBJECTIVE.md).
- **Done when:** every retained capability links to current reference and a working public
   example, all advertised local links resolve, and an independent reader reaches each
   agreed common task in at most three navigation steps and completes its documented flow.
- **Scope ceiling:** curate and correct existing knowledge; add only pages answering a real
   question. No site redesign, content mirror, duplicate example tree or page-count target.
- **Stop condition:** the selected task is discoverable, runnable and accurately documented.
   Do not continue a documentation sweep or visual polish beyond the agreed task set.

## Knowledge Architecture

Borrow Microsoft Azure's typed articles, task-oriented navigation, service/capability
ownership and related-content links, not its scale or publishing infrastructure.
Use Markdown/relative links readable in GitHub and VS Code. No required site build,
marketing landing page, whole-repository reference mirror or duplicated docs application.

Target navigation: Start, Tasks, Concepts, Reference, Troubleshooting and Design/Changes,
with a capability index as a second route to the same content. Prefer shallow grouping
and at most three navigation steps to common tasks; measure that with real readers before
claiming the target met. Search complements the index and exact API names, not replaces it.

| Content | Authoritative Owner |
| --- | --- |
| Project state/current limitations | Root `README.md` |
| Knowledge entry and cross-capability guides | `docs/README.md`, actual start/concept/how-to/troubleshooting pages as needed |
| Package catalogue/install/profile commands | `libraries/README.md`, canonical catalogue and package metadata |
| Capability implementation guarantees | Library contract/reference/docstrings and tested examples |
| Operational findings | Same library's guidance; old gotchas labeled for retired/current contracts |
| Exact deployment target, commands and receipts | Owning `deploy/` entry point/runbook and versioned records |
| Framework design and migration decisions | This spec sequence; four source plans are superseded inputs |
| Historical experiments/verification | Existing immutable receipts and capability evidence with exact date/artifact scope |
| Discoverability | Generated skill/catalogue views of library-owned guidance, not another manual |

Use existing READMEs/CONTRACT/USAGE/OPERATIONS files where suitable. Do not create empty
directories or a complete document set for each tiny library. Add/split a page when it
answers an independent reader question, not to meet a page/line quota. Stable descriptive
slugs/headings apply to the knowledge base; numeric filenames apply only to this finite
ordered specification. A future renderer consumes the same sources/navigation and assets.

## Page Contracts

| Type | Required Content | Acceptance |
| --- | --- | --- |
| Overview | Purpose, when/not when, outcomes, mental model, first-use and reference links | Reader can select the capability without its internals |
| Quickstart | One result, prerequisites/authority/cost, setup, complete example, expected output, cleanup | Clean supported environment succeeds without invented values or hidden setup |
| Tutorial | Learning goal, staged working example, explanations, checkpoints, final outcome | Each step uses actual prior output, not a dump of options |
| How-to | Concrete task, assumptions, inputs, ordered actions, read-back, likely failure/recovery | User completes a task without learning unrelated capabilities |
| Concept | Bounded question, explanation/diagram, invariants/tradeoffs and task links | Explains why/when without duplicating operator commands |
| Reference | Signatures/schema, fields/defaults/units, result/error/effect meanings, grants/lifetime, versions | Precise lookup; unsupported guarantees and native caveats explicit |
| Troubleshooting | Observable symptom, discriminating checks, interpretations, safe correction, recheck | No blind retry, unsupported privilege change or auth bypass |
| Decision/migration | Status, context, alternatives, choice, consequences, old-to-new map and evidence | Proposed/historical behavior cannot be mistaken for currently executable support |

New substantive pages carry readable type, goal, status, applicability, owner and verification
information. Publication status, maturity and proof are different: a current page may describe
an experimental operation whose live permission remains unverified. Add machine metadata only
when tooling consumes a single defined schema; do not mimic Microsoft `ms.*` fields blindly.

Answer the reader's question first. Use exact public identifiers, explicit defaults and one
action per numbered step. Compare with tables, explain dependencies/flows with diagrams,
and link to the owning contract. Keep raw logs, fetched reference bodies, transcripts and
private records outside learning/task pages. Every current page has a parent route and
useful next action; reference links back to a runnable public example.

## Interface Card

For each selected public feature, maintain this compact contract beside the example/test:

| Field | Required Decision |
| --- | --- |
| Outcome and caller | Intended task, supported profile and meaningful non-goals |
| Entry point | Public imports/constructor/typed operation and actual CLI/HTTP/MCP/frontend adapter |
| Inputs | Required/optional types, defaults/units, trusted binding versus request values |
| Authority | Caller evidence, host authorization, workload identity and operation grants separately |
| Output/effects | Typed/native values, empty/partial/unknown semantics, state owner and read-back |
| Failure | Safe codes/categories/actions; exception/value and protocol mapping; redaction |
| Lifetime | Setup/network points, sync/async behavior, borrowing/ownership, cancellation and close |
| Budget | Wait/deadline/retry/accounting scope, units and nested narrowing |
| Compatibility | Selected v1 contract/dependencies; retired old surface and app migration instructions |
| Proof | Executable success, matching refusal/integrity/cleanup cases and evidence class |

Caller-first means a usable intended API, not preservation-first. Uncomfortable setup in
an honest example is design evidence; never shorten it by omitting authorization, cleanup
or integrity checks. Native SDKs/frameworks own native semantics. Shared cross-cutting rules
must remove actual repeated logic, not add empty abstractions or a wrapper around each function.

## Tested Examples And Native Reference

Keep example code in the capability source/test owner, callable through public imports.
Use atomic examples for individual operations; composed tutorials import those functions
and pass actual results between them. A future docs renderer can include their source,
but there must not be handwritten executable copies in README, skills and website trees.

Label synthetic/offline examples and prerequisites. Do not execute live bootstrap/model
examples as docs validation. Default installation/description performs no cloud or model
request. Current install guides must not advertise nonexistent root distributions or
incompatible profile combinations before their artifacts pass.

## Independent Usability Acceptance

An independent consumer receives only the public guide, selected artifacts, non-secret
approved configuration and stated prerequisites. No private source knowledge, reference
app internals, assumed sibling checkout or mandatory raw SDK event parsing for basic tasks.

Verify initial setup, first result, repeated calls, meaningful failure/recovery and close.
For a promised provider swap, retain caller/tools/event handling and change only the
documented binding plus any required fresh session; do not promise interchangeability
between genuinely different capabilities or provider semantics.

Record lookups, clarification requests, explicit caller decisions, glue code including
setup, failed attempts and measured time to a correct result when claiming lower effort.
Use the same task and safeguards as the native SDK comparison. Unknown measurements remain
unknown. If the wrapper adds no useful rule or measurable usability gain, simplify it or
publish a recipe, not another permanent runtime.

## Rollout And Maintenance

1. Curate the knowledge entry using current guides/contracts and target migration notices.
2. Author the first data/model task examples against selected target public APIs.
3. Use the interface cards and conformance cases to refine implementation, not to resurrect
   old interfaces for a legacy app test.
4. Update package contract/example/navigation/discovery in the same delivered batch.
5. After each affected app block, operate the real target workflow. Rendered UI changes
   need actual controls/read-back, screenshots, keyboard and desktop/mobile geometry.
6. If a docs site is later selected, verify navigation/search/code copy/diagrams/tables/assets
   and responsive reading; source validity alone does not prove its usability.

Root README updates only when project-state claims change. Historical records keep their
original scope and hashes. Retired interfaces link to the replacement/migration notice;
their documentation does not imply continued runtime support. No mandatory review board,
fixed team count or extra documentation hierarchy is introduced.

## External Inspiration

References were inspected by the source design work on 2026-09-16; not fetched again by
this consolidation. Original synthesis only, no Microsoft article bodies copied here.

- [Azure Functions landing page](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/index.yml): task/article-type groups.
- [Azure Functions TOC](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/TOC.yml): curated intent/capability navigation.
- [Azure Functions overview](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/functions-overview.md): metadata, reader intent and next steps.
- [Azure SDK principles](https://azure.github.io/azure-sdk/general_introduction.html#design-principles): idiomatic, consistent, approachable, diagnosable and dependable interfaces.
- [Azure SDK documentation](https://azure.github.io/azure-sdk/general_documentation.html): README/reference/docstrings and tested common-operation snippets.

Dependability applies to the selected target contract. It is not an obligation to preserve
every abandoned experimental interface through this explicitly breaking migration.

Next: [06. Migration Execution Plan](06_MIGRATION_EXECUTION_PLAN.md).