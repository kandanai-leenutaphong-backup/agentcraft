# agent-config-build

Define agents declaratively: a YAML block naming a model, prompt files, and
tool specs. Adding an agent is **one config entry plus one prompt file**, with
no change to the runtime.

Self-contained. Copy this folder anywhere. Dependencies: Python 3.10+ and
PyYAML. No agent SDK, no cloud SDK, no web framework.

```
agent-config-build/
  README.md            you are here — rationale and design decisions
  SKILL.md             agent-facing: author an agent, author a tool, verify
  CONTRACT.md          the exact YAML schema; all a reimplementation needs
  GOTCHAS.md           ten production failures, symptom-first
  agentconfig/         the mechanism (~1,150 lines)
    _config.py           YAML load, include-merge, caching, typed lookup
    _prompts.py          foundation + per-agent prompt composition
    _tools.py            fail-closed importlib resolution, server-tool registry
    _decorator.py        SDK-free @tool stamp
    _spec.py             composition into AgentSpec — the seam
  scripts/
    validate_config.py   lint a control tree; non-zero exit on error
  examples/
    control/             a complete, working config tree
    my_tools/            two tool modules
    build_agent.py       the factory, runnable
  tests/
    selftest.py          47 checks, no test framework required
```

---

## 1. The problem

Agents defined in Python drift. Each grows its own construction code. Its
prompt ends up in a string literal or a file nobody can find. Its tool list
becomes an import block. Adding the fifth agent means editing five files, and
nobody can answer *"what agents exist and what can each of them do"* without
reading the code.

| Symptom | Cause |
| --- | --- |
| Prompt changes need a code review and a redeploy | Prompt text lives in code |
| Two agents drift apart that should be identical | Their construction was copy-pasted |
| Nobody knows the full roster | It is spread across modules |
| Adding a tool touches several files | Tool wiring is imperative |
| A capability quietly disappears | An import failure was swallowed |

## 2. The approach

Move the definition into data and keep exactly one integration point in code.

| Property | How |
| --- | --- |
| One file + one entry per agent | Roster in YAML; runtime reads it |
| Roster splits cleanly | `include:` fragments, one per use case |
| Cross-cutting rules live once | `foundation_prompts` prepended to every agent |
| Prompts are reviewable | Plain `.md` files, versioned, diffable |
| Tools are declarative | `module.path:function` strings, resolved at build |
| Config cannot import anything | Fail-closed prefix allowlist, empty by default |
| Broken definitions stop the boot | Fail-loud prompt and tool resolution |
| No SDK lock-in | One consumer factory turns a spec into an agent |

## 3. Failure model

**Prevents:** an agent shipping without its tools; an agent shipping without a
system prompt; a config file importing an arbitrary module; a duplicate agent
id silently shadowing another; a prompt path escaping the prompts directory; a
stale cache serving an old parse after an edit.

**Does not prevent:** a prompt that is present but wrong; a tool that imports
and misbehaves; a model id the SDK rejects; semantic mistakes in the roster
such as giving an agent a tool it should not have. Those need evaluation, not
validation.

**Deliberate trade-off.** Fail-closed and fail-loud both convert convenience
into boot-time errors. A misconfigured agent that starts is worse than one that
refuses to, because it answers anyway and the output looks fine.

## 4. Why it is portable

One decision: **the package never builds an agent.**

```
control/*.yaml ──► AgentSpec ──inject──► your factory ──► your SDK's agent
```

`build_agents(factory)` resolves every definition and hands each spec to the
consumer's function. That function is the whole integration surface. The
package imports no agent SDK, so the same control tree drives whatever
framework you are on this year.

Two supporting decisions keep it from leaking:

- **Unknown keys are preserved, not rejected.** Anything the package does not
  recognise inside an agent definition lands on `AgentSpec.extra`. Consumers
  carry roles, feature flags, and UI hints in the same file without this
  package knowing what any of it means.
- **Platform tools are registered, not built in.** `register_server_tool` takes
  a factory, so hosted-tool support costs no cloud dependency here.

## 5. Design decisions worth keeping

- **Reserved keys inside the roster.** `default` sits in the `agents:` block
  rather than beside it, so the landing agent is defined next to the agents.
  The cost is that `default` and `mode` cannot be agent ids; iteration skips
  them everywhere so the rule cannot be half-applied.
- **Fragments merge only two keys.** `agents` and `tool_display_names`. Scalars
  stay owned by the base file, so there is never a question of which fragment
  won. The cost is silent loss of other fragment keys — real enough to warrant
  G4 and a linter warning.
- **Duplicate ids raise.** Last-write-wins would make a definition invisible.
- **Cache key spans every fragment's mtime.** Editing a fragment invalidates
  the cache even though the base file is untouched, so development hot-reload
  is correct without disabling caching in production.
- **Empty instructions list is legal; a non-empty one that resolves to nothing
  is not.** Distinguishing "specified nothing" from "specified things that all
  failed" is what makes the error trustworthy enough to raise on.
- **Display names are flat and global.** A tool has one name wherever it is
  used, so it gets one label. Per-agent labels would let the same tool appear
  under two names in one product.
- **`@tool` stamps and returns unwrapped.** Tools stay plain functions: unit
  tests call them directly, no SDK is imported at module load, and an SDK swap
  is one edit in the factory rather than an edit in every tool file.
- **Tool order is preserved.** Some SDKs surface tools to the model in list
  order, so the config's order is meaningful and is not sorted.

## 6. Quick start

```bash
pip install pyyaml
python3 examples/build_agent.py
```

Prints the resolved roster: three agents, their prompt sizes, tool lists, and
the extra keys that survived. Then lint the example tree:

```bash
python3 scripts/validate_config.py examples/control \
    --allow-prefix my_tools. --import-path examples
```

Prove the box works here before trusting it:

```bash
python3 tests/selftest.py
```

## 7. Removal

1. Delete the `agentconfig` package and your factory function.
2. Construct agents in Python again, or swap in another loader that reads the
   same tree — `CONTRACT.md` is sufficient to write one.

There is no runtime state to unwind and no rollback step: the package only
reads files and returns objects. The control tree remains valid data.

## 8. Provenance

Extracted from a production deployment running three separate use cases from
one control tree, with a roster of roughly fifteen agents across those
fragments. Every gotcha except G4 was hit in production; G4 was found while
writing the example for this box, when a fragment-level block that the docs
claimed reached the consumer turned out to be discarded by the merge.

**Changed during extraction**, and disclosed because packaging should not
silently alter behaviour:

- Cloud-specific server-tool factories were replaced by
  `register_server_tool()`. Keeping them would have made a vendor SDK a
  dependency of a YAML loader. Local tool resolution — the part that matters —
  is unchanged.
- Two inert domain-specific prompt placeholder substitutions were dropped.
- `_spec.py` and `_decorator.py` are new. The origin composed specs inside an
  SDK-coupled builder; splitting the composition out is what makes the seam a
  single function.
