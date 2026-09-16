# KIOSK_DEMO_HANDOFF.md — Backend-Free Public Demo

Last updated: 2026-04-20

Supersedes the live-LLM aspects of `PUBLIC_DEMO_HANDOFF.md`.
Inherits its sanitization rigor (string scrubbing, secret deletion,
infra strip, verification greps) — those remain mandatory.

Reference reading: `AUTODEV.md`, `ARCHITECTURE.md`,
`app/frontend/src/features/replay/` (the existing playback engine — most
of the work is already done), `app/frontend/src/stores/replayStore.ts`,
`app/frontend/src/components/layout/SavedSessionPicker.tsx`.

---

## Goal

A self-contained single-page app that runs a convincing GridIQ
investigation **with no backend, no LLM, no network calls beyond
fetching its own bundle.** Operator presses **Play Demo**, watches a
scripted, perfectly-timed reproduction, can pause to talk through any
event, can pick a different scenario from a list. That's the entire
product surface.

| Aspect | Decision |
|--------|----------|
| Backend | **None.** No `/api/*` routes exist in the public bundle. |
| LLM | **None.** No Foundry, no OpenAI, no streaming. |
| Persistence | **None.** State is in-memory; refresh resets. |
| Auth | **None.** Public URL is anonymous; no MSAL, no DEV_API_KEY. |
| Free-form chat | **Disabled.** Input box hidden / "Demo build" placeholder. |
| Scenarios | **Bundled JSON in the SPA.** No fetches. |
| Hosting | Azure Static Web App, GitHub Pages, or nginx-only Container App — all equivalent. |

---

## Core Principle: Scenarios are CDs

**The scenario file is the product.** Everything else is a player.

One JSON file fully describes a demo run: the chat messages, tool
calls, panel contents, situation cards, agent tabs — every UI element's
state at every step, plus the timing between steps and the narration
the demo lead reads aloud. Change the JSON → change the demo. Drop in
a new JSON → new scenario. No code changes, no rebuild, no redeploy.

Non-negotiable properties:

1. **Hand-authored, not captured.** No tool ever "records" a scenario
   from a live system. A human writes the JSON in a text editor (or a
   future scenario-authoring UI writes it). Scenarios that come from
   capture are coupled to the backend's data shapes and break when
   either side evolves.
2. **Self-contained.** Everything the player needs to render the
   scenario is in the file. No external fetches. No "see also" pointers
   to other JSONs. No per-tool fixture lookups. One file = one demo.
3. **Declarative frames, not events.** A scenario is an ordered list of
   **frames**. Each frame says "at this point, the UI should look like
   *this*." The player diffs frame N against frame N+1 and animates
   the delta over `transition_ms`. This is simpler than an event
   stream and survives schema drift in the chat/panel stores.
4. **Human-readable.** A non-developer can open the JSON, find the
   text of a chat bubble, and edit it. No base64, no opaque IDs, no
   wire-format payloads.
5. **Hot-swappable.** Adding a new scenario = drop a `.json` file into
   `app/frontend/src/demo/scenarios/`, register one line in
   `index.ts`, rebuild. Removing a scenario = delete the file. The
   player never inspects file contents at build time.
6. **Stable schema, versioned.** Every scenario file declares
   `"schema": "gridiq-demo/v1"`. The player refuses to load files with
   an unknown schema rather than silently mis-rendering.

The rest of this document describes the player. The player is
straightforward. The discipline is keeping the player dumb so the
scenarios stay simple.

---

## Scenario File Schema (gridiq-demo/v1)

```jsonc
{
  "schema": "gridiq-demo/v1",
  "id": "placeholder",
  "label": "Placeholder Demo",
  "description": "A short throwaway scenario used to validate the player. Replace before going public.",

  // Initial UI state before the operator presses play.
  "initial": {
    "active_agent": "investigator",
    "chat":     { "investigator": [], "dispatcher": [] },
    "panels":   { "priority_actions": [], "situations": [] },
    "situation_scan": null
  },

  // Ordered list of frames. The player walks the array, applies the
  // patch in each frame, then waits `transition_ms` before the next.
  "frames": [
    {
      "id":           "f001",
      "chapter":      "User reports anomaly",
      "narration":    "Operator gets a phone call about a possible bus trip at Liapoota.",
      "transition_ms": 400,
      "patch": {
        // RFC-6902 JSON-Patch-style ops, scoped to the scenario state tree.
        // Use simple `set` / `append` / `update` ops — no full RFC-6902 grammar.
        "chat.investigator.append": {
          "role": "user",
          "text": "Possible Liapoota bus trip — investigate."
        }
      }
    },
    {
      "id":           "f002",
      "chapter":      "Investigator queries alarms",
      "narration":    "The investigator agent decides to look at alarms first.",
      "transition_ms": 800,
      "patch": {
        "chat.investigator.append": {
          "role": "assistant",
          "agent": "Investigator",
          "text": "",
          "tool_calls": [
            {
              "id": "tc001",
              "name": "find_alarms",
              "status": "running",
              "arguments": { "station": "LIAPOOTA", "start": "2025-09-14 14:35" }
            }
          ]
        }
      }
    },
    {
      "id":           "f003",
      "transition_ms": 1500,
      "patch": {
        "chat.investigator.update_tool": {
          "id": "tc001",
          "status": "complete",
          "duration_ms": 1500,
          "result": { "columns": ["timestamp", "label"], "rows": [/* ... */] }
        }
      }
    }
    // ... more frames
  ]
}
```

Patch operations the player understands (full set, intentionally small):

| Op | Purpose |
|----|---------|
| `chat.<agent>.append` | Add a new chat message bubble. |
| `chat.<agent>.append_token` | Stream text into the last assistant bubble (one chunk). |
| `chat.<agent>.update_tool` | Update an existing tool card by `id` (status / result / duration). |
| `panels.priority_actions.append` | Add an operator-action card. |
| `panels.situations.set` | Replace the situations list. |
| `situation_scan.set` | Set the live situation-scan summary. |
| `active_agent.set` | Switch the active tab. |
| `delegation.start` | Show the delegation banner in the dispatcher tab. |
| `delegation.token` | Stream a token into the active delegation block. |
| `delegation.end` | Mark delegation complete. |

If you find yourself wanting an op that isn't in this list, **add the
op to the player rather than the scenario.** The scenario should never
contain logic — only data.

---

## Placeholder Scenario (ship this first)

File: `app/frontend/src/demo/scenarios/placeholder.json`. ~10 frames,
~15 seconds total runtime. Purpose: prove the player works end-to-end
before investing any time in real-content scenarios.

Minimum coverage to validate the player:

- 1 user message bubble
- 1 assistant message with streamed tokens (`append_token` × ~20 frames)
- 1 tool call card going from `running` → `complete` with a tabular result
- 1 delegation handoff to the dispatcher tab
- 1 priority-action card pushed into the panel
- 1 situation-scan summary update
- 2 chapter boundaries (so step-mode and narration overlay are exercised)

Content can be lorem-ipsum tier ("Investigating placeholder station",
"Result row 1 / Result row 2"). The point is to validate that every UI
renderer the real scenarios will use can be driven from a JSON file.

Once the placeholder runs, real scenarios are pure content work — no
further player changes needed.

---

## Demo Targets

| URL | Purpose | Source |
|-----|---------|--------|
| `https://gridiq-v2.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io` | **Public demo home** | This sanitized branch, kiosk-mode build |
| `https://pathfinderiq-aemo.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io` | Internal AEMO build | Untouched, runs from the private repo |

The public Container App becomes nginx-only — no Python, no supervisord
agent process, no Cosmos. ~5 MB image vs the current ~2 GB.

---

## "Play Demo" UX

Header gets a single primary CTA: **▶ Play Demo**. Plus a scenario
dropdown next to it (the bundled scenarios from `demo/scenarios/`).
Plus playback controls that
appear once a demo is running:

- **▶ / ⏸** — Play / Pause
- **⏮** — Restart current scenario from the top
- **⏭** — Skip to next chapter
- **1× / 2× / 5×** — Speed multiplier
- **🛈 Narration** — toggle the chapter caption overlay
- **Step mode** (toggle) — auto-pause at every chapter boundary so the
  demo lead can talk before clicking "next"

The chat input is hidden in kiosk mode. Tab bar still works for
navigating between agents (investigator / dispatcher), since that's
part of the demo.

---

## Architecture

### What already exists (do not rebuild)

- `app/frontend/src/features/replay/replayEngine.ts` — async loop that
  iterates timed events with `await sleep(delayMs, signal)`. Aborts cleanly.
  **Repurpose** as the frame iterator (frames replace events; the loop
  shape is identical).
- `app/frontend/src/stores/replayStore.ts` — `off | playing | done` state
  machine + replay highlight callouts.
- The chat / panel / situation / agent stores all already accept the
  same shapes the scenario patches will produce — no store-side rewrite.

Delete `app/frontend/src/features/replay/convertSavedConversation.ts` —
it assumes captured-session input, which the new architecture forbids.

### What changes

1. **Bundle scenarios.** Move to `app/frontend/src/demo/scenarios/`:
   ```
   demo/
     scenarios/
       placeholder.json     // ship first — see schema section above
       // real scenarios drop in here later, one file each
     index.ts               // exports SCENARIOS = [{id, label, description, importFn}]
   ```
   Each JSON conforms to the `gridiq-demo/v1` schema documented above.
   Hand-authored. Never captured from a live backend. Adding a scenario
   = drop a `.json` file in this directory + add one line to `index.ts`.

2. **Frame-driven player.** Replace `ReplayEvent[]` consumption with
   `Frame[]` consumption. Each frame carries `chapter` and `narration`
   inline (no separate chapters array — chapters are just frames whose
   `chapter` field is set). The progress bar segments on chapter
   boundaries automatically.

3. **Patch dispatcher.** New module `features/demo/applyPatch.ts` —
   takes a `patch` object (one op per key, see schema table) and
   dispatches into the relevant Zustand store. Keep this module short
   and dumb — one switch on the op name, one store call per case. New
   ops are added here, never inferred from the scenario file.

3. **Extend `replayStore`.** Add: `paused`, `currentFrameIndex`,
   `currentChapterIndex`, `speed`, `stepMode`, `narrationVisible`.
   Add actions: `pause()`, `resume()`, `skipToChapter(i)`, `restart()`,
   `setSpeed()`, `toggleStep()`, `toggleNarration()`.

4. **Extend the frame iterator** (renamed from `replayEngine`).
   For each frame:
   - Apply `frame.patch` via `applyPatch()` (instant — the diff IS the visual change).
   - If `frame.chapter`, advance `currentChapterIndex`, surface narration.
   - Wait `frame.transition_ms / speed`, gated by the pause Promise.
   - In step mode, auto-set `paused=true` before any frame whose `chapter` is set.

5. **New components.**
   - `components/demo/PlayDemoButton.tsx` — primary CTA in the header.
   - `components/demo/ScenarioPicker.tsx` — dropdown of bundled scenarios.
   - `components/demo/PlaybackControls.tsx` — visible while `mode==="playing"` or `"done"`.
   - `components/demo/NarrationOverlay.tsx` — bottom-of-screen caption
     bar showing the current chapter's `title` + `narration`.
   - `components/demo/ChapterProgressBar.tsx` — segmented bar (one
     segment per chapter), highlights the active chapter.

6. **Strip the chat input.** `ChatInput.tsx` renders a disabled
   placeholder ("Demo build — press ▶ Play Demo to start") when
   `import.meta.env.VITE_KIOSK_MODE === "true"`.

7. **Strip API calls.** All of `app/frontend/src/api/` is removed in
   the kiosk bundle. Build-time guard:
   ```ts
   // app/frontend/src/api/client.ts
   if (import.meta.env.VITE_KIOSK_MODE === "true") {
     throw new Error("api/client must not be imported in kiosk build");
   }
   ```
   Modules that previously called the API get a kiosk-mode early return.

8. **Vite config.** Add a `kiosk` build mode:
   ```bash
   VITE_KIOSK_MODE=true npm run build
   ```
   Output: `app/frontend/dist/` — pure static assets.

---

## What gets deleted

For the kiosk build (the public bundle):

| Path | Reason |
|------|--------|
| `agent/`, `tools/`, `fabric/`, `hosting/`, `foundation/`, `ops/`, `situation_detector/` | Backend code — not shipped |
| `app/backend/` | Same |
| `data_processors/` | Replaced by hand-authored scenarios in `app/frontend/src/demo/scenarios/` |
| `tests/` (backend) | Frontend tests stay |
| `infra/` (AEMO Bicep) | Replaced by minimal SWA / nginx-Container-App template |
| `Dockerfile`, `Dockerfile.fast`, `deploy/supervisord.conf` | Replaced by `Dockerfile.kiosk` (nginx + dist/) |
| `azure_config.env`, `control/.env` | Deleted — no env vars needed |
| `control/agent_config.yaml`, `control/prompts/` | No agent runs in kiosk |
| `app/frontend/src/api/`, `app/frontend/src/stores/sessionStore.ts` (write paths) | No backend to talk to |

What stays: the entire frontend rendering layer (chat bubbles, tool
renderers, panels, situation cards, agent tabs, MessageBubble, the
GraphResult / TabularResult / SituationResult / DelegationResult
renderers — all of it).

---

## Hosting

Three valid options, pick one:

| Option | Cost | Custom domain | TLS | Effort |
|--------|------|---------------|-----|--------|
| Azure Static Web App | Free tier | yes | auto | minimal — just point at the repo |
| GitHub Pages | Free | yes | auto | minimal |
| nginx-only Container App on `gridiq-v2` | ~$0 (scale-to-zero) | already wired | already wired | reuses the existing FQDN, ACR, identity — **recommended** |

Recommendation: nginx-only Container App on `gridiq-v2`. Reuses the
URL already deployed, reuses the existing managed identity for ACR
pull, scales to zero so it costs nothing when nobody's looking, and
matches the `Dockerfile`/`deploy_app.sh` workflow you already have.

`Dockerfile.kiosk`:
```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY app/frontend/package*.json ./
RUN npm ci
COPY app/frontend/ ./
ENV VITE_KIOSK_MODE=true
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.kiosk.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
```

`deploy/nginx.kiosk.conf` — single-page-app fallback to `index.html`,
no `/api/` proxy, no upstream.

---

## Critical Gotchas

- **No backend means no SSE.** The replay engine fakes SSE locally — it never opens a real `EventSource`. Audit `chatStore.handleSseEvent` callers: any path that opens `new EventSource(...)` in kiosk mode must be guarded.
- **Scenario JSON is the product.** Treat each file as a hand-authored asset — never mutate it from generated code, never call out to a "live capture" tool from the kiosk build, never let the player infer schema from file contents. New op needed? Add it to `applyPatch()` and the schema doc; do not let scenarios carry logic.
- **`MessageBubble` markdown can fetch.** Markdown renderer may follow `<img>` URLs. Audit scenario JSON for any external image references — replace with bundled assets or strip.
- **Frontend code paths still try to talk to `/api/auth_setup` on boot.** Kill that fetch early or stub it with a bundled `{useLogin: false}` constant.
- **`SavedSessionPicker` previously fetched via API.** In kiosk mode, swap the fetch for an `import` of the bundled JSON (`import liapoota from "@/demo/scenarios/liapoota.json"`).
- **`PHILOSOPHY of "everything spoofed"`.** No "if backend available, use it" fallback. The kiosk bundle must never know what a backend looks like — that prevents accidental data leaks if a misconfigured CSP, env var, or local-dev oversight slips through.
- **Narration is hand-authored.** It lives inline on each chapter frame in the JSON. Budget ~30 min per scenario to write good narration — it's the difference between a demo that talks itself and one the demo lead has to fight.
- **Speed multiplier interacts with token delay.** At 5× the token stream looks unnatural. Cap at 3× for the visible-tokens phase, or skip token animation entirely above 2×.
- **Browser tab in background pauses `setTimeout`.** If the demo is running on a kiosk display and the operator opens another tab, `setTimeout` throttles. Use `requestAnimationFrame`-driven scheduling, or accept that the demo pauses when not visible (probably fine — the operator IS looking at it).
- **Scenario JSON size.** Hand-authored frame files should stay under ~50 KB each. If a scenario file balloons (lots of streamed-token frames), split repeated structures into local helpers in a build step — do not introduce shared external fixtures, that violates the self-contained rule.

---

## Build Phases (suggested order)

1. **Phase 0 — Placeholder scenario + player.** Build the player end-to-end against `placeholder.json` only (the throwaway lorem-ipsum scenario). No content work, no AEMO data, no decisions about which real stories to tell. The phase is done when the placeholder runs cleanly through pause / resume / restart / chapter skip / 2× speed / step mode.

2. **Phase 1 — Kiosk build mode.** Add `VITE_KIOSK_MODE` env, the import-time guard in `api/client.ts`, the `ChatInput` placeholder, the bundled-JSON path in `SavedSessionPicker`. Verify `npm run build` with the flag set produces a working bundle that does not call `/api/*`.

3. **Phase 2 — Playback controls.** Extend `replayStore` + `replayEngine` with pause / step / speed / chapter tracking. Build `PlayDemoButton`, `ScenarioPicker`, `PlaybackControls`, `NarrationOverlay`, `ChapterProgressBar`. Wire into the header.

4. **Phase 3 — Strip backend.** Delete the directories listed in "What gets deleted" from the kiosk branch. Replace `Dockerfile` with `Dockerfile.kiosk`. Replace `deploy_app.sh` with a one-liner that builds + pushes the kiosk image.

5. **Phase 4 — Deploy.** `az containerapp update --image <kiosk image>` on `gridiq-v2`. Strip all env vars from the Container App (`az containerapp update --remove-env-vars ...`). Set ingress port to 8080. Set `minReplicas=0, maxReplicas=1` (scale to zero — kiosk is read-only static, so cold start is just the nginx process starting).

6. **Phase 5 — First public commit.** Same as `PUBLIC_DEMO_HANDOFF.md` Phase 5. Run the verification checklist below.

---

## Verification Checklist

Before going public:

- [ ] `find app/frontend/dist -type f | xargs grep -lE "AEMO|aemo|af9ce6a9|ixksfd27yr7rc|pathfinderiq-aemo"` returns nothing.
- [ ] `grep -rE "fetch\(|axios|EventSource|XMLHttpRequest" app/frontend/dist/assets/*.js` returns only fetches that resolve to the same origin (font / asset loads). No `/api/` strings.
- [ ] Open the deployed URL in incognito on a machine not signed into Microsoft. **Browser DevTools network panel** during a full demo run shows: HTML + JS + CSS + the bundled scenario JSON. Nothing else.
- [ ] DevTools console clean — no failed fetches, no MSAL warnings, no `EventSource` errors.
- [ ] All 5 scenarios run end-to-end without errors, including pause / resume / restart / chapter skip / 2× speed / step mode.
- [ ] Narration overlay text matches what the demo lead actually wants to say at each chapter.
- [ ] Refresh during playback resets cleanly to the start state (no stuck "playing" / no orphaned tool cards).
- [ ] Container App env vars list is empty (`az containerapp show --query "properties.template.containers[0].env"` returns `[]`).
- [ ] Container App has no Cosmos / Foundry / Search / Fabric role assignments left over.
- [ ] `git ls-files | grep -E "\.env$|secret|password|key$" | xargs -I {} echo "REVIEW: {}"` — review every match before commit.
