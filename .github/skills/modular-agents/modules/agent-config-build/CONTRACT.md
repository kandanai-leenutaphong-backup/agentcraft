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

<!-- api-surface:start -->

## Public surface

Every name exported by `agentconfig`. Generated from the package with `template/api_surface.py`; regenerate after changing `__all__`.

| Name | Kind | Description |
| --- | --- | --- |
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
