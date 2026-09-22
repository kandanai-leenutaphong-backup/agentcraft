# Experiment Deployment

Status: **blocked, not deployed**. Only offline tests and read-only preflight executed.
Use `bash testbeds/foundry-hosted-agents/deploy/deploy.sh` from repository root.
One deployment owner; no ACA fallback, optimizer, provisioning, role assignment or teardown.

## Prerequisites

Continuation authority (2026-09-22): user approved user-Python installs/upgrades,
exact project-identity registry pull grant, builds and TWO versions of the same
Hosted Agent. No venv, unrelated infrastructure, teardown or auth weakening.
Historical blocked status below is not current acceptance. First run `test`,
then `preflight` for current read-only state, then `install` through deploy.sh.
`install` retains pip diagnostics and checks owner-declared requirements; failure
stops before cloud mutation. Both versions require immutable image/loaded identity,
actual nonce-correlated tool events, protected invocation and stored readback.
Ubuntu PEP 668 refused the first install before mutation. Authorized user-site
installation uses `--user --break-system-packages`, never sudo or a venv; canonical
package source is staged in a temporary directory to prevent source-tree build writes.
After successful installation, run `grant-pull`. It rereads the project, registry,
model and role definition, refuses changed principal/mode or broad role semantics,
creates only exact registry-scoped `AcrPull` when absent, then reads back assignment.
An existing exact unconditional assignment is a read-only no-op. No other role is granted.
`deploy --receipt <new-build> --previous <owned-deploy>` now explicitly creates a
new version of the same agent after old active image/metadata/latest-version
readback. Without owned receipt an existing name still refuses. Both deploy paths
retain accepted identity, then observe provider status for at most 300 seconds;
failed/unknown/deadline outcomes stop, never resubmit creation. Each image build
runs the real SDK readiness/invalid-input smoke. This is not live tool proof.

- Existing `/usr/bin/python3`, Azure CLI, current CLI login matching
  [target](env/target.json). Do not create/activate a venv or switch shared CLI context.
- Owner-declared dependencies plus [hosting requirements](requirements.txt).
  Current interpreter has incompatible MAF/OpenAI/Azure Projects versions and lacks
  hosting/provider packages. Operator remedy, **not executed and requires approval**:

```bash
python3 -m pip install --user ./libraries/framework-core './libraries/llm-interface[foundry]' ./libraries/modular-agents -r testbeds/foundry-hosted-agents/deploy/requirements.txt
```

- Existing project identity `d9cd20e0-1a11-4046-9469-1057ca18396e` needs `AcrPull`
  on registry `agentcraftdev67255` in `rg-agentcraft-dev` under subscription
  `67255afe-8670-4401-a1b8-df6ca63a3516`. Role read-back currently returned `[]`.
  No grant is authorized. Ask for this precise grant or a compatible pre-authorized registry.
- Caller needs effective registry build/push and Foundry deployment permissions.
  These remain unverified; preflight observations are not an effective-access certificate.
- No secrets in files, command output or images. Caller uses `AzureCliCredential`;
  container uses platform identity through Azure Identity with developer/interactive
  credential sources disabled. Foundry gateway owns caller authentication.

## Sequence

Each action writes a new dated JSON receipt under `records/`; stdout prints its path.
Use actual receipt filenames printed by preceding commands, not literal placeholders.

```bash
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-hosted-agents/deploy/deploy.sh preflight
bash testbeds/foundry-hosted-agents/deploy/deploy.sh build
bash testbeds/foundry-hosted-agents/deploy/deploy.sh deploy --receipt <build-receipt>
bash testbeds/foundry-hosted-agents/deploy/deploy.sh invoke --receipt <deploy-receipt>
bash testbeds/foundry-hosted-agents/deploy/deploy.sh verify --receipt <invoke-receipt>
```

| Action | Expected output and effects | On failure |
| --- | --- | --- |
| `test` | `complete`, tests and source manifest; offline only | Repair same slice; no build |
| `preflight` | `complete` only when dependencies/targets/pull role match; Azure reads only | Resolve named prerequisite with separate install/grant authority |
| `build` | Billable ACR build; allowlisted source archive, immutable image digest | Retain archive; inspect ACR operation before retry, never assume timeout means no build |
| `deploy` | Creates one Hosted Agent, platform-managed identity/version; records returned version | Existing name refuses adoption/overwrite; inspect accepted/unknown operation before retry |
| `invoke` | Requires exact active version; anonymous refusal, one authenticated proof, stored response ID | Pending version refuses; inspect status before retry. No repeated inference automatically |
| `verify` | Read-only version and stored-response retrieval; same source/config/tool evidence | Missing/changed evidence is failed acceptance, not success |

Safe reruns: test/preflight/verify append evidence. Build refuses an existing source archive;
deploy refuses an existing agent name, preserving unknown/accepted prior work. Invoke creates
one new synthetic stored response per deliberate invocation and incurs limited inference;
it is not a free/idempotent read. A successful `deploy` receipt records creation, **not readiness**.
No unbounded poll or retry loop. Agent remains retained; teardown is separately authorized.

Container uses official Responses protocol v2 on port 8088. Build context contains only
allowlisted app files, required canonical library source/metadata, Dockerfile and requirements.
No copied credentials, repository history, private datasets or environment directories.
Package installation inside the explicitly requested image build is declared in Dockerfile;
no local automatic installation. Image records `installed-packages.txt`; no dependency lock
has been resolved yet. No image or source archive has been produced in current blocked run.

Before live execution after prerequisite repair, validate installed handler lifecycle APIs and
run container readiness/Responses smoke with the exact image. Current hosting SDK is missing;
this compatibility gate cannot be certified here. Deployment code remains unexecuted.

## Proof

Client sends a fresh 32-hex nonce. Host accepts only this synthetic input, runs canonical
MAF tool loop, and returns server-generated correlated `tool.call.ready`, `tool.started`,
`tool.result` events plus platform version and source/config hashes. Client independently
recomputes expected result. Model answer alone fails. Anonymous HTTP 401/403 required;
404, login page or arbitrary successful response does not count. `verify` retrieves stored
response and checks identical evidence. No private reasoning is captured.

Current receipts and measured gaps are linked in the
[specification](../../../specs/20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md).
No owned process is running; no cloud write or inferred cleanup is pending.