# Overseer Self-Optimization Demonstration

Status: **authorized local data understanding; two exploratory iterations recorded**.

[Constitution](agentcraft_projects/overseer-self-optimization/constitution/constitution.yaml)
defines the objective, proposed measurements, permitted modification levers and fixed comparison
boundaries. Revision 6 uses schema v2 and `status: exploring`. Null scoring targets are discovery work,
not a blocker. With explicit `authority.limit_policy: user-unbounded`, null caps/expiry mean no user-imposed
bound within this local mission; actual permissions and stop conditions still apply. The demonstration directory is the
workspace root for the process's existing `agentcraft_projects/<project-id>/` layout; all run,
dataset, notebook and report paths in the constitution are relative to that project directory.

## Objective

Deliver a cyber agent that queries network telemetry, detects supported attacks and persists
evidence-backed alerts with affected hosts, time windows and uncertainty. No autonomous remediation.
Begin with attack-flow detection; incident-level claims need defensible incident ground truth.

Separately improve AgentCraft Overseer's time, effort, reliability, autonomy and reproducibility
in building, changing, deploying and verifying that agent. Cyber quality gates cannot be traded
for delivery speed. Compare overseer versions on equivalent tasks; a better detector alone does
not demonstrate a better overseer. Role, skills, supporting agents and reusable tooling are
candidate levers. Definition edits are preparation, not improved-performance evidence.

## Data Understanding First

Query -> explore -> test extraction hypotheses -> repeat -> choose tools and agent responsibilities ->
freeze evaluation -> build and measure. Revisit the data when later results expose another uncertainty.
The overseer owns routine technical decisions under the user's local mandate, without another approval
cycle. Data rights, safety, truthful evidence and frozen evaluation remain constraints.

Current routing is `agentcraft-overseer -> agentcraft-orchestrator -> local-dev-test-subject`.
The [domain orchestrator](../.github/agents/agentcraft-orchestrator.agent.md) maintains and executes assigned
stages/iterations and pilots all candidates/specialists. Overseer direct children are exactly
`agentcraft-orchestrator`, `archivist`, `note_scribe`; it retains mission alignment, strategic priorities,
authorization/criteria changes and evidence review. Direct overseer candidate dispatch is prohibited.

The candidate remains [local-dev-test-subject](../.github/agents/local-dev-test-subject.agent.md), not an extra
service deployment. Earlier direct invocations ran the saved query probe and read back results; those records
remain historical evidence, not current dispatch permission. New hierarchy has definition checks only,
not fresh invocation proof. Model/effective-effort attestation is unavailable; requested max is not runtime proof.

- [First exploration](agentcraft_projects/overseer-self-optimization/results/20260919T095912Z-data-understanding-01/run.json):
	six CSV prefixes, 2000 rows each, repeated identically. HIKARI's prefix has one attack label;
	four UWF prefixes each contain 1992 duplicate rows. The probe omitted `mitre_attack_tactics`.
- [Evidence-driven follow-up](agentcraft_projects/overseer-self-optimization/results/20260919T100445Z-data-understanding-02/run.json):
	explicit column selection now yields repeatable counts in all five UWF files. Four prefixes contain
	only Reconnaissance and one only Discovery. These samples do not establish detection quality.

The saved probe supports `datasets.sh explore --rows 2000 --label-column mitre_attack_tactics
--output <new-absolute-project-results-evidence-path>` and `--compare <prior-profile.json>`.
Outputs are create-only; use a new path for every attempt. Next data questions concern non-prefix windows,
cross-file overlap, timestamp semantics and the Parquet tables. Findings determine tool/split design.

## Decisions And Iterations

The project root is `agentcraft_projects/overseer-self-optimization/` beneath this directory:

```text
records/v2/<UTC-timestamp>-<record-id>/record.json
records/v2/<UTC-timestamp>-<record-id>/artifacts/
results/<run-id>/evidence/
reports/latest.html
```

[Archivist](../.github/agents/archivist.agent.md) is the sole publisher of new authoritative JSON records.
Overseer alone dispatches archivist and note_scribe. Workers deliver observable actions and primary evidence
through the domain orchestrator; missing archival receipts return as checkpoint requests to overseer;
the evaluator owns grades; `note_scribe` links the archive for lessons. The archivist captures pre-change,
phase and measured-outcome checkpoints and returns compact receipts plus missing evidence.

Decisions precede actions, events capture progress during each iteration, and final run records
link measured outcomes to decision IDs, changed levers, versions and evidence. All carry project,
series, run/parent and iteration identity where applicable, plus the constitution revision/digest.
Pre-run project decisions have null run context. Exploration uses `stage: data-understanding` and
`evidence_class: exploratory`; it cannot claim comparative improvement. No scored baseline exists yet.

[The process recorder](../.github/skills/agentcraft-process/record.py) accepts a JSON object on stdin,
publishes create-only and verifies read-back. Invoke from the repository root:

```bash
python3 .github/skills/agentcraft-process/record.py --project-root demonstration_project/agentcraft_projects/overseer-self-optimization < decision-input.json
python3 .github/skills/agentcraft-process/record.py --project-root demonstration_project/agentcraft_projects/overseer-self-optimization --verify
```

Every new bundle includes the exact constitution and optional explicitly selected, sanitized source
snapshots. `record_refs` links prior decisions, outcomes and measurements by path/hash. Change checkpoints
identify before/after versions, coverage and reversion status; snapshots alone do not prove live recovery.
Historical v1 decisions and runs remain untouched. The archivist's retrospective handover records missing
original before-state and incomplete historical action capture instead of inventing them. New before/after
checkpoints preserve the constitution transition from revision 4 to 5. Revision 6 changes routing only;
its post-change archival checkpoint remains for archivist publication after the implementation handoff.

Its [owning contract](../.github/skills/agentcraft-process/SKILL.md#decision-and-progress-records)
defines fields and publication guards. Corrections append, never overwrite. Keep secrets and
evaluator-only labels out; record observations and concise rationales, not private deliberation.
Charts and diagrams will derive from these records. The archivist and recorder verify structured records,
selected snapshots and references, not total hidden activity or causal improvement. Full action instrumentation,
the scored experiment runner, visualization and verified live reversion remain unimplemented.

## Datasets

Cyber incident detection is the selected demonstration domain. Both approved source datasets
are acquired under Git-ignored `data/`; scripts and [source lock](datasets.lock.json) remain
version-controlled inputs. Actual acquisition: **15 payload files, 1,341,813,722 bytes**, including
the retained HIKARI archive and extracted CSV. No packet captures or pickle files were acquired.

| Dataset | Local holdings | Terms and source |
| --- | --- | --- |
| HIKARI-2021 | `data/hikari-2021/`: CSV ZIP plus extracted `ALLFLOWMETER_HIKARI2021.csv` | [Zenodo 6463389](https://zenodo.org/records/6463389), CC BY 4.0 |
| UWF-ZeekData22 | `data/uwf-zeekdata22/`: five CSV subset files and eight weekly Parquet tables | [UWF](https://datasets.uwf.edu/), CC BY 4.0 |

UWF's CSV subset covers reconnaissance and discovery, not its complete attack taxonomy.
The Parquet files are the published weekly table export, not the entire original log corpus;
the publisher's 140-million connection-record figure is not a verified local row count.
HIKARI contains benign traffic and synthetic attacks. Prefix schemas and selected label frequencies have
been measured; full row counts, semantics, overlaps, quality and held-out split feasibility remain
**not_verified** and are active discovery work. Acquisition is not a detection experiment.
The lock records publisher/citation/license URLs, exact file URLs, byte counts, timestamps,
HTTP metadata and hashes. HIKARI's archive matches the publisher's MD5. UWF hashes are locally
observed SHA-256 pins, not independently published checksums. Respect attribution on reuse.

Run from the repository root; the entry point also resolves its paths from other working directories:

```bash
bash demonstration_project/scripts/datasets.sh setup
bash demonstration_project/scripts/datasets.sh test
bash demonstration_project/scripts/datasets.sh download
bash demonstration_project/scripts/datasets.sh verify
```

[datasets.sh](scripts/datasets.sh) owns the sequence; [datasets.py](scripts/datasets.py) implements
it. Setup installs the existing local `harness-web-resource` package without dependencies into
ignored `data/.runtime`; no virtual environment or system-package override. Requires Python 3.11+,
pip and the package's local build prerequisites. Nothing installs implicitly during download.

Download uses the tracked lock when present, verifies existing files before skipping, and refuses
modified completed files. HTTP is public-only, robots-aware and rate-limited through `webres`.
Discovery without a lock freezes a local plan before payload transfer; future dataset revisions
require deliberate review, not silently refreshed URLs. Limits: 8 GiB total transfer, 2 GiB per
file/extracted CSV, 30 minutes per file and a free-space check. Interrupted `.partial` files are
restarted on rerun; verified completed files are retained. Do not run concurrent acquisitions
against the same data directory. A source/hash conflict stops rather than overwriting evidence.

Verify is offline and checks all pinned bytes/hashes plus ZIP/Parquet signatures. Original download
receipts remain beside payloads; fresh acquisitions get their own receipts without changing the
tracked source lock. Eight offline tests and an actual second download invocation passed; all
completed files were skipped and the lock digest stayed unchanged.

## Before Scored Comparison

- Select a bounded application mission and equivalent variants, authorized data and live target.
- Agree quality/safety gates, numeric targets, trial schedule and independent evaluator ownership.
- Freeze exact baseline and candidate definitions; a version name alone is not a frozen artifact.
- Establish telemetry coverage, protected evaluation, deployment read-back and restoration.
- Exercise delegated criteria/design authority and honor the recorded open-ended local mandate.
- Complete semantic review, then validate and version a ready constitution before scored trials.

From the repository root, the readiness check is:

```bash
python3 .github/skills/agentcraft-process/validate.py demonstration_project/agentcraft_projects/overseer-self-optimization/constitution/constitution.yaml
```

Expected now: `valid` for the authorized exploration phase. Unknown scoring criteria do not stop probes;
the recorder still refuses optimization-stage records until a ready constitution exists. Reports and
dashboards are proposed outputs, not implemented surfaces. The acquisition lock is not the scenario/split
manifest. Saved discovery outcomes are not scored optimization receipts.

## Reference Project

The former `optimization_framework/` tree was moved intact to `reference_project/` and ignored
by Git at the user's request. It is local reference material, absent from fresh checkouts and
not a runtime dependency. Its original files, receipts and generated artifacts are preserved;
commands and links that depend on the old checkout layout are not relocation-verified.

Inspect reusable mechanisms before adopting them through their owning public contracts.
Historical results are not this project's baseline. Prior cloud/model grants do not transfer.
The old tracked paths appear as deletions; the ignored destination remains on disk. Nothing
was committed or automatically staged as part of this preparation.