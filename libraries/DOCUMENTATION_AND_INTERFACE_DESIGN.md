# Documentation And Interface Design

> **Superseded for the unified migration:** [final specification](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/README.md).
> Retained as a historical input, not a separate active plan. The final spec's library-first
> decisions, mandatory runtime removal, app-adoption status and verification gates control.

Status: **Proposed design strategy for discussion. No runtime API, content move or
documentation-site implementation is authorized by this document.**
Date: 2026-09-16.

## Decision

Design one discoverable knowledge system and one coherent developer experience, while
keeping specialized capability APIs and their documentation with their existing owners.
Start with Markdown, relative links and a curated index that works directly in GitHub
and VS Code. A rendering site is an optional consumer of those sources, not their owner.

Here, interface design means public framework/SDK contracts, their configuration and
failure/lifetime behavior, and the documentation navigation through which users learn
them. This is not an application visual redesign.

The [framework audit](FRAMEWORK_MIGRATION.md) owns observed capabilities and gaps.
This strategy defines how to explain those capabilities and design their future public
interfaces. Existing [package guidance](README.md), capability contracts and
[deployment runbooks](../deploy/README.md) remain authoritative for current behavior.

## Documentation Principles

- Organize navigation around reader goals, then capabilities; do not expose the source
  directory tree as the only way to find an answer.
- Give each page one job: orientation, first success, guided learning, a task, an
  explanation, reference, troubleshooting, or a design decision.
- State whether material is current, proposed, experimental, compatibility-only or
  historical. A proposed API must not look like runnable supported code.
- Keep one source for each fact. Root project status, package contracts, deployment
  procedures and historical evidence have different owners and should link to each other.
- Separate knowledge from machine outputs, transcripts, fetched reference bodies and
  private data. Synthesize findings with provenance instead of copying whole repositories.
- Prefer stable headings, descriptive relative links, short task titles and explicit
  prerequisites, expected results, failures and cleanup. No site build is needed to read.

## Interface Principles

- Write and test the caller's complete task before selecting a shared facade or base class.
- Standardize configuration, identity/authorization terminology, safe diagnostics,
  budgets, lifecycle and compatibility guarantees where meanings actually match.
- Keep native data/model/UI values and specialized operations. A universal `execute(dict)`
  endpoint does not establish consistency or type safety.
- Setup makes no hidden service calls or grants. Host policy, caller evidence and workload
  credentials remain separate; narrower nested calls cannot widen authority.
- Every meaningful operation documents completion, empty/partial/unknown outcomes,
  cancellation, retries, owned/borrowed resources and how results can be read back.
- Documentation examples and executable contract tests describe the same public surface.
  Optional HTTP, CLI and MCP adapters call that owner rather than implement it again.

## 1. What To Borrow From Microsoft

Observed in the current public Azure Functions sources, not inferred from the whole Azure
documentation repository. Source links and inspection scope are recorded at the end.

| Observed Pattern | Lightweight Adaptation Here | Do Not Copy |
| --- | --- | --- |
| Service-owned article directories | Capability owners maintain their own knowledge and contracts; cross-capability guidance has one framework owner | A giant product hierarchy or one centralized writer for every subject |
| A landing page groups links by reader task and article type | One Markdown knowledge index with Start, Tasks, Concepts, Reference, Troubleshooting and Design/Changes; a capability list supplies a second route to the same pages | Marketing cards or a separate landing-page application |
| `TOC.yml` explicitly orders navigation, independently of directory/file order | A curated Markdown index is the initial TOC. Use descriptive links and intentional order; folder listings are not navigation | Azure's large YAML TOC, publishing pipeline or language-pivot syntax before we need a renderer |
| Overview, quickstart, tutorial, how-to, concepts, samples and reference have different jobs | Adopt the page types below and keep procedural instructions separate from explanations and exhaustive reference | Every page becoming a mixed overview, tutorial, reference and changelog |
| Articles contain title, description, topic and review metadata; some name customer intent | Add a short readable page contract: reader goal, type, status, applicability, owner and verification | Microsoft-specific `ms.*` taxonomy, contributor identities or date changes that imply unperformed verification |
| Overviews link scenarios, detailed concepts and related next steps | Every page has a parent/index route and a small number of genuinely useful next links | Navigation duplicated into every page, dead-end pages or link-only wrapper forests |
| SDK guidance couples package README, docstrings, task docs and tested snippets | Keep exact examples under the capability owner, exercise them through public imports, and link/embed from the same source | Hand-maintained copies of code examples drifting across README, reference and tutorials |

The Azure SDK principles add an important interface constraint: idiomatic language usage,
consistent cross-cutting behavior, approachable setup, diagnosable failures and dependable
compatibility. Consistency within a language takes priority over forcing all languages to
look identical. These are design goals, not evidence this framework already satisfies them.

## 2. Reader And Navigation Model

Primary readers are application developers consuming capabilities. Operators need bounded
setup/diagnostic procedures; maintainers need contracts, ownership and migration decisions.
Coding agents use the same factual sources, with explicit executable entry points and scope.

| Reader Question | Entry Path | Page Must Answer |
| --- | --- | --- |
| What exists and which version/profile should I choose? | Start / capability overview | Supported, experimental and compatibility-only capabilities; dependencies and non-goals |
| How do I get one real result? | Quickstart | Prerequisites, explicit identity/authority, minimal working path, observable result and cleanup |
| How do I complete this particular task? | How-to | Inputs, ordered actions, expected output, likely failure and recovery |
| Why does it work this way? | Concepts | Mental model, invariants, tradeoffs and boundaries; link to procedures instead of repeating them |
| What exactly does this API/configuration accept? | Reference | Public signatures/types, defaults, units, effects, guarantees, exceptions and version applicability |
| Why did this fail? | Troubleshooting | Symptom, discriminating checks, interpretation, safe recovery and verification |
| Why was this choice made or what will change? | Design / migration decisions | Status, alternatives, decision, compatibility impact and evidence; not instructions for an unimplemented API |

Two navigation axes, one set of pages: **intent first**, then **capability**. Examples:
"Read a bounded ADX window", "Handle an incomplete model stream", "Validate an Entra
caller" and "Show a source preview". Display the public API name alongside the task where
useful, but do not require readers to know internal module names to locate a task.

Navigation rules:

- Prefer one or two grouping levels in the initial index. Add depth only for real content.
- Target at most three navigation steps from the index to a common task; test this with
  representative readers. This is a proposed acceptance target, not a measured result.
- Use stable descriptive slugs and headings, not numbered filenames or generic titles such
  as "General", "Miscellaneous" or "More". Historical receipts may retain dated filenames.
- Each current page links to its authority/reference and an appropriate next action.
  References should link back to a working task example.
- Search complements the index; it does not replace ownership or navigation. Plain titles,
  headings and exact API identifiers should work with GitHub search, VS Code and `rg`.
- If a renderer is later used, derive its navigation from the same source. Do not maintain
  independent Markdown and website TOCs that can disagree.

## 3. Repository Structure And Single Ownership

Proposed logical structure, not a request to scaffold all directories or move existing
files now. Add a page only when there is an actual reader question and an owning source.

```text
README.md                         live project state; link to knowledge entry
docs/
  README.md                       short task/capability knowledge index
  getting-started.md               supported profile and first composed result
  concepts/                       cross-capability explanations only
  how-to/                         cross-capability task guides only
  troubleshooting/                cross-capability diagnosis only
libraries/
  README.md                       current package catalogue and installation authority
  FRAMEWORK_MIGRATION.md           observed audit, gaps and migration gates
  DOCUMENTATION_AND_INTERFACE_DESIGN.md
  <capability>/
    README.md                     capability overview, setup and minimal use
    CONTRACT.md                   behavior/guarantee authority, when already used
    USAGE.md                      task examples, when already used
    OPERATIONS.md                 operational gotchas, when already used
    docs/                         split topics only when existing material needs it
    examples/                     executable public-API examples
    tests/                        implementation and example contract checks
deploy/
  README.md                       one authorized operator command sequence
  records/                        dated evidence, not general knowledge articles
```

The tree is a routing model, not a mandatory filename template for every library. Reuse
existing READMEs, usage guides and contracts; a small library can need only its README plus
reference in code. Do not add empty how-to/reference directories to make layouts match.

| Fact Or Content | Single Owner | Other Pages Do |
| --- | --- | --- |
| Current project state and remaining work | [Root README](../README.md) | Summarize only where necessary and link back |
| Current distributions, dependency setup and package workflow | [Library guide](README.md) and package manifests | Link to exact install/profile instructions; do not invent a unified install command |
| Public operations, failure/effect semantics and supported features | The capability's contract and implementation | Explain the relevant subset and link to the full authority |
| Cross-capability terminology, composition and design | This strategy and the [framework audit](FRAMEWORK_MIGRATION.md), then approved focused guides | Reference one decision instead of copying it into every package |
| Provisioning, release, teardown or cloud operation commands | [Deployment owner](../deploy/README.md) and its script | Link to the authorized entry point; never introduce a second command sequence |
| Tested example code | The owning capability's executable example/test | Reference the exact example; a future renderer may include it directly |
| Historical outcomes, hashes and experiments | Existing dated records and capability verification documents | Link with date and scope; do not present an old pass as current verification |
| Acquired public references | Source URLs and provenance; temporary/reference holdings where needed | Write original synthesis and applicability, not mirrored publisher documentation |

Repository Markdown is the source of truth. Any documentation application consumes those
sources and resolves assets/links; it must not fork the knowledge into a second authoring
tree. Selecting or modifying a renderer is separate work. Existing documentation-app work
is intentionally untouched by this strategy.

## 4. Page Contracts

Use these shapes as editorial guidance, not a required file count or a template generator.

| Type | Structure | Completion Check |
| --- | --- | --- |
| Overview | Purpose; when to use/not use; capabilities; mental model; first-use and reference links | Reader can choose the right capability without reading its internals |
| Quickstart | One outcome; prerequisites and cost/authority; setup; complete minimal example; expected result; cleanup; next step | A clean supported environment can reproduce the result without guessing an omitted value |
| Tutorial | Learning goal; staged working example; explanation at each meaningful step; checkpoints; final result | Each step builds on observed output from the previous one; not a dump of API options |
| How-to | Task; assumptions; exact inputs; ordered actions; expected result/read-back; failure/recovery; cleanup | Existing user can complete the task without studying the entire system |
| Concept | Bounded question; explanation/diagram; invariants and tradeoffs; examples; links to tasks/reference | Explains why and when, without duplicating installation or command sequences |
| Reference | Signature/config schema; fields/defaults/units; results/errors; grants/effects; lifecycle; version/compatibility; related example | Accurate, complete lookup for the advertised public surface; unsupported behavior explicit |
| Troubleshooting | Observable symptom; checks that distinguish causes; meaning of each result; safe correction; verification | Does not recommend retries, grants, writes or auth bypasses without justified authority |
| Decision/migration | Proposed/accepted/superseded status; context; alternatives; choice; consequences; old-to-new map; gates | Historical or proposed decisions cannot be mistaken for currently supported behavior |

For new substantive knowledge pages, use a visible lead-in block or compact table:

```text
Type: how-to
Goal: read a bounded result from an already configured source
Status: current | proposed | historical
Applies to: exact capability, API/profile and supported versions
Owner: capability or composition boundary
Verification: command/example and evidence link, or explicitly unverified
```

Do not add unused YAML frontmatter just to resemble Microsoft Learn. If later tooling
consumes metadata, define one portable schema and derive the visible information from it.
Publication status, feature maturity and verification status are separate: a current page
can document an experimental capability or an unverified live scenario.

Writing rules: answer the page's question first; use plain technical language and exact
identifiers; one action per numbered step; explain required choices before the command;
state defaults rather than relying on them invisibly. Use tables for comparisons and
schemas, diagrams for ownership/flow, prose for reasoning. Keep large logs, source dumps
and raw research outside task pages. Split a long page by independent questions, not an
arbitrary line limit; keep short factual reference tables together when that helps lookup.

## 5. Interface Design Strategy

### Design From A Complete Caller Workflow

The interface begins with the user's task, not a universal class hierarchy or a new root
namespace. Sketch the full path: installation, configuration, credential/authorization,
call, result inspection, failure, cancellation and close. Short examples must not hide
necessary setup, extra permissions or unsupported dependency combinations.

For each proposed public capability, write a compact interface card:

| Field | Required Content |
| --- | --- |
| Goal and caller | Task, supported profile and real consumer; what it deliberately does not do |
| Entry point | Import/constructor/function plus any CLI/HTTP/frontend adapter; language-idiomatic form |
| Inputs | Required versus optional, data types, defaults, units, trusted config versus untrusted input |
| Authority | Caller evidence, host authorization, workload identity and operation grants, separately |
| Output/effects | Native/typed result, empty/partial/pending/unknown meaning, persistence/read-back and side effects |
| Failure | Safe codes/categories/actions; exceptions versus values; transport mapping and redaction |
| Lifetime | Construction/description costs, network-call points, concurrency, owning/borrowing, close and cancellation |
| Budget | Deadline scope, attempts/retries, items/bytes/tokens, nested narrowing and unknown accounting |
| Compatibility | Version policy, provider/dependency support, existing consumers and explicit breaking changes |
| Proof | Runnable positive path, matching refusal and cleanup checks; docs/example links |

### Standardize Shared Meaning, Preserve Specialized APIs

| Standardize Across The Framework | Keep Capability-Specific |
| --- | --- |
| Discovery, configuration terminology and supported installation profiles | Data queries, model messages, auth claims, rule observations and UI props |
| Identity injection and host authorization vocabulary | Provider scopes, exact operation grants and auth protocol mechanics |
| Safe diagnostic metadata and effect/unknown semantics | Native payloads and meaningful domain exceptions; terse auth HTTP refusals |
| Lifecycle ownership, explicit sync/async behavior and cancellation rules | Stateless helpers, UI component state and SDK-native resource types |
| Budget units, correlation and retry/verification accounting | Operation-specific bounds and protocols; no fabricated global transaction |
| Public API/version/deprecation policy and conformance evidence | Language conventions: Python and TypeScript should each feel native |

Prefer existing SDK/framework types, serializers, context managers and instrumentation.
Use a common implementation only where multiple consumers actually share its invariant.
Do not introduce a global mutable credential/client, a generic options dictionary that
bypasses validation, automatic plugin imports from config, or a second retry/tool loop.

The [framework audit](FRAMEWORK_MIGRATION.md#5-common-standard-gap-analysis) names current
exceptions. In particular, the raw Responses and bounded-model packages are not a compatible
combined installation today. A new facade cannot conceal that conflict or silently change
conversation IDs, retention, tool authorization or event contracts. Resolve and test the
supported profile before documenting a one-command framework experience.

### One Owner, Several Adapters

Application/domain rules stay behind their owning callable contract. HTTP, CLI, MCP and UI
adapters perform transport-specific validation/translation and call it. They do not recreate
business rules or silently widen its policy. Document which adapters actually exist; do not
advertise a framework CLI or MCP tool based on a proposed wrapper.

For direct Python use, prefer typed configuration and operations with async lifecycle for
I/O, plus explicit sync adapters where required. For TypeScript, use typed props/functions
and validated wire boundaries. Same concepts need not have identical syntax. Frontend
rendering packages do not need Python context objects or mandatory Azure dependencies.

## 6. Design And Documentation Together

Use one short iteration loop per meaningful change:

1. Select a real caller task and its existing owner from the capability audit.
2. Write the task page outline and interface card, marking new syntax as proposed.
3. Check existing native APIs and dependency compatibility before inventing a wrapper.
4. Write an executable example through public imports and a matching refusal/cleanup check.
5. Implement the smallest approved change and run that check immediately.
6. Update the owning contract, example and navigation together; do not copy them elsewhere.
7. Operate the affected consumer workflow and retain scoped evidence before retiring old APIs.

Repeated awkward setup in an honest example is evidence to reconsider the API, not a reason
to omit setup from documentation. Conversely, a task guide should not enumerate every option;
it links to reference. This is the practical connection between documentation design and
interface design.

Examples begin with small single-operation cases; composed tutorials then join those proven
pieces. Synthetic/offline examples are labeled and cannot receive live acceptance credit.
Live read, model, mutation and deployment examples require their own explicit prerequisites
and authority. Do not execute a privileged bootstrap just to validate documentation.

## 7. Lightweight Rollout

This increment authors the strategy and links it from existing design/portfolio entry points.
It does not scaffold the proposed tree, migrate existing content, change public APIs or
modify the documentation application.

| Next Increment | Deliverable | Gate |
| --- | --- | --- |
| Curate the knowledge entry | One short index linking current package guides, contracts, operations and design records by intent/capability; classify stale/proposed material | Every advertised route resolves to an appropriate current page or an explicit status; no copied contracts |
| Pilot one task | A bounded existing-data read quickstart/how-to, one relevant concept page and links to exact reference; reuse current public APIs | Clean supported environment, known expected result, meaningful failure and close; reader needs no unwritten setup |
| Agree common API conventions | Interface cards for data and model composition plus the shared F1-F8 rules in the framework audit | Resolve dependency, authority, result and lifecycle decisions before root SDK/facade implementation |
| Align the remaining capabilities | Incremental page/API consistency changes by owner; relocate only when the existing location is genuinely misleading | Narrow checks and affected consumer workflow after each block; explicit compatibility/deprecation map |
| Optional publishing | Render repository sources only if a site materially improves navigation/search | No forked content; links/assets resolve, keyboard and mobile reading work, source remains usable without the site |

Start with the existing read-only data workflow because its behavior and consumer checks
already exist. Model composition follows a compatible-profile decision; it must not be
documented as ready merely because a proposed example reads well.

## 8. Verification And Maintenance

- Documentation-only edits: review claims against the owning source, check local links,
  headings/status and navigation. Check external sources when their claims are load-bearing.
- Examples or commands: run the smallest applicable test in the stated supported environment;
  identify simulated results and prerequisites. Never relabel a skipped/blocked scenario a pass.
- Interface changes: public import/type/serialization and compatibility checks, positive plus
  matching refusal, cancellation and resource cleanup, then the real affected workflow.
- Existing Perth/graph/MITRE migration checks remain available via the
  [local runbook](../template_apps/investigation_app/deploy/README.md); this strategy runs no
  cloud calls or model inference and grants none.
- If a docs renderer is later changed, verify real navigation, search, copyable code, diagrams,
  long tables, keyboard access and mobile geometry; source-file validity alone is insufficient.
- Update docs in the same change that alters the behavior they describe. The capability owner
  reviews semantics; a separate large documentation approval hierarchy is unnecessary.
- Keep current guides apart from historical evidence and proposals. Superseded decisions link
  to their replacement; preserve provenance/rights. Moving content requires redirect/link
  reconciliation, not silent removal.

Success means a reader can find, use, diagnose and compose a capability through one coherent
path, with accurate references and observable outcomes. Do not measure success by page count,
framework wrapper count or a visually polished site with incomplete knowledge underneath.

## Sources And Inspection Scope

Public material checked 2026-09-16. This is original synthesis, not copied Microsoft content
or a claim to have audited every Azure article. Raw references were held outside the repo;
the provenance catalogue verified ten acquired artifacts with no missing/changed files.
The initial obsolete Search paths returned 404 and were not used as evidence. The current
Functions navigation filename is case-sensitive `TOC.yml`.

| Source | What It Supports |
| --- | --- |
| [Azure documentation repository README](https://github.com/MicrosoftDocs/azure-docs/blob/main/README.md) | Docs-as-code contribution entry and separate license/notice authorities |
| [Azure Functions landing source](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/index.yml) | Service landing metadata and task/article-type link groups |
| [Azure Functions TOC](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/TOC.yml) | Curated Overview, Quickstarts, Tutorials, Concepts, How-to, Migration and Reference navigation |
| [Azure Functions overview](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/functions-overview.md) | Article metadata, reader intent, scenario framing and related content |
| [Azure Functions getting started](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-functions/functions-get-started.md) | Routing by task/tool/language; not a pattern to copy its publishing-specific pivots |
| [Azure SDK design principles](https://azure.github.io/azure-sdk/general_introduction.html#design-principles) | Language-native, consistent, approachable, diagnosable and dependable developer experience |
| [Azure SDK documentation guidance](https://azure.github.io/azure-sdk/general_documentation.html) | Package README, API docs/docstrings, common-operation examples and tested snippets |

These external practices are inspiration. Repository scope, existing public contracts,
security requirements and explicit user decisions remain controlling here.