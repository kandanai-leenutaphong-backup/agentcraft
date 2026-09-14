---
name: resource-explorer
description: "Use when browsing an Azure subscription as a lazy resource tree, reading bounded resource contents or ARM properties, finding resources estate-wide, diagnosing forbidden versus unreachable branches, or embedding the explorer's React frontend and Python service. Includes wire contracts, offline fixtures, examples, tests and scoped read-only MCP tools."
compatibility: "Python 3.11+ and uv for MCP. Node LTS for the optional frontend. Live reads require an operator grant, subscription and authorized Azure identity."
---

# Resource Explorer

For a host-declared data/agent/tool registry rather than Azure estate browsing, use the embedded
[resource inventory](inventory/SKILL.md). It supplies its own Python/React public package and
depends on the shared source-code viewer. Existing estate APIs and MCP tools remain unchanged.

This directory contains the complete capability: backend, browser source, wire schema, fixtures,
dependency snapshot and worked examples. MCP is another caller of the same application service.

## Decide

| Need | Surface |
| --- | --- |
| Inspect configuration and permissions | `resource_explorer_status`, no network |
| Expand a resource or collection | `resource_explorer_tree` |
| Read bytes, rows or ARM properties | `resource_explorer_content` |
| Locate resources in the estate | `resource_explorer_search` |
| Embed the application | `ExplorerService(settings, access)` and the frontend in [README.md](README.md) |

## Install And Verify

In an installed plugin, call status to locate configuration. A missing configuration grants no
live reads. Fixture mode is an explicit operator setting and all results carry `fixtures: true`.
Do not configure an account or grant live access on the user's behalf merely to make a test pass.

From a copied skill directory:

```bash
uv sync --locked --no-default-groups --no-install-project --no-install-package azdata --extra mcp --extra dev
.venv/bin/python tests/selftest.py
.venv/bin/python examples/offline.py
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/mcp_server.py --selftest
```

The framework-free selftest walks the fixture tree, content types, search, degradation and bounds.
The SDK check proves MCP input validation, scope refusal and recovery. Browser verification is
separate and documented in the README; a passing MCP call does not prove the browser built.

## Use

1. Read status, grant and scope before accessing anything.
2. Pass returned opaque node IDs unchanged. They are addresses, not bearer credentials.
3. Preserve `status`, `error`, `truncated` and `fixtures` when presenting results.
4. Select search hits by their `kind`, not their position in the result list.
5. Keep content bounded. There are no writes, secret-value reads or arbitrary cloud query tools.

Read [CONTRACT.md](CONTRACT.md) for wire fields and MCP limits, and [GOTCHAS.md](GOTCHAS.md)
for failure signatures. Resolve the [offline example](examples/offline.py) from this loaded skill
directory. Do not import the data-connectors sibling; this skill includes its own declared dependency.

## Remove

Disable the server or uninstall the containing `harness-data` plugin. A direct consumer stops its
process and removes the copied dependency. Cloud resources and role assignments are not removed.