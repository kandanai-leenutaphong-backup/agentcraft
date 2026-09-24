# Deployment Runbook

`deploy.sh` is the only entry point. Run from the template root
(`template_apps/foundry_hosted_agent`). Offline `test` needs nothing; every other action
reads `env/<environment>.env` and the digest-pinned `env/<environment>.run.json`.

Status: offline-tested only. No command below has been run against Azure from this template.

## Before the first cloud action

1. Existing resources only: Foundry project with a system-assigned identity, a model deployment,
   an Azure Container Registry. This runbook provisions nothing and grants no role.
2. The project identity holds unconditional `AcrPull` on the registry (`preflight` checks; granting
   it is a separate, owner-authorized action).
3. `cp deploy/env/example.env deploy/env/<environment>.env`, replace every `<...>`. Set `model` in
   `app/configuration.yaml` to `MODEL_DEPLOYMENT`.
4. `cp deploy/env/example.run.json deploy/env/<environment>.run.json`; set `series`, `agent`, and
   `env_sha256` to `sha256sum deploy/env/<environment>.env`. Review it, then pin its digest:
   `SHA=$(sha256sum deploy/env/<environment>.run.json | cut -d' ' -f1)`.
5. `az login --tenant <tenant>` and `az account set --subscription <subscription>`. No key,
   token or connection string is used anywhere.

## Sequence

| # | Command | Writes | Success output |
| --- | --- | --- | --- |
| 1 | `bash deploy/deploy.sh test` | none | `{"status": "complete", "action": "test", ...}` |
| 2 | `bash deploy/deploy.sh preflight -e dev --manifest-sha256 $SHA` | none (reads) | `"status": "complete"`, receipt path |
| 3 | `... build -e dev --manifest-sha256 $SHA --authorize-cloud-write` | ACR build (billable) | receipt with `host/repo@sha256:...` |
| 4 | `... deploy -e dev --manifest-sha256 $SHA --authorize-cloud-write` | new hosted version | receipt with `version`, active read-back |
| 5 | `... invoke -e dev --manifest-sha256 $SHA --authorize-cloud-write [--input TEXT]` | inference, stored response, session | `response_id`, `output_text` |
| 6 | `... verify -e dev --manifest-sha256 $SHA` | none (reads, anonymous POST) | exact version, `anonymous_status` 401/403, stored responses |
| 7 | `... teardown -e dev --manifest-sha256 $SHA --plan` | none (reads) | every step `planned` |
| 8 | `... teardown -e dev --manifest-sha256 $SHA --authorize-cloud-write` | deletes owned responses, sessions, versions | outcomes `deleted`/`already-absent`, agent `absent` |

Every cloud action prints `{"status", "action", "receipt", "code", "seconds"}` and retains the
receipt under `records/<series>/`. Exit `0` complete, `2` refused or blocked.

What each stage does (all mechanics are `foundry_ops`):

- `build`: offline tests, `preflight`, then stages the exact allowlisted source (app, vendored
  `llm_interface`/`agentcraft_core`/`agentconfig`, Dockerfile, lock, `source-manifest.json`) and runs one
  server-side `az acr build`. Tag is the release label `sha256-<32 hex>`; output is digest-pinned.
- `deploy`: `project.agents.create_version` with the digest image and metadata
  `source_sha256`/`config_sha256`/`release`; waits active, reads back exact definition and metadata.
- `invoke`: one stored, version-pinned Responses call per release/version/input.
- `verify`: active exact version; anonymous POST must be 401/403; each stored response read back by
  raw GET, output equal to the invocation, metadata equal to the source/config/agent/version identity
  the container reports.
- `teardown`: stored responses, then sessions, then versions created by this series, then agent
  read-back. Any other order re-creates sessions that block version deletion.

## Idempotency and reruns

Each mutation writes an intent record before the call and a result record after it. A rerun reuses
results (`build`, `deploy`, `invoke` return the retained outcome). An intent without a result means
the outcome is unknown: the action refuses (`unresolved_intent`). Reconcile by read-back
(`preflight`, `verify`, `az acr task show-run`); never delete an intent to retry.

A new version of an existing agent needs a new run manifest with a new `series`,
`previous_version` (the current latest) and `previous_image`; the old series' records stay intact.

## Failure playbook

| Code in receipt or stderr | Meaning | Action |
| --- | --- | --- |
| `--authorize-cloud-write` / `--manifest-sha256` | missing explicit authority or pin | pass it deliberately |
| `env_placeholder`, `env_missing`, `env_format`, `env_unknown` | env file incomplete or wrong | fix `env/<environment>.env`, update `env_sha256`, re-pin |
| `env_secret`, `env_auth_disabled`, `env_agent_access` | secret-shaped or auth-weakening variable | remove it; use managed identity or Key Vault references |
| `manifest_digest`, `manifest_pin`, `manifest_action`, `manifest_fields` | manifest changed, env drifted, action not allowed | review, then re-pin |
| `record_exists` on `run-manifest.json` | series already bound to other bytes | new `series` |
| `account_mismatch` | active `az` account differs | `az account set --subscription ...` |
| `preflight_gaps` | project, registry, `AcrPull`, model or ownership gap | fix the named gap; this runbook grants nothing |
| `unresolved_intent`, `build_outcome_unknown`, `version_unknown` | prior write outcome unknown | reconcile read-only |
| `readiness_deadline` | version not active in 300 s | inspect with `verify`; do not redeploy |
| `anonymous_accepted` | endpoint answered without credentials | stop; treat as an auth incident |
| `identity_mismatch`, `version_readback`, `stored_response_drift` | serving image/config differs from the build | stop; inspect the version |
| `still-present`, `delete-failed` in teardown | eventual consistency or blocked delete | rerun teardown; results are recorded per step |

## Not done here

ACR image deletion, role grants, model deployment, network changes and evaluation/optimization
resources. Registry cleanup: `az acr repository delete` on the owned tag, separately authorized.
