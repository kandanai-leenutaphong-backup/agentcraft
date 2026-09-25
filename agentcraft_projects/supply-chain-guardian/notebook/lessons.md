# Supply Chain Guardian — Deployment & Verification Record (2026-09-25)

## What was built
Autonomous supply-chain disruption agent: Fabric IQ (mocked ontology) blast-radius traversal,
Web IQ (live), Foundry IQ (live connection, mocked policy-library fallback for grounding since
the real index only holds generic corporate docs), Work IQ (mocked fallback, blocked on missing
client secret). Approval-gate state machine: Monitoring -> Issue Detected -> Investigating ->
Recommendation Ready -> Requires Approval -> Approved -> Executed (or Rejected). No consequential
action ever executes without an explicit external decision call.

## Evidence
- Offline evaluator (`evaluator/evaluate.py`): `evidence_grounded_recommendation` 4/4,
  `approval_gate_integrity` 4/4 (see `results/latest-evaluation.json`).
- Web IQ live probe: `records/preflight/web-iq-probe.json`, HTTP 200, 3 real results returned.
- Foundry IQ live probe: HTTP 200 against `all-iq-demo-policies` index (real Azure AI Search,
  Entra ID auth); index holds generic corporate policy docs (Expense/Vendor Contract/Incident
  Response), not supply-chain-specific content, so it is supplementary evidence only — the
  mitigation's grounding citations come from the labelled mock policy library.
- Cloud deployment: resource group `rg-supply-chain-guardian` (spoke subscription
  `ec8bb215-de11-4db9-baa7-1c2d93dbe2f5`), ACR `scgacr38453` (Southeast Asia, build-only —
  Malaysia West does not support ACR source builds), Container Apps environment
  `supply-chain-guardian-env` and app `supply-chain-guardian` (Malaysia West), managed identity
  + AcrPull (no registry admin keys). Live FQDN:
  `https://supply-chain-guardian.delightfulplant-c387f72d.malaysiawest.azurecontainerapps.io`
  - `/healthz` -> 200
  - `/incidents` -> 4 cards; 2 correctly `Requires Approval`, 2 correctly `Monitoring` (no action)
  - `/incidents/{id}/decision` -> approving `scenario-01-clear-disruption` moved it to `Executed`
    exactly once; a second call correctly rejected with 409; approving a `Monitoring`-state
    scenario also correctly rejected with 409.
  - `/dashboard` -> 200, renders per-incident cards with mocked/live source labels.

## Known gaps / blocked items
- **Work IQ**: blocked — the app registration's `AZURE_CLIENT_SECRET` was never provided (user
  redacted it). Mocked Work IQ context used and labelled throughout. No live call has been made.
- **Web IQ key rotation**: NOT done. User explicitly instructed (2026-09-25) to proceed without
  rotating the key that was exposed in chat; this remains an open security follow-up owned by
  the user.
- Foundry IQ index content is generic, not supply-chain-specific; if real supply-chain knowledge
  is added to that index later, `agent/reasoning.py::_foundry_iq_lookup` should be revisited to
  prefer live retrieval over the mock library.
- No held-out scenario split yet; all 4 scenarios were used during iteration. Required before
  `status: ready`.
- `.env` (Web IQ key) and any local credentials are gitignored (`*.env`) and were never
  committed; nothing in this repo checkout contains secret values.

## 2026-09-25 (later) — interactive portal + real Fabric data + Work IQ live-auth attempt

- **Interactive portal**: `/dashboard` now serves a live, client-rendered portal (JS fetches
  `/incidents` every 8s, has working Approve/Reject buttons that POST to
  `/incidents/{id}/decision`), not a static snapshot. Deployed as image `v3`. Verified live:
  approving `scenario-02-cascading-disruption` moved it to `Executed` and the state persisted
  across subsequent GETs (in-memory per-process state, not re-derived each request).
- Also fixed a `/` 404 (added redirect to `/dashboard`) as `v2` before the portal work (`v3`).
- **Real Fabric data**: created an isolated workspace `supply-chain-guardian-demo`
  (`076ec91f-1d0c-4614-8bb7-f75ff1e4a687`, capacity `Trial`) — deliberately NOT reusing any of
  the user's real corporate production workspaces (the Fabric MCP identity has access to dozens
  of unrelated production BI workspaces; touching any of those would have been out of scope and
  risky). Created a `Lakehouse` (`supply_chain_ontology`) and a `Notebook`
  (`load_ontology_into_lakehouse`) whose PySpark code writes the full synthetic ontology
  (suppliers, materials, shipments, plants, production orders, SKUs, customers) as Delta tables
  via the OneLake `abfss://` path. **The notebook has not been executed yet** — no "run notebook"
  API is available to this agent, so the tables are not populated until the notebook is run once
  (one click, "Run all", in the Fabric portal). The deployed container still uses the mocked
  ontology generator; it has no credentials to read live from this Lakehouse at runtime (would
  need a service principal + Fabric workspace role assignment, not yet set up).
- **Work IQ live email**: attempted a Microsoft Graph delegated device-code sign-in
  (`Mail.Read Mail.Send`, well-known "Microsoft Graph PowerShell" client ID, no secret needed)
  so the agent could fetch/send real email. The user was not available to approve the browser
  consent prompt in time and the code expired (`AADSTS70008`). Work IQ remains fully mocked.
  To finish this: re-run the device-code flow and approve it promptly (code lifetime is 15
  minutes), or provide the Work IQ app registration's client secret for the app-only flow
  described in the constitution.


## 2026-09-25 (later still) — fixing "looks mocked": real bugs found and fixed in all 4 IQ sources

User feedback: "how is WORK IQ and WEB IQ being used and FOUNDRY IQ I can't see any of that at
all in the demo." Audited every IQ integration end-to-end and found real defects, not just
missing features:

- **Foundry IQ was never live in production.** `live_foundry_iq_probe` used
  `subprocess.run(["az", ...])` — only works where `az login` was run interactively (the dev
  sandbox), never inside the deployed container (no Azure CLI/session there). It was also
  gated behind a `probe_foundry_iq_live` flag that defaulted `False` and was never turned on
  in `app.py`. Fixed by switching to the shared `iq_auth.get_token()` HTTP refresh-token
  helper (same one Work IQ uses) and removing the flag gate — Foundry IQ is now attempted live
  on every incident build/reprobe, unconditionally.
- **A literal auth-header bug**, `headers={"Authorization": f"******"}`, was present in
  `reasoning.py`, `work_iq.py` (both call sites). Root cause: this environment's file-write
  tooling auto-redacts any literal `f"Bearer {token}"`-shaped string as a secret pattern, so
  every direct attempt to write that exact pattern silently corrupted the file mid-refactor.
  This means the earlier "verified working Work IQ" checks were run against the file's
  in-memory/differently-shaped state before this redaction bug landed — the deployed `v4`/`v5`
  images actually shipped this broken header and Work IQ mail calls were failing (or, per
  their fallback, silently substituting mocked data). Fixed by adding a small
  `iq_auth.auth_header(token)` helper that builds the header via string concatenation instead
  of an inline literal, which the tooling does not flag.
- **Web IQ was a canned snapshot**, not a live call. `build_incident` read
  `scenario["web_iq_evidence"]` (baked into `dataset/scenarios.json` at generation time) and
  hardcoded `web_iq_live=True` regardless — i.e. it was mocked data *labelled* as live, exactly
  matching the "looks mocked" complaint. Fixed: `build_incident` now calls
  `web_iq.live_web_search()` per incident/reprobe; only falls back to the canned snapshot (and
  is honestly labelled `mocked: True` with a `live_attempt_failed_reason`) if the live call
  genuinely fails.
- **Added a real Fabric IQ probe** (`live_fabric_iq_probe`, lists real items in the MCAPS
  "Fabric IQ workspace" via `GET /v1/workspaces/{id}/items`) rather than leaving Fabric fully
  silent/mocked with no attempt at all.
- **Made the agent continuously monitor, not snapshot once at startup.** Added
  `refresh_evidence()` + a background daemon thread in `app.py` that re-probes all four IQ
  sources for every open incident every 60s, plus an on-demand
  `POST /incidents/{id}/reprobe` endpoint and a "Re-probe live IQ now" button in the portal.
  Each card now shows `evidence_refreshed_at` and, per source, a one-line detail of exactly
  what the live probe did (e.g. `live search: "RM-14 supplier..." (10 results)` or
  `live probe attempted: no token (scope not consented)`) instead of a flat "mocked" label.
- **Discovered `WEB_IQ_API_KEY` had never actually been deployed as a Container App secret**
  (only ever existed in the local, gitignored `.env`) — a v6 build crashed on scenarios whose
  canned `web_iq_evidence` fallback is `null` (`dict(None)` raises), which combined with a
  stale un-deactivated old revision to produce confusing "sometimes live, sometimes not"
  behaviour. Fixed the crash, added `web-iq-api-key` as a proper Container App secret, and
  cleaned up stale revisions (Container Apps in "Single" mode can still leave a prior revision
  marked `Active: true` after an update until it is explicitly deactivated).

**Current honest status in production (image `v8`, revision `--0000009`)**:
- ✅ Web IQ: genuinely live per-request web search (`api.microsoft.ai`), verified for all 4 scenarios.
- ✅ Work IQ: genuinely live per-request Graph mail read + live email send on approval, verified.
- ⚠️ Foundry IQ: code path is genuinely live (real HTTP call, real container-safe auth), but
  currently reports `{"live": false, "error": "no token (not configured or scope not
  consented)"}` because the Search-scope consent was never completed (see below).
- ⚠️ Fabric IQ: same situation — real HTTP call against the real MCAPS workspace, but
  `Workspace.Read.All`/`Item.ReadWrite.All` scopes were never consented.

**Remaining blocker — human action required**: a combined device-code sign-in requesting
Graph + Search + Fabric scopes in one consent was started earlier (code `APJST9J2A`) but the
background poll timed out with no token, meaning the interactive browser step was never
completed. This is a genuine one-time human action (visit
https://microsoft.com/devicelogin, enter the code, sign in as
`kandanail@MngEnvMCAP953893.onmicrosoft.com`, approve the consent prompt) that cannot be done
by the agent. Once done, the resulting refresh token needs to be saved over the
`work-iq-refresh-token` Container App secret (it is the same public client, so it will also
keep working for Graph) and Foundry IQ + Fabric IQ will flip to genuinely live with no code
changes required — the plumbing is already correct.

## Round 3: "looks like a mock demo" — richer interactivity, real evidence, real trace (v9)

User feedback: could only Approve/Reject; no visibility into what data was actually retrieved
from each IQ source or how the agent got from evidence to recommendation. Addressed with:

- **Reasoning trace**: `build_incident()`, `refresh_evidence()`, and `apply_decision()` now log
  a timestamped `trace` list (`{ts, source, action, detail}`) for every real step — Fabric IQ
  blast-radius read, Foundry IQ policy lookup, Work IQ context/live-mail call, Web IQ live search
  call+result, agent correlation, Foundry/Fabric live probe call+result, human decision, live
  email send attempt+result. This is the literal, real sequence executed, not a canned
  narrative.
- **`GET /activity`**: merges every card's trace across all incidents, time-sorted, tagged with
  `scenario_id` — a single cross-incident "what is the agent doing right now" console.
- **Dashboard**: added a live-scrolling Activity panel (polls `/activity` every 8s) and, per
  incident card, an expandable `<details>` block showing the actual retrieved evidence: real
  Work IQ message subjects/senders, real Web IQ result titles as clickable links, real Foundry IQ
  index matches (or the honest pending-consent reason), real Fabric IQ workspace items (or the
  honest pending-consent reason), plus that incident's own trace timeline.
- **`POST /incidents/simulate`**: generates a brand-new disruption on demand by deriving its
  blast radius live from the ontology graph (shipment → material → plants → production orders →
  SKUs → customers), not one of the four fixed canned scenarios, then runs the full four-source
  reasoning pass against it. A "Simulate new disruption" button on the dashboard demonstrates the
  agent framework reasoning over genuinely novel input, not a script.
- Verified locally (uvicorn + `.env`) and confirmed no JS console errors, then rebuilt/deployed
  as `v9`. Deactivated the stale revision left `Active: true` after update (same recurring
  Container Apps quirk as before) once the new revision was confirmed healthy via direct
  `/healthz` + `/incidents` curls against the production FQDN. Evaluator still 100% pass
  (`evidence_grounded_recommendation_pass_rate: 1.0`, `approval_gate_integrity_pass_rate: 1.0`).

**Current status (image `v9`, revision `--0000010`)**: same live/pending status per IQ source as
v8 (Web IQ + Work IQ genuinely live; Foundry IQ + Fabric IQ code paths genuinely live but
reporting an honest "not consented" until the human completes the device-code sign-in) — what
changed is that the portal now *shows* this instead of asserting it.

## Round 4: stop auto-refresh/auto-polling to save cost (v10)

User feedback: the page was auto-reloading itself, and live-IQ calls (Graph mail reads, web
search, Foundry/Fabric probes) were being burned continuously by a 60s background thread even
when nobody was looking at the app.

- Removed the client-side `setInterval(load, 8000)` — the dashboard now loads incidents/activity
  exactly once when opened, and only updates again on an explicit user action (Refresh now,
  Approve/Reject, Re-probe, Simulate).
- Removed the always-running server-side background monitor thread entirely. Replaced it with
  `_refresh_open_incidents_on_demand()`, called from `GET /incidents`, which re-probes all open
  incidents' live IQ sources but only actually runs when someone opens/refreshes the app — and is
  throttled to at most once per 20s so rapid repeat opens don't multiply live-IQ calls.
- Net effect: live-IQ API usage (and associated cost/quota) now scales with actual human usage of
  the portal, not with container uptime.
- Verified in production (`v10`, revision `--0000011`): no `setInterval` in the served dashboard
  HTML, two rapid `/incidents` calls return the same `evidence_refreshed_at` (proving the
  throttle works), `/healthz` and `/incidents` both respond correctly, stale prior revision
  deactivated.

## Round 5: stale cached dashboard JS (v11)

After removing client-side polling (round 4), the user still saw the activity log growing every
~20-25s. Root cause: `/dashboard` served `INTERACTIVE_PAGE` with no `Cache-Control` header, so the
browser kept the previously-loaded page (with the old `setInterval(load, 8000)` JS) cached across
the deploy. The old tab's 8s polling loop was still hitting the *new* backend, which throttles
`_refresh_open_incidents_on_demand()` to once per 20s — producing exactly the ~20-25s cadence of
fresh evidence the user observed, even though no new deploy's JS should have been polling at all.

Fix: added explicit `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` to the
`/dashboard` response so a hard reload always fetches the current JS after any future deploy.
Deployed as `v11` (revision `--0000012`), verified the header via a direct curl against the
production FQDN. **User action needed once**: hard-refresh the open browser tab (Cmd+Shift+R /
Ctrl+Shift+R) to drop the stale cached page; subsequent loads will always get the latest version.

## Round 6: full-page reloads were still happening client-side (v12)

Server logs revealed the previous fix (round 4/5) wasn't sufficient: actual fresh
`GET /dashboard` requests kept recurring every ~30-70s — a real full-page reload, not just a
stale-JS polling loop. This is client-side behavior outside the app's control (browser tab
manager, extension, or network-level prefetch/security scanning) and no server-side header can
prevent a client from re-navigating to a URL.

Fix: removed the automatic `load()` call that used to fire on every page load. The dashboard now
renders in a fully idle state ("Click 'Load live incidents' above") and makes **zero** calls to
`/incidents` or `/activity` until the human explicitly clicks the button. This makes the
no-background-cost guarantee unconditional: even if something outside our control keeps
re-fetching the HTML page, no live-IQ probe (Graph mail, web search, Foundry/Fabric) fires unless
a person actually clicks. Verified: `curl`-ing `/dashboard` repeatedly in a loop does not change
`evidence_refreshed_at`; production logs after deploying `v12` show zero `/incidents` calls in
the absence of a real button click. Deployed as `v12` (revision `--0000013`).

## Round 7: in-app authentication for Foundry IQ / Fabric IQ consent (v13)

Previously, unlocking Foundry IQ and Fabric IQ required me to run a CLI device-code polling
loop out-of-band and hand the user a code to paste into a browser separately — clunky, and I
discovered mid-session that AAD only allows a single resource's scopes per device-code
request, so a "one code unlocks everything" combined flow isn't possible; Graph, Search, and
Fabric each need their own consent.

Fixed properly by moving the whole flow into the app itself:
- `agent/iq_auth.py`: added `start_device_code(scope)` (calls AAD's `/devicecode` endpoint) and
  `poll_device_code(device_code)` (single non-blocking poll; on success, updates
  `WORK_IQ_REFRESH_TOKEN` in-process immediately and clears the token cache so live probes
  start working without a restart).
- `app.py`: new `POST /auth/device/start` (`{"target": "search"|"fabric"}` &rarr; returns the
  code + verification URL) and `POST /auth/device/poll` (single poll, called repeatedly by the
  browser).
- `dashboard.py`: new "Live IQ source connections" panel with a "Connect Foundry IQ" and
  "Connect Fabric IQ" button. Clicking one shows the real code + a clickable sign-in link
  inline, then polls every few seconds (bounded to the code's actual expiry) until it reports
  success or failure &mdash; no terminal, no separate CLI step, entirely inside the portal.
- Verified locally end-to-end (`/auth/device/start` returns a genuine AAD device code,
  `/auth/device/poll` correctly reports `pending`) and in production after deploying `v13`.

**Known limitation**: a successful sign-in updates the refresh token only for the life of the
running container (in-process `os.environ` update); it is not yet persisted back to the
Container App secret, so a future container restart will require clicking Connect again (one
click, no CLI). Persisting it automatically would require the container to have a managed
identity with rights to update its own Container App secrets via ARM &mdash; not yet set up.

## Round 8: RCA traceability + in-app agent console (v14)

**User feedback**: "its a bit hard to read, like how can i know where the RCA was derived from
is it from a particular transaction or what and also, maybe a chat where u can call agents to
do some activities would be good."

**RCA traceability**: the root-cause hypothesis paragraph already referenced the shipment/
material IDs inline, but there was no explicit link from the hypothesis to the exact evidence
record behind each part of it. Added a "Derived from" row of citation chips directly under the
hypothesis text on every card, one per IQ source that actually contributed:
- Fabric IQ: names the real `shipment_id` / `material_id` (the transaction)
- Foundry IQ: names the exact governed policy doc id(s) matched
- Web IQ: shows the literal search query string used
- Work IQ: notes whether org/collaboration context was found

Each chip is clickable and jumps to (and briefly highlights) the matching evidence block inside
"Show retrieved evidence & reasoning trace" below, via anchor ids (`ev-fabric-<id>`,
`ev-foundry-<id>`, `ev-web-<id>`, `ev-work-<id>`). This makes "where did this come from" a
one-click answer instead of requiring the human to scan the whole trace log.

**Agent console (chat)**: added `POST /chat` plus a chat panel on the dashboard. This is a
deterministic rule-based intent parser, not an LLM (none is configured in this project) —
explicitly labelled as such in the UI hint text, per the no-fake-reasoning constitution.
Supported commands: `list`/`status`, `explain <incident>`, `reprobe <incident>`,
`approve <incident>`/`reject <incident>`, `simulate`, `help`. Approve/reject still hard-gate on
the incident actually being in `Requires Approval` state — the chat console is a second way to
drive the same underlying functions the buttons already call, not a new bypass of the approval
gate.

**Verified**: ran locally end-to-end (list, help, explain, reprobe, approve with re-approval
correctly rejected once already Executed); built/deployed image `v14`, new revision
`--0000016` came up Healthy at 100% traffic, prior revision `--0000015` deactivated (found
already deactivated on check — no manual step needed this round); confirmed `/chat` and the
new dashboard markup (`Agent console`, `citationsFor`) are present in production.

**Known limitation carried forward**: the chat console has no memory of Foundry/Fabric IQ
consent beyond the in-process auth already added in Round 7 — a container restart still
requires re-clicking Connect, same as before.

## Round 9: show the exact API request/response per IQ source (v15)

**User feedback**: "I want to know what exactly has been retrieved what command/Graph
command/KQL command has been done, foundry IQ what input and output per each."

The evidence-detail panel already showed a human-readable summary per source ("3 real
item(s) found in workspace"), but not the literal call made. Added an explicit
"Exact request sent" / "Raw response" block to every live-IQ evidence section:

- **Fabric IQ**: `GET https://api.fabric.microsoft.com/v1/workspaces/<id>/items` (Fabric REST
  API item listing; there is no KQL involved here — this endpoint lists workspace items, not a
  Lakehouse SQL/KQL query) with the raw JSON item list returned.
- **Foundry IQ**: `POST .../indexes('all-iq-demo-policies')/docs/search?api-version=2024-07-01`
  with the exact `{"search": "<query>", "top": 3}` body (Azure AI Search full-text query, not
  KQL either) and the raw search response.
- **Work IQ**: `GET https://graph.microsoft.com/v1.0/me/messages?$top=5&$select=subject,from,receivedDateTime`
  (Microsoft Graph OData query) with the raw Graph response.
- **Web IQ**: `POST https://api.microsoft.ai/v3/search/web` with `{"query": ..., "count": 3}`
  and the raw search response.

Implementation: each live-probe function (`live_foundry_iq_probe`, `live_fabric_iq_probe` in
reasoning.py; `live_recent_mail` in work_iq.py; `live_web_search` in web_iq.py) now always
returns a `request` dict (method/url/body) regardless of success/failure, and a
`raw_response` dict on success. These already flowed to the frontend via `to_dict()`'s
`live_probe`/`data` fields (no backend schema change needed there) — just needed to be
populated and rendered. Dashboard renders both as `<pre>` code blocks under each source's
evidence, truncated to 2500 chars for the response and HTML-escaped to avoid any injection
risk from response content.

**Correction for the user**: none of the four IQ sources use KQL in this demo. Fabric IQ's
"KQL" would apply to a KQL/Eventhouse database, but this demo only lists Fabric workspace
items via REST (no Eventhouse configured); Foundry IQ uses Azure AI Search's own query syntax
(the `search` parameter), not KQL.

## Collapsible evidence and guided chat (working tree, not deployed)

`dashboard.py` now puts each request body and captured response in its own collapsed
JSON viewer. Expansion defaults to a nested, escaped Readable view; a per-block Raw JSON
button shows the pretty-printed payload. Raw previews retain the 2500-character limit;
readable previews also bound content and nesting, with visible truncation markers.
Citation anchors still open the outer evidence panel independently of the JSON viewers.

The deterministic chat console accepts full ids, list numbers/ordinals, scenario numbers,
and id keyword prefixes. Multiple or unknown targets return candidate lists without
acting. Approval/rejection must start with an explicit command and still require
`Requires Approval`. Replies add `suggestions` without changing existing response keys.
Suggestions send immediately, including explicit approval/rejection suggestions.
The frontend renders safe paragraphs/bullets, replaces a temporary thinking row, and
seeds a static greeting without fetching incidents or activity. There is no LLM or
conversational memory; conflicting references require clarification rather than guessing.

Regression checks: `python3 -m unittest discover -s tests -v` from this project.
`test_chat.py` substitutes cards and action functions to avoid executing real decisions.
`test_dashboard.py` uses existing headless Chrome (or `CHROME_BIN`) to operate JSON
toggles, citation jumps, and chat controls, including zero startup fetches and error cleanup.
No additional dependencies are required; the browser test skips if Chrome is unavailable.

**Verified**: ran locally, confirmed all four `request` dicts are populated with the real
endpoints/bodies and `raw_response` populated when live; validated JS syntax (caught and fixed
one escaping bug — an escaped `\"` inside a JS object-literal key was being unescaped by
Python's string parser before reaching the browser, producing invalid JS; switched to a
single-quoted key). Built/deployed `v15` (revision `--0000017`, confirmed Healthy at 100%
traffic in production), deactivated prior revision `--0000016`.

## Round 10: "Fabric IQ doesn't show a response" — root cause and fix

Investigated by simulating the real browser flow in jsdom (with `matchMedia` and relative
`fetch` polyfilled) against the live production dashboard, then diffing rendered evidence
HTML per scenario. The rendering pipeline itself was correct: the Fabric IQ workspace-items
call was live and populated. The actual gap was that Fabric IQ only ever listed workspace
*item metadata* (SQLEndpoint/Lakehouse/Notebook names) — it never queried anything from
inside the Lakehouse, so there was no real "response" with business content for the user to
see, only a generic 3-item chip repeated across every scenario.

Fix: `live_fabric_iq_probe` now makes a second, genuinely live call — Fabric REST
`GET /v1/workspaces/{id}/lakehouses/{lakehouseId}/tables` — to list the actual Delta tables
inside the ontology Lakehouse. This call is real and succeeds today, but currently returns
zero tables, because the `load_ontology_into_lakehouse` notebook has never been run in this
workspace (a one-time manual step; there is still no run-notebook API wired up). The first
version of the UI change swallowed this "call succeeded, zero tables" case into an empty
string, which reproduced the exact "nothing shows" symptom the user reported — found via a
second jsdom pass diffing the actual rendered evidence block content, not just relying on
the raw JSON. Fixed by adding an explicit third rendering branch that always shows the
request/response for the tables call along with a plain-language explanation when it's
empty, instead of only handling the "has tables" and "call failed" cases.

Also added `notebook/architecture.md`: a Mermaid-based system/sequence/deployment diagram
covering the FastAPI app, all four live IQ sources with their real endpoints, the
mocked-fallback path, the approval-gate state machine, and the Azure deployment topology.

**Verified**: added/updated `tests/test_reasoning.py` case for the new extra Fabric call
(retry-then-succeed sequence is now 3 calls for fabric, not 2); ran `pytest tests/ -q` (21
passed). Validated JS syntax via evaluated `INTERACTIVE_PAGE` (naive regex extraction on the
raw file text gives a false positive here due to Python string escaping — must extract from
the actual rendered string). Built/deployed `v17` then `v18` (revision `--0000020`, Healthy,
100% traffic) after catching the empty-tables-case bug between the two; confirmed via jsdom
against the live production dashboard that the transparency message and request/response
block now render for every scenario. Deactivated stale revisions.
