# Shared Plugin Handoff

This migration owns only `core/skills/modular-agents/`. The concurrent migration
owns shared package/catalogue metadata, repository README and root plugin tests.
No sibling skill, origin checkout, root installer, root MCP manifest or catalogue
version is changed by this migration.

## Discovery

Add/discover exactly one skill: `modular-agents`. Its immediate `SKILL.md` names
the directory and routes to four internal modules. The nested preserved SKILL
documents are supporting material, not four separately selectable plugin skills.

The package is installed in a dedicated environment to prevent collision with
the unrelated canvas package also named `agentconfig`. It does not import the
concurrently migrated data, model, access-management or application-composition
skills; private tool dependencies must be explicitly bundled or installed.

## Callable Access

The capability is callable through its public Python packages and
`deploy/deploy.sh`, and the resulting agent exposes authenticated Foundry
invocations. No MCP server is automatically registered. In particular, adding
this skill must not automatically expose cloud deployment, grant mutation or paid
inference as model-callable plugin tools.

If an MCP adapter is desired later, keep build inspection separate from mutation,
use the official SDK and server-side validation, use the same public APIs, and
give its launcher a separate namespace under `PLUGIN_DATA`. The plugin owner
must add its MCP entry at the plugin root and extend every-server acceptance.

## Release Evidence To Join

From this skill root:

```bash
uv sync --locked --no-default-groups --extra dev
.venv/bin/python tests/selftest.py --copy-out
```

The plugin owner should update active-skill discovery expectations and publish
matching catalogue/plugin versions with this complete directory. Run the root
plugin installation check in its isolated client profile only after concurrent
changes are integrated. Standalone skill tests are not remote plugin installation
evidence.