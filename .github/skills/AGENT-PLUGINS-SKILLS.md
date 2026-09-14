# Skill Distribution And Packaging

This checkout ships reusable skills under `.github/skills`. [README.md](README.md) is the human
catalogue; [catalogue.json](catalogue.json) records names, aliases, embedded capabilities and MCP
surfaces. Follow the selected `SKILL.md` for installation and verification. No private source
checkout, customer application, original deployment or repository-root installer is required.

Agent Skills discovery, package installation and MCP registration are different operations.
Loading a skill does not install its Python/npm dependencies, register a server or grant cloud
access. An integrating plugin must supply its own client-compatible manifest and launcher.
The [Agent Plugins specification](https://agent-plugins.org/specification) describes that optional
distribution format; client registration and installation remain client-specific.

## Packaging Procedure

1. **Inventory and baseline.** Identify public APIs, configuration, examples, tests, assets and
   callers. Read the existing checks before changing behavior. Include archive contents and hidden
   files; a clean entry-point description does not establish a clean distribution.
2. **Preserve the capability.** Keep the implementation, contracts, gotchas, tests and useful
   examples together. Anonymize project-specific examples where their meaning survives. Replace
   disputed reference payloads with independently authored examples rather than remove the API.
3. **Resolve dependencies.** Declare installable dependencies or deliberately bundle an owned
   implementation with its license. Do not reach into another checkout. Optional demo dependencies
   must not become implicit runtime requirements.
4. **Verify locally.** Run the existing behavior-scoped tests using injected offline collaborators.
   Include matching refusal cases for identity, ownership, integrity and mutation. Keep fixtures
   synthetic and visibly labelled. Never alter a test just to hide a packaging regression.
5. **Preserve knowledge.** Reconcile the contract, README, gotchas and examples. Keep useful
   failure explanations and stable public names. Do not carry private source-review inventories,
   personal home directories, customer resource IDs or unapproved historical evidence.
6. **Expose the intended interface.** Match the skill directory to its frontmatter name. Catalogue
   guidance, CLI, Python and UI access honestly. MCP is optional: use the official SDK, validate
   server inputs and call the existing capability instead of duplicating its rules.
7. **Isolate state.** Put environments, caches and operator configuration outside the published
   source. Separate each MCP server's environment and configuration. Installation enables neither
   cloud mutation nor paid model calls; these require explicit target-bound operator policy.
8. **Test the distributed artifact.** Check a copied skill or extracted archive outside the source
   checkout with only declared dependencies. For MCP, verify initialization, exact tool discovery,
   status, malformed-input refusal and recovery. For UI, operate actual desktop/mobile controls.
9. **Publish a coherent revision.** Update discovery metadata and changed contracts together. Keep
   source/license notices, locked dependencies and reproducible checks. State unverified live
   behavior separately; offline success is not cloud authorization or marketplace certification.

## Licensing And Data

The repository's existing MIT license applies to its authored implementation. It does not
relicense third-party packages, fonts, artwork, customer data or externally supplied agent tools.
Keep applicable notices with every independently distributed artifact, including ZIP payloads.
Do not manufacture copyright ownership from a missing notice or a private path.

Bundled artwork and fonts require their own recorded rights. The styling skill carries
[asset notices](azure-sky-styling/public/THIRD_PARTY_NOTICES.txt) and a
[per-artifact rights record](azure-sky-styling/research/painterly/RIGHTS.md). The explorer carries
[font notices](resource-explorer/frontend/THIRD_PARTY_NOTICES.txt). Public vendor names, artists'
attributions and official documentation links are not customer-project residue and must remain.

An acquisition receipt is not a redistribution grant. Do not publish material marked for internal
reference unless its rights are established. Preserve URLs and an authored explanation when the
source payload itself cannot be distributed. Never anonymize a license holder's required notice.

Historical measurements and synthetic examples are distinct. An anonymized historical example
must say what was generalized and must not claim a fresh reproduction. A synthetic example must
not be reported as measured performance. Original source revisions and private receipt hashes
are not needed to teach a portable procedure.

## Verification Examples

Resolve `SKILL_ROOT` to the selected installed skill, not the consuming application's root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_ROOT/tests/selftest.py"
```

Use this only when that entry documents a self-test. Other entries supply pytest, unittest,
browser or archive checks. Run the owning check instead of assuming a universal test layout.

For the independent optimization snapshot:

```bash
python3 .github/skills/agent-optimization/scripts/skillpack.py verify
python3 .github/skills/agent-optimization/scripts/skillpack.py extract --destination /tmp/optimization-reference
```

Extraction refuses an existing destination and validates paths, membership, sizes and digests.
The snapshot includes portable runtime sources and explicitly synthetic record shapes; it contains
no customer host application or captured campaign. Its dependencies remain separately declared.

For the optional resource-explorer browser, from that skill's `frontend` directory:

```bash
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npx playwright test
```

Use the browser suite's documented loopback and fixture configuration. Fixture callers exercise
the trusted edge; they do not prove real Entra authentication or authorize a production bypass.

## Removal And Limits

Removing a skill does not revoke cloud roles, delete deployed resources, remove consumer-vendored
code or commit pending recovery artifacts. Those are separate operator-owned lifecycles. Preserve
recovery output before uninstalling a client-managed package that might own its data directory.

Copy-out tests establish the capability on the tested platform. They do not establish legal title
to newly added material, live tenant access, paid-provider compatibility or installation in every
client. Recheck those boundaries when a future release changes them.