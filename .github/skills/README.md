# Skill Catalogue

Generated from [libraries/capabilities.json](../../libraries/capabilities.json). Do not edit this view.

28 named skills, 8 native protocol workflows and 5 embedded guidance entries. Embedded names are lookup aliases in this workspace view and first-class entries in the contained reader package.

[Packaged task index](../../libraries/framework/src/agentcraft/guidance/README.md) links to retained guidance and notices. [Generated metadata](catalogue.json) preserves native task discovery. Use `repository-catalogue --root libraries/framework/src/agentcraft/guidance --list --json`; the workspace catalogue identifies this retained reader package.

Framework runtimes install separately. Authoring-only skills may own scripts and assets without becoming framework libraries. MCP implementation: implemented; verification: offline-verified. Registrations: 0; disabled by default. With the selected installed `mcp` extra, explicitly run `agentcraft mcp --offline` for composition-only synthetic/offline stdio. No data, model, recovery or inventory binding is created. Other targets require a trusted host calling `agentcraft.mcp.create_server` with explicit bindings, exact per-binding tool grants, principal and execution context. Metadata is not activation, credentials, live-service evidence or installed-client acceptance.

[Distribution contract](AGENT-PLUGINS-SKILLS.md) separates installation, activation, authorization and publication.
