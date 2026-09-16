---
description: 'One deployment directory, one entry point, one documented sequence, no secret in the repository.'
applyTo: '**'
---

# Deployment

The test: someone who has never seen this repository, given only `deploy/README.md`, reaches a
running system without asking a question or inventing a value.

## The mandate

1. **One directory.** Everything needed to provision, release, verify, tear down lives in `deploy/`.
2. **One entry point.** `deploy/deploy.sh` is the only thing an operator runs. A step existing only
   in shell history does not exist — add it to the script in the same change.
3. **One sequence, documented.** `deploy/README.md` lists the commands in run order with expected
   output and what to do when each fails.
4. **Idempotent.** Every command is safe to run twice.
5. **Verified.** `deploy.sh verify` proves the system is serving, from outside, and exits non-zero
   when it is not.
6. **Reversible.** `deploy.sh teardown` removes exactly what was provisioned.
7. **No secret in the repository.** Not in a script, env file, comment, or example.

## Targets and credentials

**Targets are configuration and belong in the repository.** Subscription and tenant IDs, resource
group, region, resource names, image tags. One file per environment, `deploy/env/<environment>.env`,
committed, read by `deploy.sh -e <environment>`.

**Secrets never enter the repository, the environment file, or a shell variable in a log.** In
order of preference:

1. **No secret at all.** A user-assigned managed identity with an Azure RBAC role assignment
   replaces connection strings, account keys, and client secrets for Azure-to-Azure access.
2. **Key Vault, referenced not fetched.** For a third-party credential that cannot be an identity:
   store it in an RBAC-authorized vault; the platform resolves the reference at runtime using the
   app's managed identity. The deployment script never reads the value.
3. **Never** `az keyvault secret show` piped into a variable, a file, or an image.

Operator auth: `az login` plus explicit `az account set --subscription`. CI auth: OIDC federated
credentials, never a client secret. Grant the narrowest role that works, scoped to the resource.

## Who is calling, and who is running

Three identities, routinely conflated:

- **The workload's own identity.** A managed identity is how the running application reaches other
  Azure resources. It authenticates no caller and authorizes no user.
- **The human.** A deployed application that runs or wraps a model sits behind tenant-scoped Entra
  sign-in. Its auth configuration fails closed. No `AUTH_ENABLED=false`, no bypass header, no
  auth-disabled copy claimed equivalent.
- **The agent.** A coding agent authenticates as itself through a request-signing credential
  separate from any human's: the private key reaches neither the repository, the image, nor a log.
  Installation generates no key and enables no agent access.

Both caller paths feed the same explicit authorization decision. Anything between client and
application — gateway, proxy, rewrite rule, platform auth layer — must preserve exactly what was
signed: the method, the raw path and query string before any normalisation, the body bytes, and the
signature headers. Prove it against the running deployment, not a local server.

Replay defence is scoped: an in-memory nonce cache defends one process. Across replicas the choice
— shared store, sticky routing, or a bounded window accepted in writing — is stated where the
verifier is configured.

## Preflight

`deploy.sh` fails loudly with the exact fix before it does anything: required tooling present; `az`
logged in with the active subscription equal to the environment file's; every required variable set
and non-empty; caller holding the roles the deployment needs; a refusal when a variable holds
something secret-shaped; a refusal when a variable would disable authentication; and a refusal when
one would enable agent access nobody asked for.

## Structure

```
deploy/
  README.md              the sequence, the resources, the failure playbook
  deploy.sh              the only entry point
  env/example.env        documented template, committed
  env/<environment>.env  real targets, committed, no secrets
  infra/main.bicep       declarative resources, idempotent by construction
  .gitignore             refuses obvious secret files
```

Prefer declarative infrastructure: a Bicep or Terraform definition applied by `az deployment group
create` is idempotent by construction and supports `--what-if`.
