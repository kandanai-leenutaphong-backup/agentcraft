# Azure RBAC SDK Comparison

**Verified offline first increment, 2026-09-14. Not a production adapter or a published
package.** The [comparison suite](test_rbac_sdk.py) exercises the real Azure SDK through
an in-memory ARM transport with synthetic credentials; socket connections are forbidden.

## Reuse And Dependencies

The suite imports the existing installed `azaccess` package through its public API.
`AccessManager` still owns policy, confirmations, verification and ownership-aware revoke;
those rules were not copied. The test-only `SdkRbacProbe` supplies native SDK operations.
The baseline provider and SDK probe run the same fixture lifecycle for comparison.

Resolved through the root `access-comparison` development group and
[workspace lock](../../../uv.lock):

| Component | Observed Version |
| --- | --- |
| uv | `0.9.30` |
| Python | `3.11.14` |
| `azure-access-management` | `1.1.0`, installed from the existing local skill owner |
| `azure-mgmt-authorization` | `4.0.0` |
| `azure-core` | `1.41.0` |

These are observed development versions, not declared minimum supported runtime ranges.
Azure Identity is not exercised here; the injected credential returns only a synthetic
test value. No sign-in, role grant, service call or real credential is used.

## Run

From `libraries/`, using the existing owner and registry packages already resolved by uv:

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.venv-access-comparison" uv sync --locked --only-group access-comparison
UV_PROJECT_ENVIRONMENT="$PWD/.venv-access-comparison" uv run --locked --only-group access-comparison python -B -m unittest discover -s azure-access-management/tests/comparison -v
```

Observed: **11 tests passed**. The existing access source self-test was also run using
this environment: **271 checks passed, 0 failures**. That baseline is separate evidence;
it does not mean all 271 checks exercise the SDK adapter.

## Observations

- SDK and existing provider complete create, exact read-back, revoke and verified absence
  with matching ownership/result states; the SDK serializes the declared principal type.
- Out-of-scope inspection refuses before the credential or SDK transport is invoked.
- Read-only policy prevents mutation. Wrong-plan and reused confirmations cause no SDK call.
- An inherited assignment does not satisfy an exact-scope declaration.
- A `409` race is adopted with its observed id and is not eligible for implicit deletion.
- Accepted create, missing response evidence and a lost write response retain the requested
  target id without retrying or claiming creation ownership.
- Accepted deletion retains ownership evidence; a failed read remains unknown.
- A foreign-origin continuation is refused before another send; repeated pages hit the
  comparison's two-page limit. SDK retries and redirects are disabled for this probe.

## Remaining Gates

The probe deliberately binds one synthetic subscription/resource, uses a fixed assignment
name, bounds pages rather than aggregate output bytes, and has no production configuration
surface. It must not be imported as a supported provider. No live Azure result is implied.

Before promotion: cover policy/tenant/role and condition parity across all relevant paths;
malformed/oversized results and exact response identity; time, item and byte budgets;
real credential lifetime and SDK challenges; supported clouds; SDK failure taxonomy;
full ownership-ledger and concurrency behavior; deliberate retries and dependency ranges.
Run existing consumers against an independently installed canonical package, then retire
only approved superseded implementations. Graph async compatibility and other planes remain
separate work. Existing CLI/MCP tools and skill implementation are unchanged.
