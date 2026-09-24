# Foundry Official Integration And Redundancy Reduction

Status: F08 live integration verified 2026-09-22; F09 authoritative publication pending.
Original audit and acceptance requirements below remain intact. Worker evidence:
[F08 settlement](../deploy/remediation-evidence/20260922T174900Z-f08/20260922T191008048851Z-settlement-live.json).
Owner: AgentCraft overseer; implementation assigned through `agentcraft-orchestrator`.
Outcome: use supported Microsoft SDK operations wherever they remove custom mechanics
without removing experiment correctness, security, provenance or recovery guarantees.

## 1. Execution Contract

An agent can execute this document without inventing a replacement architecture. Read
sections 1-5, execute required tasks in dependency order, resolve each conditional task
using its stated gate, then complete section 8. A conditional task may finish `retained`
with measured evidence; an untested mandatory replacement cannot finish `passed`.

This request authorizes the audit and this specification. **Do not execute the migration
merely because this file exists.** On an instruction to execute it, bind current source,
interpreter and mutation authority in F00. Reuse still-applicable user authority; do not
repeatedly ask for already granted actions. Missing authority, not routine technical
choices, blocks the affected phase. No new optimization-quality campaign is needed.

### Scope

| Alias | Owning root | Role |
| --- | --- | --- |
| H | [hosted testbed](../testbeds/foundry-hosted-agents/README.md) | Configuration, custom tools, protected hosting and redeployment |
| E | [evaluation testbed](../testbeds/foundry-agent-evaluation/README.md) | Dataset upload, Foundry evaluation, independent execution oracle |
| O | [optimization testbed](../testbeds/foundry-agent%20optimization/README.md) | Native optimization, candidate configuration, classification and metric export |

Preserve O's literal space in every command. Working directory is repository root.
Runtime/package owners remain [llm_interface](../libraries/llm-interface/CONTRACT.md),
[modular-agents](../libraries/modular-agents/CONTRACT.md), and the official SDKs.
The declared root architecture overview was absent; the current
[documentation overview](../docs/README.md) and those contracts supplied routing.
Do not manufacture a new architecture manifest to pass this migration.

### Invariants

- Historical records, images, source archives, dataset splits, downloaded data and
  reported metrics remain byte-identical. New evaluator behavior gets a new version
  and comparison identity, never a rewritten score or changed old constitution pin.
- Freeze pre-change source including untracked files before editing. Do not discard
  user changes. Update active runbooks, not command strings in historical evidence.
- Preserve explicit tenant/subscription/cloud, least privilege, verified TLS, gateway
  authentication, caller ownership, immutable image/config identity and anonymous refusal.
- Keep the accepted tool-proof deployment and Iris deployment available. Use separate
  migration canaries unless a protected same-agent update is explicitly selected.
- No held-out labels in candidate tools, images, logs or uploads. Existing holdout is
  already used; never rerun it to certify SDK transport parity or tune a repair.
- A timeout is not proof of failure. Preserve request/operation/response IDs and reconcile
  accepted or unknown writes before retrying. Never repeat inference to recover output.
- Official SDK constructors/serialization are not strict validation, authorization,
  idempotency or archival. A smaller implementation must still pass negative tests.
- Do not dispatch an overseer, directly or indirectly. One writer per path/resource.
  No new framework, general SDK facade, alternate model loop or testbed-to-testbed runtime import.
- Use `uv` for **all** dependency additions, removals, resolution, builds, installation
  and package inventory. No bare pip, `python -m pip`, Poetry, Pipenv or fallback.
  No environment creation/activation, including implicit environments from `uv run`,
  `uv sync`, build isolation or `uv tool` installation. See F01.

### Machine-Readable Work Order

Task sections below define edits, tests and completion; this graph defines order.
`conditional` means evaluate the gate and record `implemented`, `retained`, `deferred`
or `blocked` with evidence, not silently skip. Conditions cannot weaken required tasks.

```json
{
  "schema_version": 1,
  "id": "foundry-official-integration-20260922",
   "status": "f08_verified_f09_publication_pending",
  "working_directory": "/home/hanchoong/agentcraft",
  "roots": {
    "H": "testbeds/foundry-hosted-agents",
    "E": "testbeds/foundry-agent-evaluation",
    "O": "testbeds/foundry-agent optimization"
  },
  "package_manager": "uv",
  "create_environment": false,
  "tasks": [
    {"id": "F00", "depends_on": [], "gate": "required"},
    {"id": "F01", "depends_on": ["F00"], "gate": "required"},
    {"id": "F02", "depends_on": ["F01"], "gate": "required"},
    {"id": "F03", "depends_on": ["F02"], "gate": "required"},
    {"id": "F04", "depends_on": ["F03"], "gate": "required"},
    {"id": "F05", "depends_on": ["F04"], "gate": "required"},
    {"id": "F06", "depends_on": ["F05"], "gate": "required"},
    {"id": "C01", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C02", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C03", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C04", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C05", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C06", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C07", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C08", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C09", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "C10", "depends_on": ["F06"], "gate": "conditional"},
    {"id": "F07", "depends_on": ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10"], "gate": "required"},
    {"id": "F08", "depends_on": ["F07"], "gate": "required"},
    {"id": "F09", "depends_on": ["F08"], "gate": "required"}
  ]
}
```

At execution create one append-only progress record through the existing evidence owner,
outside frozen comparison files. Each task returns: ID/status; before/after source and
dependency identities; chosen public API/version; removed functions/callers; tests and
commands; external effects and operation IDs; exceptions; evidence paths/digests; next
task. Use the process recorder for authoritative AgentCraft publication, not a new
tracking service. Worker primary receipts are not a substitute for overseer publication.

## 2. Audit Baseline And Coverage

Source/SDK inspection and official documentation establish the opportunities below.
Migration and live equivalence are **not verified** by this audit. Recheck mutable
source and installed signatures in F00. References are anchors, not patch line numbers.

| Area | Reviewed implementation and observations |
| --- | --- |
| H runtime | [main.py](../testbeds/foundry-hosted-agents/main.py), [composition.py](../testbeds/foundry-hosted-agents/composition.py), [proof_tools.py](../testbeds/foundry-hosted-agents/proof_tools.py); already official MAF tool execution and Responses host |
| H lifecycle | Entire [experiment.py](../testbeds/foundry-hosted-agents/deploy/experiment.py), [compatibility.py](../testbeds/foundry-hosted-agents/deploy/compatibility.py), shell entrypoint, Dockerfile, requirements, configuration, tests and runbooks |
| E lifecycle | Entire [experiment.py](../testbeds/foundry-agent-evaluation/deploy/experiment.py), tests, entrypoint and runbooks; explicit public Projects/Blob stages, OpenAI Evals |
| O lifecycle | Entire [campaign.py](../testbeds/foundry-agent%20optimization/deploy/campaign.py), [live.py](../testbeds/foundry-agent%20optimization/deploy/live.py), [prepare.py](../testbeds/foundry-agent%20optimization/deploy/prepare.py), [hosting.py](../testbeds/foundry-agent%20optimization/deploy/hosting.py), [evaluator.py](../testbeds/foundry-agent%20optimization/evaluator.py), runtime/composition, native configuration, manifests, tests and runbooks |
| Dependencies | Both active Dockerfiles use pip; H install and O install/repair actions also invoke pip. H hosting requirement is unpinned. Library pyprojects already own canonical dependencies; do not fork those declarations |
| History | Selected existing receipts and candidate metadata compared, not every historical payload re-audited. No raw holdout labels opened. Old receipts remain authoritative for what ran then |

Observed interpreter: `/usr/bin/python3`, Python 3.12.3. `uv` 0.9.30 matches
[workspace requirement](../libraries/pyproject.toml). Observed distributions:

| Distribution | Installed version |
| --- | --- |
| azure-ai-projects | 2.6.1 |
| openai | 3.13.0 |
| azure-ai-agentserver-core / azure-ai-agentserver-responses | 2.1.0 / 2.1.0 |
| azure-ai-agentserver-optimization | 1.0.0b1 |
| agent-framework-core / agent-framework-foundry / agent-framework-openai | 1.18.0 / 1.13.0 / 1.14.3 |
| azure-identity / azure-core / azure-storage-blob | 1.26.0b2 / 1.39.0 / 12.26.0 |

These are discovery facts, not a resolved lock or fresh deployed-image inventory.
Legacy `agent-framework==1.0.0rc4` and `azure-ai-agentserver-agentframework==1.0.0b17`
have incompatible requirements; importing the legacy hosting adapter failed. Modern
`agent_framework_foundry_hosting` and ACR Tasks SDK were absent. Do not install a legacy
adapter or downgrade core packages to make examples import.

Reproduced audit probes, not live failures:

- Correct nested `item.sample.output_text` receives zero from O's grader. `sample=None`
  raises even when `item.response` exists because nested defaults evaluate eagerly.
- E's text extractor silently chooses among conflicting output representations.
  With an isolated passing oracle, collection accepts error-status rows, wrong criterion
  names and boolean/nonfinite scores; strict JSON persistence later rejects NaN.
- Instructions-only configuration rejects inline skills but not `skills_dir` alone.
- SDK job results and retained REST listing match all three candidates on ID, name,
  average score/tokens and evaluation/run IDs. Extra listing fields are not equivalent.
- Current hosted proof call checks a version but lacks the explicit version selector
  on submission. A later identity refusal does not undo execution on the wrong version.

No claim that those input-shape probes invalidate historical flat-format evaluations.
No bespoke model/tool loop or replacement optimizer search engine was found.

## 3. Required Tasks

### F00 - Pin Source, Authority And Environment

Inputs: this spec, active worktree, three testbed runbooks, owning library contracts,
current deployment target files and existing immutable receipts.

1. Inventory active code, imports, CLI actions, dependency commands, duplicate helpers and
   current callers with `rg`. Exclude evidence archives, installed packages and raw data
   from code-removal counts. Record missing architecture overview without blocking local work.
2. Preserve a secret-free allowlisted source snapshot and hash inventory of existing
   evidence; retain dirty diff and untracked source. A Git commit alone is insufficient.
3. Read interpreter path/version, public SDK signatures and import origins; run
   `uv --version`, `uv pip list --python "$PYTHON"` and `uv pip check --python "$PYTHON"`.
   Classify existing conflicts instead of fixing unrelated packages. No secret env dump.
4. Bind `PYTHON` to an existing interpreter and verify writable installation target before
   package mutation. Resolve current authority for code, package changes and live canaries.
5. Run the scoped offline commands in section 6 and retain baseline failures. Do not run
   old upload, optimize, holdout or dependency-repair actions during preflight.

Exit: source recovery bytes verified; current SDK facts and before counts recorded;
required commands/targets resolved. Unknown source or unresolved mutation blocks affected work.

### F01 - uv-Only Reproducible Dependencies

Files: H `deploy/experiment.py::install`, H/O Dockerfiles and requirements; O
`deploy/live.py::install_loader`, `restore_sdk`; relevant H/E/O active runbooks and build
context allowlists. Canonical library manifests remain the source of their dependencies.
Sources: U01-U03, D01, D06.

1. Replace every active pip install/freeze path with `uv`. Retire consumed SDK repair
   actions after caller migration (F06); do not retain a pip escape hatch. Historical
   command evidence remains untouched and explicitly labeled historical.
2. Keep requirements-based testbeds requirements-based unless a project manifest removes
   actual duplication. Add reviewed, transitive uv-generated locks for host/client and
   runtime profiles. Include exact loader/Projects/MAF compatibility and native build tools.
   No blanket upgrade; resolve against owning library bounds, including preview versions.
3. Use `uv pip compile --python "$PYTHON" --no-python-downloads --no-build-isolation ...`
   for requirements locks. For an existing pyproject owner use `uv add --no-sync`,
   `uv remove --no-sync` and `uv lock` with downloads/build isolation disabled. Do not
   introduce newer uv options merely because floating documentation contains them.
4. Install only through `uv pip install --python "$PYTHON" --no-python-downloads
   --no-build-isolation --require-hashes -r "$LOCK"` after lock/artifact review.
   Bind `$LOCK` in the owning script; no unresolved placeholder is an executable action.
   If local source requirements cannot be hash-locked, build source-pinned wheels with
   `uv build --wheel --python "$PYTHON" --no-build-isolation`, retain wheel hashes and
   a verified wheelhouse, then lock/install that exact wheel set. Resolve workspace path
   sources through their owner; never accidentally download a namesake local package.
5. Build requirements must already exist or be separately locked and installed through
   uv into the approved existing interpreter. No temporary isolated build environment.
   Do not use `--no-deps` to hide incompatibility. A wheels-only install is acceptable
   only with complete pinned dependency closure and a subsequent compatibility check.
6. For nonwritable system Python, stop before OS modification. An explicitly approved
   existing user-site target may use `--target` after containment/import-order checks;
   never create an environment, assume pip `--user` semantics, invoke sudo, or silently
   use `--break-system-packages`. Exact synchronization/uninstallation of a shared
   environment requires its own scoped removal decision and recovery inventory.
7. Container builds copy a verified digest-pinned official uv binary and use the existing
   image interpreter, for example `/usr/local/bin/python`. Pin Python/base-image identity,
   locks and wheelhouse in the source archive; use `uv pip` with explicit interpreter.
   No remote unpinned resolution, `uv sync`, new venv, or raw shell installer. Record
   `uv pip freeze --python ...`, distribution locations and compatibility smoke in image.

Tests: command-vector test rejects pip fallbacks, implicit environment creation and
unrelated upgrades; locks reproduce; actual import origins match selected artifacts;
all scoped tests pass. Use dry-run resolution before installation. Existing incompatible
legacy packages are removed only after confirming callers and exact removal scope.

Exit: zero active non-uv package mutations; no new environment; lock and image build
inputs recoverable. No dependency changes are performed just to author this specification.

### F02 - Correct Grader Mapping And Configuration Guards

Files: O [EXACT_CODE and evaluator registration](../testbeds/foundry-agent%20optimization/deploy/live.py#L20),
[apply_optimization](../testbeds/foundry-agent%20optimization/composition.py#L34), existing
`tests/test_live.py`. Sources: D04-D06, D08-D09.

1. Replace eager fallback expressions with a small explicit extraction routine in the
   registered code. Support observed `item.response`, literal `item["sample.output_text"]`,
   documented `item["sample"]["output_text"]`, and top-level `sample.output_text` only
   when shape-valid. If more than one is supplied, require agreement; no silent priority.
2. Distinguish mapping/data errors from wrong agent predictions. Missing ground truth,
   malformed containers or conflicting fields fail evaluator execution; invalid class
   strings remain incorrect scored predictions under the unchanged independent oracle.
3. Make native `data_mapping` explicit. Verify actual registered evaluator schema/version
   and the observed service envelope. Documentation mentioning `model` does not prove
   the previously working `deployment_name` parameter is wrong; canary both against the
   selected evaluator contract before changing an initialization field.
4. Reject both inline skills and directory-backed skills for instruction-only candidates,
   including loader `has_skills`/`skills_dir`, tools and unapproved model changes. Validate
   `CandidateConfig` fields rather than assuming its constructor rejects invalid values.
5. Assign a new evaluator/version/series for revised registered code. Keep old code bytes
   and native results accessible. Frozen independent `evaluator.py`, label vocabulary,
   split membership and metric formulas do not change for this migration.

Tests: each valid output shape; correct/wrong/invalid labels; whitespace; null/non-string
inputs; `sample=None`; conflicting representations; malformed ground truth; inline and
directory skills; foreign models/tools. Live gate is a small versioned mapping canary,
not re-running historical optimization or exposed holdout. A synthetically correct case
must score 1 and a wrong label 0 through the actual new registered mapping.

Exit: all shape canaries discriminate; no false score from adapter errors; instruction-only
invariant holds; historical evaluation unchanged. This repair precedes scoring-path cleanup.

### F03 - Official Response Models With Strict Result Acceptance

Files: E [sample_text and collect](../testbeds/foundry-agent-evaluation/deploy/experiment.py#L553),
O `campaign.py::eval_metrics`, candidate evaluation collection; existing tests.
Sources: D07-D09, D12.

1. Use official model serialization (`as_dict()` for Azure models,
   `model_dump(mode="json")` for OpenAI) before a single bounded target-output adapter.
   Response objects supply `output_text`; evaluation rows can instead contain serialized
   message blocks. No universal output property or conversion is assumed across both.
2. Cross-check direct, dotted and nested target output when several appear. Decode the
   retained assistant content-block format with shape/size checks. Never score judge
   `results[].sample` as the agent response. Preserve tool proof envelope as a versioned
   contract until C03 is accepted.
3. Verify run/row completion, absence of service errors, exact expected query membership,
   unique output IDs, criterion name/version/metric identity and required fields. Scores
   must be finite numbers, not booleans. Retain real failed criteria as valid scored
   evidence; distinguish `complete`, `oracle_passed`, `criterion_passed` and `accepted`.
4. Use SDK `output_items.list` iteration/`iter_pages()` and `retrieve` rather than manual
   continuation URLs. Impose total-row/page/deadline bounds, detect duplicates across pages,
   preserve cursors on incomplete collection. `limit` is page size, not completeness.
   E's three-row extra-page refusal remains valid for its fixed experiment.
5. Prefer public request types `TestingCriterionAzureAIEvaluator`,
   `TargetCompletionEvalRunDataSource`, `AzureAIAgentTargetParam` and `EvaluatorVersion`
   where they replace repeated wire dictionaries. Keep semantic validation because
   generated models accept missing/unknown fields; preserve extension fields in raw evidence.

Tests: malformed and conflicting outputs, wrong evaluator/version, errored/skipped rows,
cancelled runs, duplicate/missing/foreign rows, multiple pages, booleans, NaN/infinity,
partial retrieval, genuine below-threshold score. Replay retained public fixtures offline;
do not overwrite old verdicts. Exit: all result consumers share their owning tested
contract and cannot claim acceptance from a successful HTTP status alone.

### F04 - Replace Handwritten Authenticated Hosting Transport

Files: H [api](../testbeds/foundry-hosted-agents/deploy/experiment.py#L249), `deploy`,
`inspect_agent`, `invoke`, `verify`, `logs`; O
[inspect_runtime](../testbeds/foundry-agent%20optimization/deploy/campaign.py#L139).
Sources: D01-D03, D12.

Replace manually constructed bearer headers, URLs, authenticated HTTP calls and response
unwrapping with these installed public operations:

| Existing operation | SDK replacement |
| --- | --- |
| Agent/version create and read | `AIProjectClient.agents.create_version`, `get`, `get_version`, `list_versions` |
| Session enumeration and read | `agents.list_sessions(agent_name=...)`, `get_session(...)` |
| Protected inference/readback | `project.get_openai_client(agent_name=..., max_retries=0, timeout=...)`, `responses.create`, `responses.retrieve` |
| Log bytes | Keep `agents.get_session_log_stream` already used |

`agents.create` is not an available substitute for `create_version` in Projects 2.6.1.
Pin the invocation's `agent_reference` with explicit name and version in `extra_body`,
as O already does; reading an expected version before calling latest is insufficient.
Use public SDK typed container/protocol definitions where supported. Preserve exact
timeouts, no write retries, prestate/ownership checks, 404 semantics and receipt compatibility.
Delete old authenticated generic `api` helper only after every caller migrates.

Keep a small unauthenticated HTTP probe: an authenticated SDK cannot prove anonymous
refusal. TLS/platform identity configuration is not redundant. Keep operator
`AzureCliCredential` and workload credential exclusions; no ambient human fallback.
Do not replace platform agent identity with a project identity by assumption.

Tests: older-version routing after latest changes; wrong image/config/owner; unknown create
outcome without repeated POST; multiple/empty session pages; credential/timeout failures;
exact stored text/metadata; anonymous 401/403. Use injected SDK transports and no network
for tests. Live equivalence is F08, not inferred from source tests.

### F05 - Use Native Optimizer Results And Recovery Identities

Files: O [collect_candidates](../testbeds/foundry-agent%20optimization/deploy/campaign.py#L430),
`optimize`, `optimizer_operation`, `inspect_optimizer`, `optimizer_wait`.
Sources: D04-D06, D12.

1. Enumerate `project.beta.agents.get_optimization_job(job_id).result.candidates`.
   Remove separate raw `/candidates` listing and its HTTP/pagination duplication.
   Preserve IDs, name, score/tokens and evaluation/run links. Additional timestamps or
   latency fields may require an explicitly retained source, not invented equivalents.
2. Record `poller.details["job_id"]`, supported continuation token/operation identity,
   sanitized headers and exact submitted request before handing off. Do not reconstruct
   internal operation URLs or resubmit create merely to rediscover headers.
3. Keep native `begin_create_optimization_job` and the official advanced polling pattern:
   `polling=False`, bounded `get_optimization_job` reads and retained state transitions.
   Alternatively use the native poller only if timeout/background cleanup and restart
   tests pass. `result(timeout=...)` is not a cancellation guarantee.
4. Keep bounded Evals reconciliation; installed OpenAI runs have no verified poll-until-done
   convenience method. Prefer stored run IDs and `retrieve` over recent-run discovery.
5. Evaluate config retrieval through C01 separately: candidate listing is not config
   resolution. No fabricated `get_candidate_config` method or import of private resolver.

Tests: existing three candidate identities match; cancelled/failed job retains partial
evidence; empty/duplicate/missing candidates refuse completeness; interrupted submission
and restart perform no second create; no live poller remains on closed clients. Export
native and independent metrics separately; no generated lineage or summed duplicate usage.

### F06 - Remove Consumed Repair Paths And Parameterize Active Runs

Files: H/E/O CLI dispatch and runbooks; O `campaign.py` observers/`SERIES`; E upload
recovery actions; O dependency and optimizer diagnostic actions. Sources: D04, D07, D12.

1. Derive agent/version/job/candidate IDs, counts and expected paths from a pinned input
   run manifest, not `cand_opt_21*`, a global historical series or fixed 90/60-row watchers.
   Reuse current request/result types and evidence owner; no new workflow engine.
2. Identify callers of `register-existing`, `optimizer-operation`,
   `optimize-retry-rejected`, dependency restore commands and consumed canaries. Archive
   their source snapshot, migrate active runbook callers, then remove obsolete active
   dispatch. Keep a bounded official read-only reconciliation path for unresolved work.
3. Replace local-file observer busy loops with existing command completion plus resumable
   status reads where no live monitoring consumer exists. Keep provider polling only when
   it waits for a real provider operation. Do not remove useful deadlines as "redundancy".
4. Correct E upload-helper explanation: Blob kwargs include retry/timeouts, but stage
   provenance validation, per-stage intents and recovery are the reason explicit APIs
   remain. Correct SDK/REST support labels and mark uncertain routes honestly.

Tests: retired actions unavailable or return a no-mutation migration instruction;
fresh and historical run IDs cannot mix; wrong manifest refuses; resumption reads existing
operation without re-execution; no remaining active caller of removed functions.
Exit: removed code and matching documentation changes listed, old evidence readable.

## 4. Conditional Opportunities

These opportunities must receive a decision, not all become new dependencies/features.
Default choices optimize deletion of redundant mechanics, not the number of SDKs imported.

### C01 - Public Candidate Configuration Loader

Target: O `collect_candidates` config GET, `main.py::loaded_spec`, native config apply.
Official: `azure.ai.agentserver.optimization.load_config(config_dir=..., credential=...)`
and `CandidateConfig` (D06). Runtime already uses this public loader.

**Adopt for retrieval only if** an isolated caller-owned output directory preserves raw
config evidence, exact instruction bytes/hash, expected candidate identity, transport
bounds, no silent baseline fallback and no unrelated downloads or overwrites. Installed
1.0.0b1 caches by candidate ID, writes files, can download skills/manifests, strips local
instruction whitespace and does not expose timeout/retry transport controls. Test all
resolution sources, malformed fields, missing candidates, cache reuse and path escapes.
Native inline `OPTIMIZATION_CONFIG` is supported but marked deprecating in installed
source; do not remove it without proving resolver-path parity.

**Otherwise retain** a narrowly bounded read-only resolver adapter with version pin and
documented exception. Its route matches Microsoft's loader; a complete public REST
reference was not verified. Do not describe it as fully documented or import `_resolver`.
This exception must remain visible in final report; it does not block F05 enumeration.

### C02 - Dataset Convenience Upload

Target: E `storage_response`, URL/provenance validation, `upload`, registration recovery.
Official: `datasets.upload_file`, `pending_upload`, `create_or_update`, `get`,
`get_credentials`; Blob `ContainerClient` (D10).

**Default retain explicit public SDK stages.** A helper can remove orchestration only
after tests prove pre-byte destination validation, same blob-prefix handling, separate
reservation/upload/registration intent recovery, bounded transport at every stage and
remote byte/hash readback. Helper kwargs reach Blob upload, not necessarily all stages;
the installed helper chooses basename rather than the returned blob prefix. Do not
weaken trusted-response provenance or assume managed storage shares our subscription.
SAS stays in memory and outside URLs/receipts/logs. Dataset version maximum is 50 characters;
keep full content hash separately. Test timeout after each stage and unknown reservations.

### C03 - Native MAF Hosting And Structured Tool Output

Target: both `main.py` handlers; public `llm_interface` boundary only if needed.
Official modern host: `agent_framework_foundry_hosting.ResponsesHostServer(agent)` (D13).
Current official `ResponsesAgentServerHost`/`TextResponse` is already valid integration.

**Not a drop-in:** `AgentBinding` exposes a guarded event/session contract, not native
`SupportsAgentRun`; no public native-agent accessor exists. Do not access private internals,
instantiate a second unguarded agent or import incompatible legacy adapters. Gate a
public owner-approved adaptation on actual deletion of protocol/session/tool handling
and preserved limits, tool authorization, cancellation, metadata and stored readback.

Native structured output could let Foundry tool evaluators consume real `output_items`;
today H returns tool events as JSON text. If adopted, version the response/evaluator
contract and update both callers together. Test native function-call/output correlation,
exact custom-tool result, partial streams, cancellation, anonymous refusal and historical
text-envelope readback. Otherwise keep the current host and explicitly state its limitation.

### C04 - ACR Build Submission With Direct Run Identity

Target: H `build`, O `hosting.py::build` discover new ACR runs from inventory differences.
Official CLI is acceptable, but concurrent builds make that association ambiguous.
Preferred replacement candidate: `azure-mgmt-containerregistrytasks` operations
`registries.get_build_source_upload_url`, `registries.schedule_run(...) -> Run`,
`runs.get`; `DockerBuildRequest`; `azure-containerregistry`
`ContainerRegistryClient.get_manifest_properties` (D14).

Packages absent at audit. Resolve/pin via F01 before use. Adopt if native returned run
identity removes the discovery race without increasing equivalent custom machinery.
Keep build context allowlist, linux/amd64, source archive/hash, immutable image digest
and unknown-submit reconciliation. No upload SAS logging or automatic destructive cleanup.
Test concurrent unrelated runs and dropped create response. If documented CLI exposes
equivalent direct run identity, use it instead of adding a second management stack.

### C05 - Hosted Code Upload Instead Of ACR Containers

Official `agents.create_version_from_code(..., code=..., code_zip_sha256=...)` with
`HostedAgentDefinition(code_configuration=CodeConfiguration(...))` can remove Docker/ACR
build and image-pull plumbing (D15). Treat as an alternative to C04, not a second default.

Adopt only in an explicitly selected deployment-mode migration. A uv-built Linux bundle
must include canonical dependencies under the documented `packages/` convention, fit
service limits, pass TLS/runtime checks and provide immutable ZIP/source identity.
Remote-build dependency tooling is unverified and cannot bypass the uv requirement.
Existing image-digest acceptance would need a versioned equivalent content-hash contract.
Otherwise retain containers; do not claim an API replacement with unchanged semantics.

### C06 - Service-Managed Independent Evaluation

Target: O `baseline_validation`, `candidate_validation`, `final_holdout` invocation loops.
Official Evals target runs (D07-D09) can own batch dispatch and per-row retrieval.
Adopt for a **new migration canary series** if rows preserve pinned target/config identity,
stored response IDs, errors, exact membership, independent metric inputs and resumability.
Do not substitute native optimization search rows for independent validation. Server-side
retries are not a client billing cap; preserve reported/unknown attempt accounting.

Keep independent local `evaluator.py` aggregation and held-out separation. Cloud upload
of holdout requires evaluator-only access proof, not convenience. Do not run existing
holdout. If equivalent identity/readback is unavailable, retain direct SDK invocation
with one small local helper instead of inventing a new batch service.

### C07 - Official Graders And Typed Outputs

Potential replacements: native string-check equality or OpenAI `StringCheckGraderParam`,
native evaluator schemas and MAF structured output (D08-D09, D16).
Gate exact-label replacement on whitespace, invalid/null values, mapping and denominator
parity. Some samples accidentally compare ground truth to itself; reproduce wrong-answer
canaries, never copy sample assertions blindly. Optimizer evaluator references are not
arbitrary OpenAI grader objects.

`builtin.f1_score` is text similarity, not the fixed three-class confusion-matrix macro-F1.
LLM label judges and native composite averages are also not equivalent. Keep those local
classification metrics. A JSON/enum output schema could remove format parsing but changes
the exact-label task contract; use a fresh declared comparison, not historical repair.

### C08 - Native Tracing And Metrics

Official `AIProjectInstrumentor.instrument(...)`, MAF instrumentation and Application
Insights can replace handwritten span/token timing instrumentation (D17). Hosting already
configures instrumentation; prove no double spans/exporters before adding another layer.
Keep sensitive content/baggage disabled and avoid decorators that capture arguments/results
regardless of content settings. Traces supplement immutable receipts and request IDs.

Optimizer job result is candidate metadata; Foundry **Evals** owns evaluation runs,
per-criterion/row results and report URLs. Operational telemetry belongs in tracing/Monitor.
Keep CSV/JSON export as a derived joined view for independent accuracy/macro-F1; no verified
native export removes that requirement. Do not invent generation/parent fields or sum
duplicate native usage groups. Implement only if it replaces existing custom instrumentation
or a named required correlation gap, not as a new dashboard project.

### C09 - Native Cancellation And Resource Lifecycle

Both host handlers ignore the native cancellation signal. Test cancellation during model
and tool work before claiming a leak. If needed, connect that signal to existing tasks
and SDK shutdown hooks rather than adding another scheduler. Test no subsequent dispatch,
resource closure and no false completed result. Per-request context managers already own
credentials/transports; pooling changes concurrency and is not automatic simplification.

Public `agents.stop_session`, `delete_session`, `delete_version`, Responses cancel/delete
can replace future cleanup code (D01-D03). Respect cancellation mode restrictions and exact
ownership. Current resources are intentionally retained: no automatic teardown. SDK log
stream returns bytes despite structured annotations; documented bounded SSE decoding and
redaction remain needed unless a supported decoder is actually verified. Test split UTF-8,
multiline/malformed events and limits; never log unrestricted tool/model content.

### C10 - Shared Owners, Management And Configuration

Keep short official Azure CLI account/resource/RBAC/model preflight unless native ARM
SDKs materially reduce duplicate process parsing across real consumers (D18). More
imports alone are not simplification. Preserve inherited roles, registry mode, exact
principal, effective-access limits and deterministic grant/readback. No automatic `azd up`.

Keep canonical YAML/`agentconfig` and `llm_interface`; Foundry metadata does not replace
their allowlists, public contracts or single MAF loop. Native AZD optimizer apply is optional,
not a second execution path requiring a parallel config source. Keep config application
from retrieved native candidates reproducible and explicitly versioned.

If duplicated SDK-only code still remains after F04-F06, prefer direct calls; extract only
when two actual callers share semantics. Check the existing modular-agents public hosting
surface first. It is not a verified replacement for this Foundry lifecycle; do not reach
into its internals or put project resource names in a library. A shared extension needs
one owner, public contract, both consumer migrations and removal of old implementations.
Completed-output recovery may reuse `workrecovery` only if its envelope/API fits; it does
not replace pre-call intents, jobs, queues or cloud idempotency. No generic `utils` package.

## 5. Final Required Tasks

### F07 - Consolidate Runbooks And Measure Real Deletions

After conditional decisions, update only owning H/E/O READMEs, commands, requirements and
tests whose behavior changed. Re-read user-edited specs before changing them. Root README
changes only when current state becomes inaccurate. Preserve reusable skills as working
operator recipes with SDK versions, official links and explicit retained exceptions.

Record before/after active custom functions, authenticated HTTP sites, dependency mutation
sites, files/lines and package counts using the same scope. List removed symbols/callers
and their official replacements. No estimated effort savings or code-reduction claim
without measurement. Added negative tests are not counted as production duplication.

Exit: every opportunity has a recorded disposition; active docs require uv; no obsolete
caller remains; all offline acceptance checks pass and historical hashes still match.

### F08 - Exact-Artifact Live Parity

Future execution only after bound live authority and local checks; use each owning
`deploy/deploy.sh`, never one-off write commands. Record task/source/lock/build identities
before mutation and do not overwrite accepted deployment or comparison records.

1. Hosted canary: build exact uv-locked artifact; create version via official SDK; invoke
   both custom tools with fresh development inputs and explicit version; read stored result
   and server config/image identity; require anonymous 401/403 and no foreign-owner access.
2. Evaluation canary: fresh synthetic versioned rows, new grader version if F02 changed;
   one normal and one deliberately wrong output; complete row/result retrieval and finite
   scores, aggregate counts, raw IDs and negative canaries. A low score is not tool failure.
3. Optimizer read-only parity first: retrieve existing job through SDK and compare candidates
   and evaluation links to immutable receipts. If submit/recovery/config-loader behavior
   changed, run a separately named minimal native canary with development-only data and
   frozen canary criteria, apply actual generated config and verify loaded identity.
   Never rerun old series/holdout or claim historical score equivalence from a new run.
4. C04/C05/C03 adopted: run their specific concurrency, artifact identity, protocol/tool,
   auth, cancellation and readback checks; document any semantic contract version change.
5. Reconcile every accepted/unknown operation before stopping. Retain failure receipts;
   do not report success from local tests or dashboard appearance. No new live campaign
   is necessary for a docs-only or pure existing-result serialization change.

Exit: observed protected user journey for each changed live slice; unexecuted gates
explicitly `not_verified`, not `passed`. Host/model provisioning beyond chosen canary
targets and destructive cleanup require separately bound authority.

### F09 - Settlement And Completion

Publish verified references to before/after source, lock/image identities, tests, API
canaries, metrics and each exception. Ensure no worker, poller, unknown write or required
acceptance remains unsettled. Preserve source restoration and accepted version selection
procedure; don't claim rollback tested unless observed. Report retained resources/cost
unknowns plainly. Completion requires all F tasks passed and every C task resolved.

## 6. Offline Command Gates

Existing entrypoints below are the initial local gates, not permission to repeat live
actions. They may append fresh local test receipts; historical ones must remain unchanged.

```bash
cd /home/hanchoong/agentcraft
uv --version
uv pip check --python /usr/bin/python3
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh validate
bash 'testbeds/foundry-agent optimization/deploy/deploy.sh' test
```

An existing dependency conflict is a recorded F01 input, not permission for global sync.
First substantive edit must be followed by the cheapest test that can falsify it, before
editing another slice. Reuse H/E/O existing test files; add cases, not another test harness.
If a command has drifted, read its owning CLI and update this gate with evidence before
running it; never guess a mutating subcommand.

Required test matrix in existing tests:

| Slice | Positive | Negative or recovery |
| --- | --- | --- |
| Dependency policy | uv vectors, lock/import provenance | pip fallback, implicit venv, package conflict |
| Grader | all approved target shapes and mapped 1/0 | missing/conflicting/null fields, invalid schema |
| Candidate restrictions | instruction-only config | skills directory, tools/model changes, fallback identity |
| SDK hosting | exact version and stored tool result | latest drift, wrong owner/image/config, anonymous success |
| Results | complete finite criterion rows | missing/duplicate/foreign/error rows, wrong criterion, NaN/bool |
| Native job | public candidate/result IDs | replayed create, unknown acceptance, canceled/partial result |
| Upload | authenticated destination and bytes | foreign/private URL, prefix mismatch, stage timeout, SAS logging |
| Cancellation | closed tasks/clients | further dispatch or false completion after cancellation |
| History | byte-identical retained evidence | mutation or deletion of accepted receipts/splits |

## 7. Official Source Index

Checked 2026-09-22 through current Learn docs and installed SDK/source inspection.
Version-pinned samples take precedence for installed-call signatures; service behavior
still needs canaries. A sample is not proof of correct evaluator semantics. Floating docs
can describe newer features; do not upgrade the workspace to match them automatically.

| ID | Official reference | Use |
| --- | --- | --- |
| D01 | [AIProjectClient](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.aiprojectclient?view=azure-python), [AgentsOperations](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.operations.agentsoperations?view=azure-python) | Client, version/session APIs |
| D02 | [Deploy hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent) | Host protocol, container deployment and identity |
| D03 | [Manage hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent), [session sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_sessions_crud.py) | Session lifecycle and byte-stream logs |
| D04 | [Basic optimizer sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/agents/optimization/sample_optimization_job_basic.py), [advanced app polling](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/agents/optimization/sample_optimization_job_advanced_app_polling.py) | Public submission, job ID and polling patterns |
| D05 | [BetaAgentsOperations](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.operations.betaagentsoperations?view=azure-python), [job result](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.models.agentoptimizationjobresult?view=azure-python) | Typed results and candidates |
| D06 | [Optimizer readiness](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/make-agent-optimizer-ready), [loader 1.0.0b1](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-agentserver-optimization_1.0.0b1/sdk/agentserver/azure-ai-agentserver-optimization/README.md) | Public config loader and documented integration |
| D07 | [Cloud evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation), [target sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/evaluations/sample_agent_evaluation.py) | Version-pinned batch evaluation and results |
| D08 | [Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators), [code evaluator sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/evaluations/sample_eval_catalog_code_based_evaluators.py) | Grader input shapes and versioning |
| D09 | [Coherence sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/evaluations/agentic_evaluators/sample_coherence.py), [graders sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/evaluations/sample_evaluations_graders.py) | Current mapping/schema, not copied score assertions |
| D10 | [DatasetsOperations](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.operations.datasetsoperations?view=azure-python), [dataset sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/datasets/sample_datasets.py) | Convenience helper and staged public upload |
| D11 | [Optimizer overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview), [optimizer dataset](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/create-optimizer-dataset) | Composite metrics and task/evaluator contracts |
| D12 | [OpenAI Python 3.13.0](https://raw.githubusercontent.com/openai/openai-python/v3.13.0/README.md) | Responses/Evals serialization, pagination, request IDs, timeouts/retries |
| D13 | [MAF Foundry hosting](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent), [framework integration](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/framework-hosted-agents) | Modern adapter, not legacy package substitution |
| D14 | [ACR Tasks registry operations](https://learn.microsoft.com/en-us/python/api/azure-mgmt-containerregistrytasks/azure.mgmt.containerregistrytasks.operations.registriesoperations?view=azure-python), [run operations](https://learn.microsoft.com/en-us/python/api/azure-mgmt-containerregistrytasks/azure.mgmt.containerregistrytasks.operations.runsoperations?view=azure-python), [DockerBuildRequest](https://learn.microsoft.com/en-us/python/api/azure-mgmt-containerregistrytasks/azure.mgmt.containerregistrytasks.models.dockerbuildrequest?view=azure-python), [registry data client](https://learn.microsoft.com/en-us/python/api/azure-containerregistry/azure.containerregistry.containerregistryclient?view=azure-python) | Direct build identity and immutable manifest properties |
| D15 | [Hosted code upload](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code) | Conditional code-bundle deployment |
| D16 | [MAF structured output](https://learn.microsoft.com/en-us/agent-framework/agents/structured-output) | Conditional typed output contract |
| D17 | [AIProjectInstrumentor](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.telemetry.aiprojectinstrumentor?view=azure-python), [client tracing](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-client-side?tabs=python) | Native tracing, privacy and correlation |
| D18 | [Resource operations](https://learn.microsoft.com/en-us/python/api/azure-mgmt-resource/azure.mgmt.resource.resources.operations.resourcesoperations?view=azure-python), [model deployments](https://learn.microsoft.com/en-us/python/api/azure-mgmt-cognitiveservices/azure.mgmt.cognitiveservices.operations.deploymentsoperations?view=azure-python), [RBAC](https://learn.microsoft.com/en-us/python/api/azure-mgmt-authorization/azure.mgmt.authorization.v2022_04_01.operations.roleassignmentsoperations?view=azure-python) | Optional management SDK consolidation |
| U01 | [uv dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/) | Declaration, no-sync add/remove and source ownership |
| U02 | [uv existing environments](https://docs.astral.sh/uv/pip/environments/) | Explicit existing interpreter; repository prohibits documented venv examples |
| U03 | [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/) | Official binary/image pins and system-image installation |

Unverified public contract: raw optimizer candidate-config REST beyond the installed
official loader implementation. Failed guesses at API-reference URLs are not evidence
of an endorsed endpoint; C01 records the bounded exception or replaces it safely.
Modern MAF host full installed signature, code-upload live parity and ACR Tasks resolved
dependency versions also remain unverified. No cloud requests were needed for this audit.

## 8. Completion Checklist

- [x] F00 recovery/source/authority/interpreter baseline retained.
- [x] F01 uv-only policy covers local scripts, images, locks and active instructions.
- [x] F02/F03 correctness canaries fail before repair and pass after repair.
- [x] F04/F05 SDK replacements remove old authenticated transport and candidate-list code.
- [x] F06 historical repair actions retired only after caller migration; run identities explicit.
- [x] C01-C10 each have evidence-backed implementation or retention/defer/block decisions.
- [x] F07 measurements and reusable operator documentation match actual changes.
- [x] F08 all required exact-artifact live checks pass, or result remains explicitly incomplete.
- [ ] F09 operations settled, old evidence hashes unchanged, authoritative outcome published.

Observed F08: H three tools including distinct redeployment, exact stored identity,
anonymous refusal and caller-side foreign-owner guard; E three complete finite rows
and 3/3 tool proofs; both versioned grader mappings 1/0/0; O three development jobs,
first two baseline-only, third baseline plus two generated configs actually loaded
as versions 3/4/5 with nine stored independent responses and separate metric exports.
Local tests H39/E26/O46. Eight protected/final versions matched; all operations terminal;
896 historical hashes unchanged. F09 settlement prepared, not authoritatively published.

C09 native cancellation is verified on deployed H/O with terminal `cancelled` and
no completed output. Joined child tasks/closed credentials are locally tested;
provider cleanup log marker was not recovered. No separate-principal IAM, live
rollback or hard-kill durability claim. C01 loader-compatible resolver exception
remains. Historical 28/30 versus 29/30 is unchanged; synthetic development scores
are not prediction improvement or generalization evidence.

Final handoff: concise implemented/retained/blocked opportunity list, source/lock/image
identities, removed code measurements, command/results table, protected live acceptance,
unchanged historical evidence receipt and remaining documented exceptions. Do not state
"fully official" while an unverified resolver route or untested adapter remains.

This spec is the durable audit artifact; no separate notebook infrastructure is required.
The existing repository `/specs/` ignore rule also covers this file. Do not change Git
tracking, stage, commit or push it without an explicit request.