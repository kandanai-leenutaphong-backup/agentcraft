
# Entra sign-in on Azure Container Apps

Gate a container app to one tenant's accounts, with an optional signed path for headless agents.
This skill supplies guidance, not a server or automatic tenant configuration. All commands belong
in the consuming project's authorized deployment entry point. Keep ingress closed until the
configured gate refuses unauthorized requests. Installation grants no tenant or cloud authority.

## Choose the enforcement point first

| | Platform enforces (`RequireAuthentication`) | App enforces (`AllowAnonymous`) |
| --- | --- | --- |
| Code | none | ~60 lines |
| Signed/agent access | **impossible** — request never reaches the container | supported |
| Risk | platform bug only | your bug serves the document |

Signed automation forces the second. Otherwise take the first.

## 1. Registration

Redirect URI needs the FQDN, which does not exist until the app is deployed. Deploy first.

```bash
FQDN=$(az containerapp show -g $RG -n $APP --query properties.configuration.ingress.fqdn -o tsv)
az ad app create --display-name "$NAME" \
  --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" \
  --enable-id-token-issuance true --query appId -o tsv
```

`--enable-id-token-issuance true` is mandatory; EasyAuth uses `response_type=code+id_token`. The URI
must be on the **web** platform — an `spa` entry does not satisfy it, and `web` does not satisfy
MSAL. Different features; do not cross them.

**If the tenant blocks registration** (`AADSTS530084`, conditional-access token protection, or an
interactive device-bound login unavailable headlessly), stop for an authorized operator. Do not
switch tenants to evade that policy. An operator-approved multi-tenant registration is a separate
decision: pin the issuer to the target tenant and obtain its required consent before use.

## 2. Secret

Credential creation and rotation are operator-owned. Put the credential in an RBAC-authorized
Key Vault through an approved secret-handling path; never read it into a shell variable, argument,
file or log. The application identity resolves the vault reference at runtime. URI and identity
resource ID below are non-secret configuration:

```bash
az containerapp secret set -g "$RG" -n "$APP" \
  --secrets "aad-client-secret=keyvaultref:$AAD_SECRET_URI,identityref:$IDENTITY_RESOURCE_ID"
```

The deployment must verify the reference resolves without exposing its value. Retire the old
credential only after the new configuration is verified. No live vault or sign-in result is implied
by this guidance.

## 3. Platform auth

```bash
az containerapp auth microsoft update -g $RG -n $APP \
  --client-id $APP_ID \
  --client-secret-name aad-client-secret \
  --issuer "https://login.microsoftonline.com/$TENANT_ID/v2.0" \
  --yes

az containerapp auth update -g $RG -n $APP --enabled true \
  --action AllowAnonymous        # or RequireAuthentication if no signed path is needed
```

`--issuer` with a tenant GUID is the access boundary. `common`/`organizations` admits every Entra
org.

## 4. In-app gate (only for `AllowAnonymous`)

Default deny. A trusted platform principal or a verified signature establishes identity; the
application's authorization policy separately decides access. `authorized` and
`verified_signed_principal` below are consumer-owned contracts, not implementations supplied by
this guidance:

```python
def allowed(request) -> bool:
  principal = trusted_platform_principal(request)
  if principal is None:
    principal = verified_signed_principal(request)
  return principal is not None and authorized(principal, request)

# browsers get sign-in, everything else gets a bare 401
if not allowed(request):
    if request.method in ("GET", "HEAD") and "text/html" in request.headers.get("accept", ""):
        return redirect(f"/.auth/login/aad?post_login_redirect_uri={path}", 302)
    return Response(status_code=401)
```

Trust `X-MS-CLIENT-PRINCIPAL-*` only after proving the configured platform strips forged inbound
values (test 3 below) and no direct-origin route avoids that edge. Otherwise validate tokens in
the application. Add `Cache-Control: no-store, private` to authorised responses.

Platform-owned endpoints: `/.auth/login/aad`, `/.auth/logout`, `/.auth/me`. Sign-out link
`/.auth/logout?post_logout_redirect_uri=%2F` clears the cookie, drops tokens from the store, and
signs out at the provider.

## 5. Verify — negatives are the test

```bash
U=https://$FQDN
curl -so/dev/null -w'1 anon api        %{http_code}\n' $U/
curl -so/dev/null -w'2 anon browser    %{http_code}\n' -H 'Accept: text/html' $U/
curl -so/dev/null -w'3 forged header   %{http_code}\n' -H 'X-MS-CLIENT-PRINCIPAL-ID: x' $U/
curl -so/dev/null -w'4 asset direct    %{http_code}\n' $U/assets/logo.png
curl -so/dev/null -w'5 unknown path    %{http_code}\n' $U/nope
curl -sL $U/.auth/login/aad | grep -o 'AADSTS[0-9]*' || echo '6 authorize page OK'
```

Expect `401, 302, 401, 401, 401`, no AADSTS code. **A gate proven only by successful entry is
unproven.** Also expire a token, replay a signature, tamper a signed path.

Browser checks use a **cache-busting URL** (`?cb=$RANDOM`): a browser that already loaded the page
serves it from disk cache after the session is cleared, which looks exactly like a broken gate.

## Gotchas

| Symptom | Cause / fix |
| --- | --- |
| `AADSTS530084` on `az ad app create` | CA token protection. Stop for an authorized operator; do not switch tenants to bypass policy. |
| `AADSTS50011` redirect mismatch | FQDN changed, or URI on the wrong platform (`spa` vs `web`). |
| 401 where you configured `RedirectToLoginPage` | Provider key did not resolve; observed unfixed by casing changes or revision restart. Issue the 302 from the app instead. |
| 503 right after enabling auth | Sidecar injecting; the replica is restarting. Re-probe after ~30s. |
| Site public between deploy and auth | Real exposure window. `az containerapp ingress disable` until auth is on, then re-enable. |
| Auth "works" but nobody can sign in | Consent required in the target tenant for a multi-tenant app. Needs admin consent. |

## Agent access without a browser

A custom signed request cannot pass a platform gate that rejects it before it reaches the
application. If an operator explicitly authorizes this extra caller path, use a supplied verifier
such as the optional `signed-dev-access` capability, with the same application authorization
decision as the human path. Do not invent a signature format or session cookie here.

Browser requests must be signed individually over their actual method, raw path/query and body.
Only the public verifier key reaches the server; an unset key disables that path. Prove tamper,
expiry and replay refusal at the running proxy boundary. A process-local nonce cache does not
prevent replay across replicas: choose shared replay storage, routing constraints, or an explicitly
accepted bounded window. This guidance does not bundle a verifier or promise headless sign-in.
