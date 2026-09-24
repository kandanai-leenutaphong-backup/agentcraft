# Experiment Deployment

Status: **two-version live acceptance passed**, 2026-09-22. Baseline version 2;
new-tool version 3. Version 1 retained as failed TLS evidence, not accepted.
Use `bash testbeds/foundry-hosted-agents/deploy/deploy.sh` from repository root.
One deployment owner; existing Foundry/project/model/registry only. No ACA fallback,
optimizer, unrelated infrastructure, auth weakening or teardown.

## Prerequisites

Continuation authority (2026-09-22): user approved user-Python installs/upgrades,
exact project-identity registry pull grant, builds and TWO versions of the same
Hosted Agent. No venv, unrelated infrastructure, teardown or auth weakening.
Read current state with `preflight`; missing dependencies require reviewed lock,
explicit existing target and exact recovery before installation. Run `test`, then
`grant-pull` only when exact approved pull assignment is missing.
`install` retains uv diagnostics; failure stops before cloud mutation.
Both versions require immutable image/loaded identity,
actual nonce-correlated tool events, protected invocation and stored readback.
Historical Ubuntu PEP 668/install attempts remain in immutable receipts; their
package commands are not current instructions. F01 uses uv 0.9.30, existing Python,
explicit `--target`, hashes and retained wheels, never environment creation,
build isolation, system-package override, dependency suppression or global sync.
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
ACR upload uses a temporary directory materialized from verified allowlisted archive
bytes; local tarball paths are not accepted by `az acr build`. Every attempt retains
a distinct archive, queues with `--no-wait`, records run ID, and observes that run
for up to 900 seconds. Never retry an unknown run without inspecting it first.
The installed CLI returns no JSON for `--no-wait`; run discovery uses before/after
inventory and refuses ambiguity, then checks exact output source tag and digest.
Recover an accepted build using `build --run-id <id> --archive <retained-archive>`;
archive members, bytes and manifest must match current source. Recovery submits no build.
Version 1 reached active but model HTTPS failed certificate validation. Adapter
uses public `connect(..., transport=...)` with `ssl.create_default_context()` to
honor platform CA trust, `CERT_REQUIRED`, hostname verification, no proxy env and
zero retries. No shared library edit or TLS bypass. Failed version remains retained.
`inspect` reads agent/versions/sessions; `logs --receipt <deploy> --session <id>`
retains bounded redacted exception lines for an exact owned version/session.

- Existing `/usr/bin/python3`, Azure CLI, current CLI login matching
  [target](env/target.json). Do not create/activate a venv or switch shared CLI context.
- Owner-declared dependencies plus [hosting requirements](requirements.txt).
  Approved installation completed: MAF core 1.18.0, Foundry provider 1.13.0,
  OpenAI provider 1.14.3, Azure Projects 2.6.1, OpenAI 3.13.0, hosting SDK 2.1.0.
  [Install receipt](records/20260922T054628468461Z-install.json).

- Existing project identity `d9cd20e0-1a11-4046-9469-1057ca18396e` has `AcrPull`
  on registry `agentcraftdev67255` in `rg-agentcraft-dev` under subscription
  `67255afe-8670-4401-a1b8-df6ca63a3516`, exact registry scope, no condition.
  [Grant/readback](records/20260922T054913876849Z-grant-pull.json).
- Caller needs effective registry build/push and Foundry deployment permissions.
  Actual image builds, version creation, invocation and retrieval succeeded.
  Preflight alone is not a complete effective-access certificate.
- No secrets in files, command output or images. Caller uses `AzureCliCredential`;
  container uses platform identity through Azure Identity with developer/interactive
  credential sources disabled. Foundry gateway owns caller authentication.

## Sequence

Each action writes a new dated JSON receipt under `records/`; stdout prints its path.
Use actual receipt filenames printed by preceding commands, not literal placeholders.

```bash
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-hosted-agents/deploy/deploy.sh preflight
bash testbeds/foundry-hosted-agents/deploy/deploy.sh install --target /home/hanchoong/.local/lib/python3.12/site-packages --reviewed-lock b7c69b84c5ae3ccb14d97e5da8e04ea92680190842a723a776321501add65851 --dry-run
bash testbeds/foundry-hosted-agents/deploy/deploy.sh grant-pull
bash testbeds/foundry-hosted-agents/deploy/deploy.sh build
bash testbeds/foundry-hosted-agents/deploy/deploy.sh deploy --receipt <build-receipt> --previous <current-owned-deploy-receipt>
bash testbeds/foundry-hosted-agents/deploy/deploy.sh invoke --receipt <deploy-receipt> --tool nonce_statistics
bash testbeds/foundry-hosted-agents/deploy/deploy.sh verify --receipt <invoke-receipt>
bash testbeds/foundry-hosted-agents/deploy/deploy.sh invoke --receipt <deploy-receipt> --tool nonce_digest
bash testbeds/foundry-hosted-agents/deploy/deploy.sh verify --receipt <old-tool-invoke-receipt>
bash testbeds/foundry-hosted-agents/deploy/deploy.sh inspect
```

Skip install/grant when preflight already passes. Omit `--previous` only for initial
creation when name is absent; it is mandatory now because this agent already exists.
Build/deploy are deliberate billable release actions, not idempotent reads. Preserve
accepted baseline before editing the tool configuration/script for a new version.

| Action | Expected output and effects | On failure |
| --- | --- | --- |
| `test` | `complete`, tests and source manifest; offline only | Repair same slice; no build |
| `install` | Reviewed hash-locked uv dry-run/install at explicit existing user-site | Additions/replacements refuse without exact recovery; no global repair |
| `grant-pull` | Exact approved principal/registry AcrPull grant and readback | Refuse changed identity, mode or role semantics |
| `preflight` | `complete` only when dependencies/targets/pull role match; Azure reads only | Resolve named prerequisite with separate install/grant authority |
| `build` | Billable ACR build; allowlisted source archive, immutable image digest | Retain archive; inspect ACR operation before retry, never assume timeout means no build |
| `deploy` | Creates owned Hosted Agent version; waits for active image/metadata match | Foreign/existing name without prior receipt refuses; inspect unknown operations before retry |
| `invoke` | Requires exact active version; anonymous refusal, one authenticated proof, stored response ID | Pending version refuses; inspect status before retry. No repeated inference automatically |
| `verify` | Read-only version and stored-response retrieval; same source/config/tool evidence | Missing/changed evidence is failed acceptance, not success |

Safe reruns: test/preflight/inspect/verify append evidence; exact grant is a no-op.
Build appends a source archive; deploy creates an immutable version only with explicit ownership.
Invoke creates
one new synthetic stored response per deliberate invocation and incurs limited inference;
it is not a free/idempotent read. Successful `deploy` requires active exact-image readback.
No unbounded poll or retry loop. Agent remains retained; teardown is separately authorized.

Container uses official Responses protocol v2 on port 8088. Build context contains only
allowlisted app files, canonical source/metadata, pinned wheels, dependency manifest,
Dockerfile and hash lock.
No copied credentials, repository history, private datasets or environment directories.
Package installation inside the explicitly requested image build is declared in Dockerfile;
local installation requires the explicit action. Image records `installed-packages.txt`
and `installed-locations.json`, runs `uv pip check` and existing compatibility smoke.
Official uv/Python images are digest-pinned; image installation is offline and hash-locked.
Changed images have not been built or piloted in F01; F08 owns that acceptance.
Accepted historical images remain unchanged.

## Locked Profiles

[Runtime lock](runtime-requirements.lock) and [host lock](host-requirements.lock)
resolve 98 packages from canonical wheel metadata and installed-version constraints.
[Manifest](dependency-manifest.json) pins runtime wheel hashes, source and images.
H host profile also supplies E client dependencies. O owns its loader-bearing profile.
Legacy hosting adapter and umbrella MAF package are excluded, not uninstalled globally.
The current target dry-run proposes six shadows of unchanged system versions;
non-dry installation refuses these until exact recovery is separately reviewed.
Existing imports already satisfy the selected profile; no runtime mutation is needed.

F01 preparation and primary evidence:
[procedure](../../../deploy/remediation-evidence/20260922T154800Z-f01/packages.py),
[profile verification](../../../deploy/remediation-evidence/20260922T154800Z-f01/profile-verification.json).
Run from repository root with `/usr/bin/python3` and an explicit procedure action:
`inventory`, `build-dry-run`, `build-install`, `wheels`, `compile`, `artifacts`,
`finalize`, `verify`. Evidence outputs refuse overwrite; new preparation needs a new
evidence directory and review, not replay over historical files. `build-install`
is only the separately reviewed setuptools prerequisite, not runtime installation.
Do not rebuild canonical wheels merely to refresh their timestamps; retained hashes
are release inputs. Source changes require new wheels, locks, manifests and review.

Each successful image build executed real hosting SDK readiness/invalid-input and MAF
schema checks in that image. Actual remote model/tool execution and stored readback
then passed. SDK warns that in-flight response crash recovery is disabled; this
experiment proves completed response retrieval, not interrupted-work durability.

## Proof

Client sends JSON text with exact `tool` and fresh 32-hex `nonce`; plain nonce retains
original-tool compatibility. Host accepts only these synthetic inputs, runs canonical
MAF tool loop, and returns server-generated correlated `tool.call.ready`, `tool.started`,
`tool.result` events plus platform version and source/config hashes. Client independently
recomputes expected result. Model answer alone fails. Anonymous HTTP 401/403 required;
404, login page or arbitrary successful response does not count. `verify` retrieves stored
response and checks identical evidence. No private reasoning is captured.

Current receipts and measured gaps are linked in the
[specification](../../../specs/20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md).
Latest endpoint:
`https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry/agents/agentcraft-hosted-tool-proof/endpoint/protocols/openai/responses?api-version=v1`.
Foundry Entra authentication remains required. Version 3 is latest; versions 1/2,
images and sessions remain retained. Default provider idle timeout is 900 seconds.
No owned local process, worker or provider operation remains pending; cost unknown.