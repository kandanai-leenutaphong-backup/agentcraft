# Supply Chain Guardian — Architecture

Autonomous agent that detects manufacturing supply-chain disruptions by correlating
evidence from four live "Microsoft IQ" sources, forms a root-cause hypothesis, and
gates any consequential mitigation action behind explicit human approval.

## System overview

```mermaid
flowchart TB
    subgraph Client["Browser"]
        UI["Dashboard (dashboard.py)\nEvidence viewer + chat console"]
    end

    subgraph App["FastAPI app (app.py) — Azure Container App"]
        API["/incidents, /incidents/{id}/reprobe,\n/incidents/simulate, /chat"]
        Engine["Reasoning engine (reasoning.py)\ncorrelate_evidence / build_incident"]
        Gate["Approval-gate state machine\n(pending -> approved/rejected)"]
        Auth["iq_auth.py\ndevice-code token cache (in-process)"]
    end

    subgraph IQ["Microsoft IQ sources (live, real tenant calls)"]
        Fabric["Fabric IQ\nFabric REST API\nworkspace items + Lakehouse tables"]
        Foundry["Foundry IQ\nAzure AI Search\npolicy index query"]
        Work["Work IQ\nMicrosoft Graph\nmail.read (delegated)"]
        Web["Web IQ\nWeb search API"]
    end

    subgraph Mock["Mocked fallbacks (explicitly labelled)"]
        MockData["*.mock.json snapshots\nused only when a live call\nis unavailable/not consented"]
    end

    UI <--> API
    API --> Engine
    Engine --> Gate
    Engine -->|reads token via| Auth
    Engine --> Fabric
    Engine --> Foundry
    Engine --> Work
    Engine --> Web
    Fabric -.fallback.-> MockData
    Foundry -.fallback.-> MockData
    Work -.fallback.-> MockData
    Web -.fallback.-> MockData

    Fabric --> FabricAPI[("api.fabric.microsoft.com")]
    Foundry --> SearchAPI[("Azure AI Search index")]
    Work --> GraphAPI[("graph.microsoft.com")]
    Web --> WebAPI[("web search endpoint")]
```

## Evidence correlation flow (per incident)

```mermaid
sequenceDiagram
    participant U as User (dashboard/chat)
    participant A as app.py
    participant R as reasoning.py
    participant F as Fabric IQ
    participant D as Foundry IQ
    participant W as Work IQ
    participant S as Web IQ

    U->>A: GET /incidents or /incidents/{id}/reprobe
    A->>R: build_incident(scenario)
    R->>F: GET workspace items
    R->>F: GET lakehouse tables (if Lakehouse item found)
    R->>D: POST search index query
    R->>W: GET recent mail (delegated)
    R->>S: GET web search(query)
    F-->>R: items + tables (live) or fallback
    D-->>R: policy matches (live) or fallback
    W-->>R: messages (live) or fallback
    S-->>R: search results (live) or fallback
    R->>R: correlate_evidence() -> hypothesis + confidence + citations
    R-->>A: Incident (evidence, hypothesis, trace, request/response per source)
    A-->>U: JSON (rendered as cards + collapsible evidence + chat replies)
    U->>A: POST /incidents/{id}/approve|reject (human gate)
    A->>R: transition state, log to trace
```

## Key design principles

- **Live-first, mock-fallback-explicit**: every IQ source attempts a real, read-only
  API call first; a mocked snapshot is used only on failure/no-consent, and every
  evidence block is labelled `mocked: true|false` so the UI never conflates the two.
- **Full request/response transparency**: each live probe returns the exact
  `request` (`method`, `url`, `body`) it issued and the `raw_response` it received,
  so the dashboard can show precisely what was called and what came back — not just
  a summarized chip.
- **Human-gated actions**: the agent can propose mitigations (informed by the
  correlated hypothesis and matched governed policies) but every consequential
  action requires an explicit `approve` via the API/chat before it is considered
  taken.
- **Bounded resilience**: each live probe has a single bounded retry (timeout/429/5xx
  only) and fails closed to the mocked snapshot rather than propagating errors to the
  user.
- **In-process auth only**: Fabric/Foundry/Work tokens are cached via device-code
  consent in `iq_auth.py` and held in process memory (no Container App secret
  persistence). Because the app has `minReplicas: 0`, a scale-to-zero cold start
  clears these tokens and the affected sources revert to "not consented" until the
  user re-authenticates from the UI.

## Deployment topology

```mermaid
flowchart LR
    subgraph Azure["Azure (Malaysia West)"]
        ACR["Azure Container Registry\nscgacr38453"]
        CA["Container App\nsupply-chain-guardian\n(minReplicas: 0)"]
        RG["Resource group\nrg-supply-chain-guardian"]
    end
    Dev["Local build (docker build)"] --> ACR
    ACR --> CA
    CA --> FQDN["supply-chain-guardian.delightfulplant-c387f72d.malaysiawest.azurecontainerapps.io"]
    RG -.contains.-> ACR
    RG -.contains.-> CA
```
