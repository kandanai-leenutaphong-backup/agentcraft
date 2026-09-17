# CONTRACT.md — agent-config-build

The YAML schema. Everything else in this box is one implementation of this
document.

---

## 1. Tree layout

```
control/
  agent_config.yaml     base: cross-cutting config + include list
  agents/*.yaml         fragments: one per use case, each owning a roster
  prompts/              instruction files, referenced by relative path
    _shared.md            foundation prompts, conventionally underscore-prefixed
    <group>/<agent>.md    per-agent instructions
```

`control/` may be named anything; the consumer passes its path. The `prompts/`
subdirectory name comes from `prompts_dir` and resolves relative to the
directory holding `agent_config.yaml`.

## 2. Base file keys

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `agents` | mapping | yes | Agent definitions plus the reserved `default` key |
| `include` | list of paths | no | Fragments to merge, relative to this file |
| `foundation_prompts` | list of filenames | no | Prepended to **every** agent, in listed order |
| `prompts_dir` | string | no | Prompt directory name. Default `prompts` |
| `tool_display_names` | mapping | no | Tool function name to UI label |

Any other top-level key is preserved and readable via `load_agent_config()`.
This package does not interpret it.

## 3. Reserved keys

Inside the `agents:` block, two keys are **not** agent definitions:

| Key | Meaning |
| --- | --- |
| `default` | Agent id used when a caller names none |
| `mode` | Reserved; ignored |

They are skipped by `iter_agents()` and rejected by `find_agent()`, so no agent
may be named `default` or `mode`.

## 4. Agent definition

```yaml
agents:
  researcher:                       # agent id: stable, referenced by clients
    name: Researcher                # display name
    description: "One line."        # shown in pickers
    model: gpt-5.4                  # passed through verbatim to the SDK
    surface: hidden                 # optional; "hidden" omits from user pickers
    instructions:                   # prompt files, relative to prompts_dir
      - demo/researcher.md
    tools:                          # tool specs, resolved in listed order
      - my_tools.notes:search_notes
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | no | Falls back to the agent id |
| `description` | string | no | Empty string when absent |
| `model` | string | no | Falls back to `default_model`, then the SDK default |
| `instructions` | list of paths, or one path | no | Order preserved |
| `tools` | list of spec strings | no | Order preserved |
| `surface` | string | no | Consumer vocabulary; `hidden` is the one convention |

Every other key lands on `AgentSpec.extra`, untouched.

## 5. Tool spec grammar

Two forms, discriminated by the `@server:` prefix.

```
local:   "<module.path>:<function_name>"
server:  "@server:<name>"
         "@server:<name>:<json-params>"
```

**Local specs** resolve through `importlib`. The module path must start with an
allowlisted prefix or resolution raises. The allowlist is empty by default:
nothing is importable until the consumer declares a prefix. This is the control
that stops a configuration file from importing an arbitrary module path.

**Server specs** are built by a consumer-registered factory:

```python
agentconfig.register_server_tool("web_search", lambda p: WebSearchTool(**p))
```

No factories ship built in, so this package depends on no cloud SDK. An
unregistered name raises, listing the names that are registered.

## 6. Instruction composition

```
foundation_prompts (in listed order)
    + agent instructions (in listed order)
joined by a blank line
```

Per-entry resolution:

| Entry resolves to | Behaviour |
| --- | --- |
| A file with text | Appended |
| A directory | Every `*.md` inside, sorted by name, appended |
| A file that is empty | Counted as unresolved |
| A missing file | Counted as unresolved, logged as a warning |
| A path escaping `prompts_dir` | `ValueError` |

If the `instructions` list is **non-empty** and nothing resolved to text,
`PromptLoadError` is raised. An **empty** list is legal and yields an empty
prompt: that is how a tool-only or test agent is expressed.

Missing *foundation* prompts warn rather than raise, because foundation text is
cross-cutting and a partial load still yields a usable agent.

## 7. Include merge

Fragments contribute exactly two keys:

| Fragment key | Merged? |
| --- | --- |
| `agents` | yes, into the base roster |
| `tool_display_names` | yes; later fragments overwrite earlier keys |
| anything else | **no — parsed and discarded** (GOTCHAS.md G4) |

Rules:

- Paths are relative to the base file's directory.
- A missing fragment raises `RuntimeError`.
- A duplicate agent id across any two sources raises `ValueError`.
- Reserved keys inside a fragment's `agents:` block are skipped.
- Scalar base keys (`prompts_dir`, `foundation_prompts`, `default`) are owned by
  the base file and never merged from fragments.

## 8. Caching

The merged config is cached against an mtime signature spanning the base file
and every resolved fragment, so editing any fragment invalidates it. Call
`invalidate_config_cache()` after writing YAML programmatically inside a
process; it also clears the foundation-prompt cache.

### Opt-in strict loading and source tracking

Existing positional arguments, return types and defaults remain unchanged:

```python
load_agent_config(config_path=None, *, strict=False, sources=None) -> dict
load_instructions(paths, prompts_dir, preamble_path=None, *, strict=False, sources=None) -> str
```

`strict=True` on `load_agent_config` requires a real base file and mapping roots
with mapping `agents` blocks. It rejects duplicate YAML keys at every depth,
invalid include lists, include or `prompts_dir` paths escaping the configuration
directory (including symlinks), non-mapping display names, and agent/display-name
collisions across includes. Unlike default merging, reserved fragment keys are
not skipped: they also collide with an existing base key. Other scalar keys
remain base-owned. Distinct fragment display names remain additive; strict mode
never overwrites an existing label. Missing files raise `OSError` or
`RuntimeError`; invalid YAML, shapes, paths and collisions raise `ValueError`.

`strict=True` on `load_instructions` requires every named prompt, including any
preamble, to be a non-empty file confined to `prompts_dir`; missing, empty,
directory and escaping entries raise `ValueError` even when other entries load.
An empty list still returns an empty string. Hosts can pass foundation references
through this same API when every foundation file is required. Default
`load_foundation_prompts`, `build_spec` and all tool-resolution APIs are unchanged.

Both functions optionally append `(resolved_path, raw_bytes)` to a caller-owned
`list[tuple[Path, bytes]]`. Config sources are base then includes; prompt sources
are preamble then entries. Order, repeated references and raw line endings are
preserved; composed text retains normal text-file newline normalization and
trimming. Tracking or strict config reads bypass, and do not populate, legacy
caches. Sources already read remain appended if a later entry fails.

The Investigation caller uses explicit paths and strict options, hashes the raw
base/include/foundation/instruction bytes in that order into its existing
12-character SHA-256 prefix, and retains per-file prompt metadata. Its model,
runtime limits, display requirements, local-only tool resolver, execution grants,
required template foundations and persisted-version policy remain host-owned.

## 9. Resolved output

```python
@dataclass(frozen=True, slots=True)
class AgentSpec:
    agent_id: str
    name: str
    description: str
    model: str
    instructions: str          # foundation + per-agent, composed
    tools: tuple[Any, ...]     # imported callables / platform objects
    surface: str
    extra: dict[str, Any]      # every unrecognised key from the definition
```

## 10. Errors

| Raised | When |
| --- | --- |
| `AgentNotFound` | Unknown or reserved agent id; subclass of `ValueError` |
| `PromptLoadError` | Non-empty instructions list resolved to no text |
| `ValueError` | Bad spec format, disallowed prefix, duplicate id, traversal |
| `ImportError` | Tool module not importable |
| `AttributeError` | Function absent from the module |
| `TypeError` | Named attribute is not callable |
| `RuntimeError` | No control dir configured, or a missing include fragment |

## 11. Minimal working config

```yaml
# control/agent_config.yaml
prompts_dir: prompts
agents:
  default: solo
  solo:
    name: Solo
    model: gpt-5.4
    instructions: [solo.md]
    tools: []
```

```python
import agentconfig
agentconfig.configure("control", allowed_tool_prefixes=("mytools.",))
spec = agentconfig.build_spec()
```

---

## Local Authoring Store

`AgentVersionStore(root, *, builtin_id, builtin, validate, validate_assignment)` owns
immutable agent versions and one pinned assignment per owner. `root` is a host-selected
`Path`; `builtin` is an `AgentDraft`. Both policy callbacks are required:
`validate(AgentDraft) -> None` runs before save and assignment; then
`validate_assignment(AgentVersion) -> None` runs before assignment publication.
Callbacks raise to refuse. The store knows no models, tools, roles, principals, issuers,
settings or application imports. Host adapters authenticate and authorize every call.

Public operations accept an already-authorized, nonempty opaque `owner_id: str`:

| Operation | Result |
| --- | --- |
| `save(owner_id, SaveAgent, agent_id=None)` | New `AgentVersion`; no overwrite, return after read-back. |
| `get(owner_id, agent_id, version=None)` | Specified or latest `AgentVersion`. |
| `versions(owner_id, agent_id)` | Sorted distinct version numbers. |
| `version_names(owner_id, agent_id)` | Number-to-label mapping, including empty legacy labels. |
| `list(owner_id)` | Summaries including builtin, versions, labels and selected tool IDs. |
| `assignment(owner_id)` | `AgentAssignment`; defaults to builtin version 1, revision 0. |
| `assign(owner_id, AssignAgent)` | Pinned assignment with incremented revision, read back after write. |

`AgentDraft` contains name, model, optional version label, system prompt, Markdown instruction
files and tool IDs. `SaveAgent` adds `base_version` and `expected_latest_version`.
`AgentVersion` adds schema version 1, agent ID, version, base version, creation timestamp and
the original owner ID. `AssignAgent` carries agent ID, version and `expected_revision`;
`AgentAssignment` replaces expected revision with persisted revision. Unknown fields refuse.
`AGENT_ID` and `MAX_INSTRUCTION_BYTES` expose the identifier pattern and combined instruction cap.
Pydantic schema validation errors remain `ValidationError` at request construction.

Storage layout is unchanged from Investigation authoring:

```text
<root>/<sha256(owner_id.encode("utf-8")).hexdigest()>/
  .lock
  <agent_id>/versions/<number>.json
  roles.json
```

Owner IDs are not normalized or interpreted as paths. Stored version owner, agent ID and
number must match the request. Malformed JSON/schema and mismatched records refuse as
`AgentStoreError(status=404, detail=...)`; an existing edit validates base and latest records
before writing. Stored assignments must resolve to an owner-readable version. Symlinked
owner namespaces, agents, version directories, version files, role files and lock files refuse.
Missing agents/versions use 404, invalid owner/location uses 400, stale version/assignment CAS
uses 409. Host policy may use 422. Filesystem failures propagate as `OSError`; hosts translate
these separately from refusal. `AgentStoreError` is a `ValueError` with `.status` and detail
available through `str(error)`.

Each write holds a per-owner POSIX `flock`. Versions publish with exclusive `os.link`;
assignment replaces with `os.replace`. Temporary files are written in the destination directory,
flushed and file-fsynced, then cleaned on success or failure. New directories use mode 0700;
new JSON and lock files use 0600. There is no directory fsync, transaction across builtin
bootstrap and later publication, journal, network-filesystem guarantee, or crash-durability
claim. A failed later publication can leave a successfully bootstrapped builtin version.
Trusted host-controlled local filesystem is required: path checks do not defend against a
hostile local process racing symlink replacement, and valid payloads are not cryptographically
authenticated. File content changes that retain valid schema and matching identity are not
detectable as tampering. The store does not authenticate owner IDs.

Builtin version 1 is virtual until the first edit or explicit assignment pins it to disk.
Persisted builtin bytes never track later deployment changes. A missing `version_name` reads
as `""` without rewriting the record. Existing instruction content, field order, JSON indentation,
trailing newline, owner namespace and `roles.json` format remain unchanged; no migration runs.

Verification from repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 python -m pytest -p no:cacheprovider libraries/modular-agents/modules/agent-config-build/tests/test_agent_version_store.py -q
```

<!-- api-surface:start -->

## Public surface

Names exported by [agentconfig](agentconfig/__init__.py). The public source owns signatures;
this reference does not require a retired template generator.

| Name | Kind | Description |
| --- | --- | --- |
| `AgentVersionStore` | class | Owner-scoped local immutable versions and pinned assignment with host policy callbacks. |
| `AgentDraft`, `SaveAgent`, `AgentVersion`, `InstructionFile` | models | Validated authoring request and persisted version schemas. |
| `AgentAssignment`, `AssignAgent` | models | Pinned assignment response and CAS request schemas. |
| `AgentStoreError` | class | Store refusal carrying status and detail. |
| `AGENT_ID`, `MAX_INSTRUCTION_BYTES` | constants | Agent identifier pattern and aggregate instruction byte bound. |
| `configure` | function | One-call composition-root setup. |
| `set_control_dir` | function | Register the process-wide default control directory. |
| `set_allowed_tool_prefixes` | function | Register the process-wide default importable tool-module prefixes. |
| `set_default_agent` | function | Register the fallback agent id used when a config omits ``default``. |
| `AgentSpec` | class | One agent, fully resolved and ready to hand to an SDK. |
| `build_agents` | function | Resolve every agent and hand each spec to the consumer's factory. |
| `build_all_specs` | function | Resolve every agent in the merged config. |
| `build_spec` | function | Resolve one agent id (or the configured default) to an ``AgentSpec``. |
| `tool` | function | Mark a function as agent-callable. Usable bare or with arguments. |
| `is_tool` | function | True when ``fn`` carries the marker. |
| `tool_metadata` | function | Return the stamped metadata, or an empty dict for an unstamped callable. |
| `TOOL_MARKER` | constant | '__agentconfig_tool__' |
| `register_server_tool` | function | Register a factory for the ``@server:<name>`` spec form. |
| `resolve_tool` | function | Resolve a tool spec to a callable or platform tool object. |
| `resolve_tools` | function | Batch-resolve tool specs. |
| `load_agent_config` | function | Parse an agent config YAML file, merging any ``include:`` fragments. |
| `load_agents_block` | function | Load and cache the agents block from agent_config.yaml. |
| `get_tool_display_names` | function | Return the tool_display_names mapping from agent_config.yaml. |
| `get_control_dir` | function | Return the configured control/ directory. |
| `get_prompts_dir` | function | Return the prompts directory path from config. |
| `default_agent_id` | function | Resolve the default agent identifier from ``agent_config.yaml``. |
| `find_agent` | function | Look up a specific agent's config by ID. |
| `iter_agents` | function | Iterate over (agent_id, agent_config) pairs, skipping reserved keys. |
| `resolve_agent_cfg` | function | Resolve an agent ID (or default) to ``(target_id, agent_cfg)``. |
| `invalidate_config_cache` | function | Clear both the YAML LRU cache and the agents block cache. |
| `load_instructions` | function | Load and concatenate prompt files, optionally prepending a preamble. |
| `load_foundation_prompts` | function | Load and cache foundation prompt text from agent_config.yaml. |
| `AgentNotFound` | class | Raised when ``resolve_agent_cfg`` cannot locate an agent ID. |
| `PromptLoadError` | class | Raised when a non-empty ``instructions:`` spec list resolves to no text. |

<!-- api-surface:end -->
