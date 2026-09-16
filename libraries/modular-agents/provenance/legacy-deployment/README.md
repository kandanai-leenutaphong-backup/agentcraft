# Foundry Hosted Agent Operations

One entry point: `bash deploy/deploy.sh`. Commands below run from the skill root.
This adapter deploys into an **existing** Azure Foundry account/project with the
hosted code-upload protocol available. It does not provision those resources,
enable a preview feature, create a model deployment or grant itself operator rights.

The source protocol uses Python 3.13 and invocations 2.0. Current live availability
in your region/project is unverified by this migration. Obtain authorization for
the target and possible costs before running any live step.

## 1. Install And Check Offline

```bash
uv sync --locked --no-default-groups --extra dev
.venv/bin/python tests/selftest.py --copy-out
bash deploy/deploy.sh plan
bash deploy/deploy.sh build
```

Expected: passing selftests, `cloud_calls:false` in the plan, and a JSON build
result containing `artifact`, `artifact_id`, `zip_sha256`, `tools`. The example
permits only its two offline note tools; model execution and every cloud mutation
remain denied. Failure before build means fix the named configuration, tool
schema, source package or lock, not cloud RBAC.

Dependencies download once into this skill's environment. For read-only plugin
installation paths, set `UV_PROJECT_ENVIRONMENT` to an operator-managed directory
outside the package. Explicit `--output-dir` can likewise move local artifacts.

## 2. Declare One Environment

Create `deploy/env/<name>.env` from [env/example.env](env/example.env), and a
corresponding JSON policy from [env/example-policy.json](env/example-policy.json).
Commit non-secret target coordinates; keep receipts and generated artifacts out
of version control. Every environment key is required:

| Key | Value |
| --- | --- |
| `SUBSCRIPTION_ID` | subscription containing the approved target |
| `TENANT_ID` | tenant used by the operator and target |
| `FOUNDRY_ACCOUNT` | existing account DNS name |
| `FOUNDRY_PROJECT` | existing project name |
| `FOUNDRY_RESOURCE_GROUP` | resource group owning the account |
| `AGENT_NAME` | exact agent name permitted by operator policy |
| `BUILD_CONFIG` | path to build JSON, relative to the environment file |
| `OPERATOR_POLICY` | path to policy JSON, relative to the environment file |
| `STATE_DIR` | persistent operator-owned receipt/artifact directory |

No shell expansion or variable interpolation occurs. Unknown fields, missing
values and secret fields are rejected. Model and data credentials do not belong
in this file, the build JSON, invocation JSON or the deployment artifact.

Edit the selected YAML agent's `model` to the **actual deployment name**, not a
model family label. In the build JSON set `runtime_target.model_endpoint` to the
account's approved `https://<account>.openai.azure.com/openai/v1` or
`https://<account>.services.ai.azure.com/openai/v1` endpoint. Set
`runtime_policy.allow_model:true` only when inference is authorized. Grant exact
tool names individually; the agent YAML cannot enlarge that policy.

## 3. Authenticate And Review Permissions

The operator signs in directly, outside the agent conversation:

```bash
az login --tenant <TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
bash deploy/deploy.sh -e <name> plan
```

These are authentication prerequisites; every provision/release/verify/teardown
operation still goes through `deploy.sh`. Live preflight reads `az account show`
and refuses the wrong subscription, tenant, or non-user login. Tokens are acquired
by Azure Identity and never printed. Operator role sufficiency cannot be proved
offline; a live 403 stops with an operation/status, not a permissive retry.

Required operator permissions: Foundry agent read/write for deployment, invoke
permission for verification/chat, and role-assignment read/write/delete at each
declared scope only when grant automation is approved. Obtain those permissions
through the target owner's process; this script does not assign them to itself.

The runtime instance identity needs its own data and inference grants. Supported
automated roles are exact-scope ARM grants only:

```json
{
  "role": "Cognitive Services OpenAI User",
  "scope": "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>"
}
```

Add such entries to `grants` in the **operator policy**, and set
`allow_role_changes:true` only with explicit authorization. Search uses the exact
service scope; Blob uses a specific container. Cosmos SQL, Kusto and SQL database
permissions are different planes and must be configured/verified separately.
No automatic provider or broad role substitutes for them.

## 4. Build And Deploy

Set the exact `allowed_agents` list and `allow_deploy:true` in the reviewed policy.
Set `allow_update:true` only for replacing a previously receipted deployment.
Then:

```bash
bash deploy/deploy.sh -e <name> build
bash deploy/deploy.sh -e <name> deploy --artifact <artifact-directory> --confirm
bash deploy/deploy.sh -e <name> verify --artifact <artifact-directory>
```

Use the exact `artifact` directory printed by build. No files are copied into a
consuming application. Upload consists of the flat zip plus metadata; the
client receipt and grant policy are not uploaded.

Expected: receipt reaches `active`; verify reports `verified:true`, the exact
version, runtime source digest and declared policy/model. Every grant is read
back at exact scope. The CLI uses one exclusive receipt lock; do not run another
deployment tool against the same agent concurrently.

`active` means runtime readiness and read-back passed. It does **not** mean a
model or data query succeeded. The step below establishes the required behavior.

## 5. Invoke And Read Back

Set `allow_invoke:true` only for approved tool/model execution. The example call
is an offline fixture even when its container is hosted:

```bash
bash deploy/deploy.sh -e <name> invoke --request examples/call.json --confirm
bash deploy/deploy.sh -e <name> invoke --request examples/chat.json --confirm
```

The second command requires runtime model permission and incurs inference cost.
Expected: call returns the Hosting note; chat returns a terminal `done` result
with a tool result and evidence-grounded answer. A mocked/offline answer is not
live acceptance. Use an application-specific read-only probe when replacing the
fixture backend with real data, and test the matching denied operation.

Read back a chat by submitting `{"op":"result","turn_id":"example-turn"}`
through the same `invoke` command. Consumer sessions are derived from the verified
operator identity; maintenance uses a different namespace. Results do not survive
session/process restart and are not a durable audit log. Use a new turn id for a
new request; duplicate ids are refused, not billed again by this runtime.

## Failure Recovery

| Failure | Required response |
| --- | --- |
| Policy denies action | Review the plan and authorization; do not widen policy implicitly |
| Existing agent has no receipt | Stop; establish ownership rather than overwrite |
| `uploading` receipt has no version | Outcome is ambiguous; inspect live version/source and reconcile receipt under operator review; do not blindly repost |
| Remote version `failed` | Read platform build diagnostics; check Python/runtime availability, flat layout and declared dependencies |
| Warm returns 403 | Correct caller permissions/session ownership; this is not a cold-start retry |
| Repeated 409/424 | Bounded warm retries; deadline failure remains failure |
| Grant read-back fails | Keep receipt and identity; reverify or teardown recorded pending grant |
| Model/data 403 after grant exists | Distinguish exact role/scope from propagation; grant read-back is not data-plane success |
| Wrong runtime digest or version | Stop; do not claim the earlier artifact passed |
| Revoked grant still visible | Teardown stops before deleting identity; retry after observing propagation |

No exception response includes token values or raw upstream bodies. Keep operator
logs and backend errors free of credentials as well.

## 6. Roll Back Or Tear Down

Rollback is an authorized update using a retained prior artifact, followed by
the same verify and live acceptance commands. It creates a new version rather
than rewriting an immutable artifact.

For teardown set `allow_delete:true`, retain role-change permission for any owned
grant revocation, then:

```bash
bash deploy/deploy.sh -e <name> teardown --confirm
```

Expected: created grant assignments read back absent, then the exact recorded
agent reads back absent, receipt `state:deleted`. Repeating teardown is safe.
Changed versions or identities stop deletion. Pre-existing assignments are not
removed; external grants are not swept. Account, project, model deployment,
resource group and tenant identities are not removed by this command.

## Local Extracted Runtime

The socket selftest operates the real HTTP adapter without Azure. For a manual
local run, extract `agent.zip` into an empty directory, install its locked
requirements into a dedicated environment, and start `python main.py` there.
Set `MODULAR_AGENTS_LOCAL_TOKEN` through your own shell/environment, without
showing its value to an agent or storing it in the repository. The process binds
loopback, reads `PORT` (8088 by default), and requires `Authorization: Bearer ...`
for every invocation. Do not set Foundry platform markers to avoid local auth.

## Refresh Runtime Pins

After a reviewed dependency change, regenerate from this skill root:

```bash
uv lock
uv export --locked --no-default-groups --no-emit-project --no-hashes --no-header \
  --output-file modules/foundry-hosted-agents/hostedagents/runtime/requirements.txt
uv sync --locked --no-default-groups --extra dev
.venv/bin/python tests/selftest.py --copy-out
```

Commit metadata, lock, generated pins and source together. Custom tools needing
extra third-party dependencies must supply their own fully pinned requirements
closure and pass the extracted-artifact check under those dependencies.