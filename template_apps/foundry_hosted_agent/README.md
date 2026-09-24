# Foundry Hosted Agent Starter

Minimal reusable skeleton for a native Microsoft Foundry Hosted Agent: a Responses protocol
container whose model and tool loop is Microsoft Agent Framework through `llm_interface`,
configured by one canonical `agentconfig` `configuration.yaml`, plus a lifecycle whose only entry
point is [deploy/deploy.sh](deploy/deploy.sh) over the shared `foundry_ops` library.

Generalized from [testbeds/foundry-hosted-agents](../../testbeds/foundry-hosted-agents/deploy/README.md)
(live-accepted 2026-09-22). Kept: platform CA trust with verification on, exact image/config identity
in response metadata, stored-response read-back, anonymous 401/403 refusal, teardown order
responses -> sessions -> versions, 50-character label limit. Stripped: nonce proofs and envelopes,
grants, overlap builds, cancellation probes.

Status: 37 offline tests pass (`bash deploy/deploy.sh test`, real local SDKs, no network). No image
built, nothing deployed, no cloud call made. Live behaviour is unverified for this template.

## File map

| Path | Owns |
| --- | --- |
| [app/main.py](app/main.py) | `ResponsesAgentServerHost` handler, `run_agent` (`llm_interface.connect`), cancellation, identity metadata, `--self-check` image smoke |
| [app/composition.py](app/composition.py) | `load_spec`: exactly one default agent; tools only from `agent_tools` |
| [app/configuration.yaml](app/configuration.yaml) | agent name, model deployment, prompts, tools |
| [app/prompts/agent.md](app/prompts/agent.md) | instructions |
| [app/agent_tools.py](app/agent_tools.py) | example deterministic tool `count_words` |
| [deploy/deploy.sh](deploy/deploy.sh) | entry point; sets `PYTHONPATH` to the repository libraries |
| [deploy/lifecycle.py](deploy/lifecycle.py) | env validation, source allowlist, action order over `foundry_ops` |
| [deploy/Dockerfile](deploy/Dockerfile) | digest-pinned uv + Python 3.12 base, hash-locked install into the image's system interpreter |
| [deploy/runtime-requirements.in](deploy/runtime-requirements.in), [.lock](deploy/runtime-requirements.lock) | third-party pins; lock derived from the testbed's live lock minus repository packages |
| [deploy/env/example.env](deploy/env/example.env), [example.run.json](deploy/env/example.run.json) | documented targets (placeholders) and the run manifest pinning them |
| [deploy/README.md](deploy/README.md) | run order, expected output, failure playbook |
| [tests/](tests/) | runtime, configuration, env, manifest, source, lifecycle-over-fakes and CLI refusal tests |

## Run order

`test` -> `preflight` -> `build` -> `deploy` -> `invoke` -> `verify` -> `teardown --plan` ->
`teardown`. Cloud writes need `--authorize-cloud-write`; every cloud action needs `-e <environment>`
and `--manifest-sha256`. Commands and failure handling: [deploy/README.md](deploy/README.md).

## Left to the app author

- Real tools and prompts: add functions to `agent_tools.py`, list them in `configuration.yaml`.
  Keep tools side-effect-free or idempotent; host cancellation cannot undo a synchronous side effect.
- Input contract: `parse_input` accepts bounded text only; structured input is the author's.
- `LIMITS` in `main.py` (model/tool calls, tokens, timeout).
- Targets, run manifests and review of each manifest digest.
- Role grants (`AcrPull` for the project identity), model deployment, networking, ACR image cleanup.
- Evaluation and optimization. Native candidate loading via
  `azure.ai.agentserver.optimization.load_config` is not included; see `loaded_spec` in
  [the optimization testbed](../../testbeds/foundry-agent%20optimization/main.py).
- Lock refresh: edit `runtime-requirements.in`, regenerate with the `uv pip compile` command in the
  lock header, rerun `test`.

## Limits

- Runtime paths not exercised offline: a real model call through `llm_interface`, platform
  `DefaultAzureCredential`, the platform-injected `FOUNDRY_AGENT_NAME`/`FOUNDRY_AGENT_VERSION`/
  `FOUNDRY_PROJECT_ENDPOINT`, the Docker build and `--self-check` inside the image, and every Azure
  CLI/SDK call in `lifecycle.cloud_clients` and `preflight`.
- The lock is a subset of the testbed's live-accepted lock; resolution from the index (the testbed
  used a local wheelhouse) is unverified.
- Secret-shaped env detection is a pattern backstop; per-variable formats are the primary guard.
