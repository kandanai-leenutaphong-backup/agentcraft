# Skill Catalogue

This directory contains 28 reusable capability skills and five embedded entries owned by their
parents. The eight authored protocol workflows live separately under
[protocols](../protocols/README.md). The machine-readable inventory is [catalogue.json](catalogue.json).
Seven optional MCP adapters declare 27 tools; loading a skill alone does not register an adapter
or grant live access.

Ask **"Use the NAME skill to ..."** to load an entry and its supporting files. Follow that entry's
installation and verification instructions using the loaded skill directory. Explicit slash
invocation varies by client. This checkout has no repository-root plugin installer; an integrating
plugin must supply its own client-compatible registration and verification.

The repository's existing [MIT notice](LICENSE) travels with each independently distributed
skill. Fonts, artwork and external runtime dependencies keep their own terms. See
[distribution guidance](AGENT-PLUGINS-SKILLS.md) for source boundaries and licensing checks.

## All Current Skills

| Skill | What It Provides | Access |
| --- | --- | --- |
| [agent-optimization](agent-optimization/SKILL.md) | Frozen-cohort experiments, immutable generations and replay UI; verified portable source snapshot with integration guides and synthetic record examples | Skill + Python/React + reference-pack CLI |
| [architecture-placement](architecture-placement/SKILL.md) | Ownership/dependency advice and an explicit-root architecture checker | Skill + CLI |
| [azure-access-management](azure-access-management/SKILL.md) | Consolidated Entra API/frontend sign-in, native access workflows, workload identity, compatibility helpers and 68 capability records | Skill + offline planner/Python/Bicep + read-only MCP |
| [azure-cli-infra-management](azure-cli-infra-management/SKILL.md) | Target-bound Azure CLI resource lifecycle, ownership, read-back and documented live-test infrastructure | Skill guidance |
| [azure-data-connectors](azure-data-connectors/SKILL.md) | Bounded Azure data queries and reusable resilient connectors | Skill + Python + MCP |
| [azure-llm-connectors](azure-llm-connectors/SKILL.md) | `azllm` model access, streaming, parsing and embeddings | Skill + Python + MCP |
| [azure-search](azure-search/SKILL.md) | Index/schema/document CRUD, vector/semantic queries and per-item failure handling | Skill + Python |
| [azure-sky-styling](azure-sky-styling/SKILL.md) | Scoped theme, depth recipes, original galleries, fonts/artwork and browser tests | Skill + CSS/React |
| [codebase-cleanup](codebase-cleanup/SKILL.md) | Read-only filesystem inventories, same-scope comparisons and authorized cleanup workflow; alias `codebase_cleanup` | Skill + Python CLI |
| [content-from-a-store](content-from-a-store/SKILL.md) | Read-mostly content with immutable fallback and ETag refresh | Skill + worked example |
| [deploy-container-apps](deploy-container-apps/SKILL.md) | Identity-based image pulls, rollout, verification and teardown guidance | Skill guidance |
| [event-stream](event-stream/SKILL.md) | Named SSE framing across byte/line boundaries and JSON dispatch | Skill + TypeScript |
| [frontend-implementation](frontend-implementation/SKILL.md) | Implementation, accessibility, build and browser-verification workflow | Skill guidance |
| [ghcp-cli-frontend](ghcp-cli-frontend/SKILL.md) | Interactive Copilot CLI React/xterm frontend and host-owned Python PTY runtime; alias `ghcp_cli_frontend` | Skill + React/Python |
| [harness-guide](harness-guide/SKILL.md) | Validated skill/protocol listing, task search and exact entry-point reads | Skill + CLI |
| [hyperframes-motion](hyperframes-motion/SKILL.md) | Pinned local CSS-motion runner, rendering and decoded-frame verification | Skill + render CLI |
| [investigation-notebook](investigation-notebook/SKILL.md) | Searchable, evidence-grounded working memory with schema and fresh-project lifecycle tests | Skill + CLI |
| [managed-identity-model-clients](managed-identity-model-clients/SKILL.md) | Independent `modelaccess` API with identity, streaming and aligned embeddings | Skill + Python + MCP |
| [modular-agents](modular-agents/SKILL.md) | Configured agents, typed tools, hosted bundle creation and authorized Foundry workflows | Skill + Python/deployment CLI |
| [portable-app-composition](portable-app-composition/SKILL.md) | Canonical documents, allowlisted composition and lifecycle handling | Skill + Python + MCP |
| [recoverable-jobs](recoverable-jobs/SKILL.md) | Completed-output preservation, verified store commit and restart recovery | Skill + Python + MCP |
| [resource-explorer](resource-explorer/SKILL.md) | Scoped resource tree, content and estate search with optional browser source | Skill + Python/browser + MCP |
| [runbook-replay](runbook-replay/SKILL.md) | Operator runbook replay with observations and actionable gaps | Skill guidance |
| [signed-dev-access](signed-dev-access/SKILL.md) | `devauth`, Ed25519 signing and authenticated browser/API piloting | Skill + Python/signing CLI |
| [situation-detector](situation-detector/SKILL.md) | Configured synchronous/async query batteries with explicit windows and result identity | Skill + Python |
| [source-code](source-code/SKILL.md) | Read-only Shiki source rendering, wrapping, clipboard feedback and safe token text | Skill + React |
| [ui-experience-audit](ui-experience-audit/SKILL.md) | Task flow, feedback, accessibility and responsive-geometry auditing | Skill guidance |
| [web-resource](web-resource/SKILL.md) | Guarded public-page/image/screenshot acquisition with provenance | Skill + Python/acquisition CLI |

The former `adx-event-store` skill is retired into the canonical
[azdata.event_store library](../../libraries/azure-data-connectors/docs/event-store/README.md).
Its implementation, operator workflow, tests, gotchas, license and provenance are preserved
there; installation grants no writes or Azure access. It has no remaining native skill entry.

The two model libraries are independent APIs; installation does not replace either one.
Former auth/browser, Container Apps auth and Bicep identity names resolve as lookup aliases
to `azure-access-management`. They are not additional native skills or guaranteed native
slash commands. The consolidated skill retains the distinct compatible APIs and tests.
The embedded entries below support their named parent and are not additional plugin installs.
They are catalogued as components, searchable, and readable by exact name; read the parent
integration contract before composing them.

| Embedded Skill | Parent | What It Provides |
| --- | --- | --- |
| [agent-config-build](modular-agents/modules/agent-config-build/SKILL.md) | `modular-agents` | Declarative YAML roster, prompt fragments and allowlisted tools |
| [foundry-agent-runtime](modular-agents/modules/foundry-agent-runtime/SKILL.md) | `modular-agents` | Foundry/MAF runtime with identity, per-agent clients and bounded fallback |
| [purpose-built-tools](modular-agents/modules/purpose-built-tools/SKILL.md) | `modular-agents` | Validated tool inputs, deduplication, output shapes and ablation evidence |
| [creative-agent-optimization](agent-optimization/python/agent_optimization/skills/creative-agent-optimization/SKILL.md) | `agent-optimization` | Evidence-first creative experiments and measured exploration |
| [resource-inventory](resource-explorer/inventory/SKILL.md) | `resource-explorer` | Host-registry datasource/agent/tool explorer with bounded previews |

## Protocol Workflows

Each workflow under [protocols](../protocols/README.md) has one authored `SKILL.md` containing
the complete procedure. The catalogue reads that file directly; no generated wrapper is needed.

[HyperFrames](hyperframes-motion/SKILL.md) is a bundled capability, not an additional protocol
workflow or a second implementation supplied by another module.

## MCP Calls

Start with the status tool. It reports its actual `config_file`, not a path inside the consuming
project. Missing configuration and denied live grants are expected on a fresh install.

| Server | First Call | Other Tools |
| --- | --- | --- |
| `azure-access-management` | `azaccess_status` | `azaccess_matrix`, `azaccess_role`, `azaccess_scope`, `azaccess_inspect` |
| `azure-data-connectors` | `azdata_status` | `azdata_query_kql`, `azdata_query_gremlin`, `azdata_query_graph`, `azdata_search` |
| `azure-llm-connectors` | `azllm_status` | `azllm_ask`, `azllm_embed` |
| `managed-identity-model-clients` | `modelaccess_status` | `modelaccess_ask`, `modelaccess_embed` |
| `portable-app-composition` | `appcompose_status` | `appcompose_validate`, `appcompose_demo` |
| `recoverable-jobs` | `workrecovery_status` | `workrecovery_list`, `workrecovery_stage`, `workrecovery_read` |
| `resource-explorer` | `resource_explorer_status` | `resource_explorer_tree`, `resource_explorer_content`, `resource_explorer_search` |

Try "Call appcompose_demo" for a useful offline call. It runs and stops a fixed in-memory
application. Configuration changes, model spending, live Azure reads and local recovery access
remain explicit operator decisions, never grants supplied in tool input.

Skills without one of the listed adapters have **no MCP server**. Loading them makes their guidance
and files discoverable. Follow their Python, CLI or template instructions when they provide executable
capabilities; plugin installation does not install their libraries into your application's venv.
In particular, `modular-agents` does not register deployment or paid inference as MCP tools.

## Verify And Remove

Run the selected skill's documented checks. An integrating plugin should use temporary
configuration and each adapter's offline smoke check, then verify tool discovery, status and
malformed-argument refusal through an official-SDK client. Do not use live operator configuration
for an installation check. Offline success is not evidence of Azure permissions or deployment.

For local recovery work, choose a durable operator-owned `recovery_root`. Commit or export pending
artifacts before uninstalling an integrating plugin; clients may remove plugin data on uninstall.
Uninstalling does not revoke Azure roles, destroy deployed resources or remove consumer-vendored code.

Project overview: [../../README.md](../../README.md).
Packaging and configuration: [AGENT-PLUGINS-SKILLS.md](AGENT-PLUGINS-SKILLS.md).