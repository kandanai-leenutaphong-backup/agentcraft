# Optimization Workspace Frontend

React 19, strict TypeScript, Vite, CSS, Lucide icons. Four API-backed views:
comparison, run timeline, candidate evidence with SME feedback, experiment report.
No app fixture fallback, external fonts, model calls, or cloud operations.

## Local Commands

Run from `optimization_framework/frontend`:

```sh
npm ci
npm run typecheck
npm run build
npm run dev -- --port 5173
```

Vite proxies `/api` to `http://127.0.0.1:9020`, preserving browser Host/Origin.
The backend must accept the same-origin local operator request. No authorization
bypass or browser-auth shim is installed. Production output is `dist/`; assets
use root base `/`. The integrated server must serve `dist/index.html` at `/`
and `dist/assets/` at `/assets/`, alongside the fixed API routes.

## Browser Verification

Parent starts the integrated server; smoke test creates retained deterministic
runs and feedback through browser controls, then restores a passed candidate:

```sh
TEST_BASE_URL=http://127.0.0.1:9020 npm run test:smoke
```

`TEST_BASE_URL` is required. Smoke never starts or substitutes a backend. It
checks browser Origin, polling, four views, source diff, feedback author and
disposition read-back after reload, candidate/check links, confirmed restore,
JSON/CSV/HTML downloads, keyboard skip navigation and 390px mobile geometry.
Cancellation is reported as skipped if the run settles before cancellation;
that is not cancellation acceptance. Runs and feedback remain in that server.

Explicit isolated fixture verification:

```sh
npm run build
npm run test:fixture
```

This starts only `tests/fixture-server.mjs` at `127.0.0.1:19027`, serving built
assets and a **test-owned synthetic API fixture**. Port reuse is refused. The
fixture process is stopped by Playwright after the suite; state is in memory.
It additionally checks loading/empty/error recovery, contract mismatch refusal,
ambiguous-save idempotency, rejected Origin, restore/download refusal, shuffled
candidate ancestry and a successful response missing verified restore evidence.
Fixture browser results do not verify the real framework, real authentication,
model execution, process restart durability, or deployment.

Playwright 1.58.2 uses its installed Chromium browser. If absent, install the
matching browser with `npm exec playwright install chromium`. Screenshots,
downloads and failure traces are written under `test-results/` (ignored).
Screenshot names identify fixture versus integrated evidence.

## Contract And Limits

`src/api.ts` validates API JSON once with Zod. Routes and field names follow
`../API_CONTRACT.json`; unknown additive fields are ignored. Null measurements
stay unavailable, never zero. There is only one selectable executor:
`deterministic`. Every displayed run preserves the service's evidence class.

- Missing contract fields remain explicit: cohort denominator/success rate,
  failed-trial count, cost, architecture/version pins, phase intervals,
  screenshots, deployment/persisted-result identity, captured cases, thresholds,
  construction effort, handoff evidence, resource inventory.
- Polling rereads complete stored events every 1.8 seconds. The contract has no
  event cursor, pagination, streaming endpoint, or incremental sequence field.
- Feedback author comes from the service. The request has no author field;
  the UI neither invents attribution nor claims who authored a disposition.
- Restore requires a passed candidate, nonempty all-passed checks, explicit
  confirmation, selected-candidate read-back and a matching verified receipt.
  The API exposes no restore-operation identity to distinguish two receipts for
  the same candidate. Service remains the authorization owner.
- One in-flight mutation prevents duplicate clicks. Identical retries retain
  their idempotency key in memory until success; refreshing the page discards
  an unconfirmed request key. No automatic mutation retries occur.
- Synthetic deterministic evidence is not measured optimization improvement.
  Nonempty limitations remain visible in every selected-run view.

Runtime dependencies: React renders the workspace; Lucide provides named-control
icons; Zod rejects malformed contract records. CSS follows repository allowance
without introducing another styling framework.