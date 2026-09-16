# Azure Hillclimber Writeup

Vocs documentation site, bundled GridIQ kiosk demo, and dataset-preparation example.
Imported from `/home/hanchoong/1_capabilities/hillclimber/app_writeup` on 2026-09-16.
This directory is the working copy; the original tree is retained unchanged as rollback.
No Azure resource, image, access grant, or authentication setting was changed during import.

## Local Development

Requires Node.js 22 and Python 3. Run from the repository root:

```bash
cd doc_app
npm ci
npm --prefix demo/app/frontend ci
./deploy/stage_demo.sh
npm run build
npm run preview
```

Production-output preview: <http://127.0.0.1:5179>. For live editing, run
`npm run dev` at <http://localhost:5178>.
Use the built preview for identity-script and sidebar-dock behavior: Vocs development
mode does not reproduce the post-build injection. Preview is loopback-only content
rendering, not a test of deployed authentication. Do not expose it publicly.

Re-run `./deploy/stage_demo.sh` after demo-source changes, then `npm run build`.
The kiosk uses bundled data; no backend, model call, Azure login, or production env file
is needed to build it. Dependencies and generated demo/site bundles are not committed.

## Capability Owners

| Outcome | Owner And Source | Public Surface | Dependencies And Verification |
| --- | --- | --- | --- |
| Read the writeup | This app: `docs/`, `vocs.config.ts`, `scripts/postbuild.mjs` | Site routes configured in Vocs | React/Vocs; `npm run build` |
| Run the bundled kiosk | This app: `demo/app/frontend/` | `/demo/`; static demo entry point | React/Vite and bundled fixtures; `./deploy/stage_demo.sh` |
| Inspect the labeled AEMO case | This app: `dataset_prep/`, `docs/pages/dataset-prep.mdx` | Case JSON, validation/sync scripts, `/dataset-prep` | Committed public source; checks below |
| Serve protected content | Runtime: `deploy/app/`; hosting: repository-root `deploy/` | Container App HTTP routes; root `deploy/deploy.sh writeup` | Starlette, tenant-pinned Entra authentication, existing signed-agent access; [deployment runbook](../deploy/README.md#writeup-deployment) |

Existing app implementations are retained; no shared-library migration is included.
The root deployment owner configures the new host and documented ID-token-only sign-in mode.
Configuration enters through Vocs, the kiosk build, or
deployment tooling. The protected server, not the static preview, owns reader access.

## Checks

From `doc_app/`:

```bash
node dataset_prep/scripts/validate.mjs
node dataset_prep/scripts/validate.mjs --self-test
node dataset_prep/scripts/sync.mjs --check
```

With the built preview running:

```bash
cd demo/app/frontend
node ../../../dataset_prep/scripts/verify-rendered.mjs http://127.0.0.1:5179/dataset-prep
```

Dataset provenance and regeneration commands live in [dataset_prep/README.md](dataset_prep/README.md).

## Deployment And Import Scope

Live: **https://ca-agentcraft-writeup.wonderfulmoss-6cbdac9f.eastus2.azurecontainerapps.io**.
The writeup now runs alone in `rg-agentcraft-testing`, with its own Container Apps environment,
ACR and image-pull identity. The bundled demo is static content in that same container; no model,
database or other app was deployed. Human readers use Microsoft corporate sign-in.
The root [deployment runbook](../deploy/README.md#writeup-deployment) owns release commands,
current URL, authentication caveats and verification evidence. Signed content read-back and
desktop/mobile browser navigation pass; interactive employee sign-in remains unverified.

The former Azure deployment and all resources in `rg-singtel-ticket-poc` were deleted and
independently verified absent on 2026-09-16. Its URL is no longer a supported deployment target.
The local source and preview remain available.
The app's [historical deployment runbook](deploy/README.md) preserves prior image/auth
details; its `existing-writeup` CLI now refuses before any Azure call.

All authored files retain their relative paths beneath `doc_app/`: site content/assets,
demo source/tests, dataset sources/artifacts, and deployment code. The original copy
remains outside this repository. `node_modules`, build/cache outputs, local env files,
private-key formats, and nested agent configuration were excluded from transfer.
The demo's excluded production env file is not required by the kiosk build.
Legacy demo Azure env files also remain only in the original tree; their credential-named
fields are not imported. The old writeup env file is historical configuration only.
Public-source artifacts and existing provenance notices are retained.

Local production builds do not establish deployed-image/source parity or complete an
interactive Entra sign-in. No release or cloud teardown was performed during the original
import; the later authorized group retirement is recorded by the root deployment owner.
The subsequent deployment verifies the served index against the local build's SHA-256;
it does not claim exhaustive image/source equivalence or completed corporate sign-in.
The inherited demo is desktop-oriented: it renders at mobile width but clips some controls
inside its three-column layout. Responsive redesign is not part of this import.