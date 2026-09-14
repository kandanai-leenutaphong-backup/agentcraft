# Container Apps Authentication

Prefer [native Easy Auth](https://learn.microsoft.com/en-us/azure/container-apps/authentication)
for a new private frontend when its host requirements fit. It supplies sidecar-based
authentication, provider sign-in/session behavior and identity headers. Application
authorization, origin/CSRF policy and assurance about the configured edge still matter.

## Decide The Enforcement Point

| Caller/Host Requirement | Preferred Route | Required Evidence |
| --- | --- | --- |
| Private frontend and APIs, supported provider callers | Easy Auth with `RequireAuthentication` and a tenant-pinned provider | Positive sign-in plus refusal for anonymous assets/API/unknown paths, forged headers and wrong tenant |
| Headless caller with a supported provider token | Supported bearer/client-directed authentication | Correct audience, roles/scopes and refusal; headless does not mean anonymous |
| Custom application-verified signature | Explicitly reviewed application enforcement, or a separately routed protected surface | Default-deny gate, no direct-origin bypass, shared authorization, replay/tamper/expiry refusal across real replicas |
| Portable/secretless public-client flow or special session semantics | Supported MSAL/framework flow, or retained compatibility helpers after native comparison | Actual callback/CSRF/session/revocation parity; no silent fallback to disabled auth |

The older [setup sequence](container-apps-setup.md) is preserved for detailed command and
failure references. It is guidance for the consuming deployment entry point, not a script
the skill runs automatically. Keep ingress closed until the intended gate is configured
and negatively verified.

## Configure And Verify

1. Confirm target tenant/subscription, FQDN, app registration ownership and allowed callers.
   Select the correct web or SPA redirect platform and literal callback URI; these are
   not interchangeable. Registration restrictions require an authorized operator.
2. Pin the tenant issuer. Do not choose `common` or another tenant to evade policy.
   Directory registration, consent and Graph permissions are not implied by Azure RBAC.
3. Where the chosen provider configuration needs a client credential, use an operator-owned
   Key Vault reference and the identity permitted to resolve it. Never retrieve a secret
   into a shell variable, repository, build artifact or log. Verify rotation before retirement.
4. Choose the enforcement point deliberately. `AllowAnonymous` only defers the access
   decision; it is secure only with the reviewed in-app deny gate protecting all required paths.
5. Trust `X-MS-CLIENT-PRINCIPAL-*` only after proving forged inbound headers are stripped
   and no route reaches the origin without the trusted edge. Map identity once, then
   apply the host's record/route authorization policy.
6. Verify `/.auth/login/aad`, callback and logout with cache-busting browser requests.
   Check the actual API response type: a redirect returning login HTML is not an API 401.
   Keep sensitive responses and refusals private/no-store where the host owns those headers.

For custom signed access, load the separate `signed-dev-access` capability; do not copy a
second verifier here. Requests must preserve the signed method, raw path/query, body and
headers across proxies. A process-local nonce cache is not replica-wide replay defense.

## Acceptance Remains Pending

Operate the deployed frontend and API. Verify anonymous navigation/API, asset and unknown
paths, forged identity headers, expired and wrong-tenant/audience tokens, logout and
revoked cookies, callback state and flow replay, cross-origin unsafe requests, and custom
signature refusal where enabled. Verify provider credential references without exposing
values. Native-session lifetime/refresh behavior must be measured against the host's
requirements, not assumed from a documentation page.

The [offline planner](../scripts/workflow.py) validates a non-secret task configuration
and prints read-back commands. It makes no HTTP request, creates no app registration,
changes no auth setting and grants no authority. Example configuration:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "subscription_id": "22222222-2222-2222-2222-222222222222",
  "resource_group": "fixture-rg",
  "app_name": "fixture-app",
  "enforcement": "platform",
  "caller": "provider-token"
}
```
