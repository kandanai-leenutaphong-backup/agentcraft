# Authority, Versioning And Recovery

## Autonomous Authority

**OF-12 Scoped autonomy.** The intended operator experience grants a fresh overseer enough
authority to provision, deploy, test and optimize without repeated approvals inside the
agreed scope. Actual targets and limits MUST be machine-readable before execution. This
specification does not provision credentials, grant RBAC, or authorize a current cloud run.

Provisioning/deployment authority is distinct from permission to act on customer assets.
Task authority must separately identify allowed operational actions and required approvals.
Read-only tasks need no physical-action recovery plan; consequential tasks must establish
appropriate simulation, constraints and escalation before action.

Authority manifest fields:

- Actor identity and credential references, authorized tenant/subscription and resource groups.
- Allowed services, regions, operation types, roles available, resource naming/ownership tags,
  shared protected resources and explicit policy for provisioning new groups.
- Repository writable paths, evaluator exclusions, local process/network boundaries.
- Data read/write/processing scope, retention, model deployments and inference allowance.
- Request, concurrency, resource, runtime and monetary limits; expiry and stop policy.
- Creation, update, deletion, rollback and teardown permissions separately stated; identity/RBAC
  mutation requires explicit inclusion, never inferred from permission to create an app.
- Cleanup owner, retained resources, backup locations and escalation contact/mechanism.

Preflight verifies effective access and selected target without displaying secrets. It reports
unsupported enforcement. Azure budget alerts are not hard caps; request/resource bounds and
deadlines restrict work, while delayed billing remains a disclosed limitation. Unknown spend
does not mean zero. Full task-resource authority never includes evaluator/audit ownership.

Managed identity and native caller authentication remain distinct. Tenant sign-in and
application record authorization must survive deployment. Agent signing credentials stay
separate from human credentials. Preserve replay protection across the selected replica model.
Use official/native infrastructure tooling through the deployment owner's entry point.

## Discrete Versions

**OF-13 Recoverable versions.** Every candidate manifest links these layers:

| Layer | Version and restore evidence |
| --- | --- |
| Source | Baseline commit or immutable source snapshot, candidate patch/commit, dependency locks and diff; isolated worktree/branch per experiment where suitable |
| Agent | Prompt, tool selection, schema, policy and implementation/build digests; immutable authored version and assignment revision |
| Build | Retained package/container digest and build provenance; restore exact artifact without a fresh build |
| Deployment | Infrastructure/config version, target inventory, release receipt, previous known-good artifact and read-back |
| State | Schema compatibility, owned namespace, backup/checkpoint and verified restore procedure before risky mutation |
| Framework | Runner, skill, adapter, evaluator and metric versions used to produce the result |

Do not require a commit in a user's active worktree. Snapshot approved dirty/untracked inputs
without secrets and preserve user changes; fail if the baseline cannot be captured faithfully.
Git branches track code, not database contents, cloud state, credentials or running images.
Retention policy protects known-good artifacts and required backups until replacement recovery
is verified. Garbage collection cannot delete evidence needed by retained runs.

## Restore Protocol

1. Select a known-good manifest and verify ownership, artifact availability and state compatibility.
2. Stop new candidate work; settle writers and reconcile ambiguous external operations by read-back.
3. Record restore intent and expected current target revision; refuse racing target changes.
4. Restore configuration/agent assignment and exact executable artifact through the owning adapter.
5. Restore data only with explicit authority and a tested, compatible checkpoint. Never overwrite
   post-checkpoint user data implicitly. Prefer isolated experiment state and reversible migrations.
6. Verify readiness, deployed digest, authorization/refusals and representative persisted output.
7. Persist restore result and timings; retain failed candidate evidence and resource inventory.

Restoration is a new event, not history deletion. Restored does not mean validated until the
checks pass. Failed restoration leaves an explicit degraded target and blocked promotion.
Irreversible changes require a separately authorized migration/recovery plan before mutation;
otherwise the experiment refuses. A Git checkout alone never satisfies rollback acceptance.

Software restoration does not reverse real-world consequences. For operational actions,
record any separately authorized compensating action and verify its outcome; explicitly
state effects that cannot be reversed. Never label an asset or service consequence undone
merely because the previous application image is running.

## Resource Lifecycle

Each run inventories created/borrowed resources and tags owned cloud resources. Teardown
removes only inventory-confirmed, authorized run-owned resources; shared infrastructure is
untouched. Verify absence by read-back and report surviving resources and possible charges.
Cleanup failures remain visible even when application acceptance passed. Cancellation/crash
must leave enough durable intent for a new supervisor to reconcile external effects safely.

Deployment sequence: local acceptance, authorized plan/preflight, build immutable artifact,
protected release, external authenticated verification, stored-result read-back, rollback drill,
and resource reconciliation. Local success and HTTP 200 alone do not certify deployment.

The framework and Investigation each keep one deployment directory and entry point. Target
configuration is committed without secrets; secret values are never copied into manifests,
images, reports, notebook notes or environment files. Historical grants are not fresh authority.