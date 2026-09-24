---
name: agent-config-build
description: Define agents declaratively in YAML instead of Python - model, prompt files, and tool list per agent, merged from per-use-case fragments, with fail-closed tool imports and fail-loud prompt resolution. Use when adding or crafting an agent, wiring tools to an agent, organising prompts, splitting a growing agent roster, when a tool silently never loads, when an agent behaves as if it has no system prompt, when a config edit has no effect, or when agent construction code is duplicated across a codebase.
license: MIT
---

# Agent config build

An agent is a configuration entry, not a class. Adding one is a YAML block plus
prompt files. Nothing in the runtime changes.

```
YAML roster -> merge fragments -> compose prompts -> resolve tools -> AgentSpec
                                                                         |
                                                    your factory --------+
                                                                         |
                                                              your SDK's agent
```

## Decide in one line

| Situation | Action |
| --- | --- |
| Add an agent | New block in a fragment + prompt file. Nothing else |
| Add a tool to an agent | One line under its `tools:` |
| Add a use case | New `agents/<name>.yaml` + one `include:` line |
| Rule every agent needs | Add to `foundation_prompts`, not to each prompt |
| Tool never gets called | GOTCHAS.md G1, then G10 |
| Agent ignores its persona | G3 |
| Config edit had no effect | G7 locally, G8 when deployed |
| Fragment key ignored | G4 |
| Renaming an agent | G6 — alias it, do not rename |
| Writing a loader in another language | CONTRACT.md only |

## Install

```bash
cp -r agent-config-build/agentconfig  <your-app>/
pip install pyyaml 'pydantic>=2.11,<3'
```

Create the control tree (copy `examples/control/` as a starting point):

```
control/
  agent_config.yaml
  agents/demo.yaml
  prompts/_house_style.md
  prompts/demo/researcher.md
```

Wire it once, at your composition root:

```python
import agentconfig

agentconfig.configure(
    "control",
    allowed_tool_prefixes=("my_tools.",),   # fail-closed: empty imports nothing
    default_agent="researcher",
)

# The factory is the ONLY code you write. Replace the body with your SDK.
def make_agent(spec: agentconfig.AgentSpec):
    return ChatAgent(
        name=spec.name,
        instructions=spec.instructions,
        tools=list(spec.tools),
        model=spec.model,
    )

agents = agentconfig.build_agents(make_agent)   # build at boot, fail at boot
```

See `examples/build_agent.py` for a runnable version.

## Author an agent

```yaml
# control/agents/demo.yaml
agents:
  researcher:
    name: Researcher
    description: "Searches notes and answers with citations."
    model: gpt-5.4
    instructions:
      - demo/researcher.md
    tools:
      - my_tools.notes:search_notes
```

Then `include: [agents/demo.yaml]` in the base file. Ids are public: clients
and saved sessions reference them, so treat a rename as a breaking change (G6).

## Author a tool

```python
from agentconfig import tool

@tool
def search_notes(query: str, limit: int = 3) -> dict:
    """Search the note store and return matching notes.

    Use for any question about internal process. An empty `notes` list means
    the answer is not in the store -- say so rather than answering from memory.

    Args:
        query: Words to look for.
        limit: Maximum notes to return.
    """
    return {"status": "ok", "count": len(hits), "notes": hits}
```

Four conventions that matter more than they look:

1. **The docstring is the model's documentation.** State *when to call* and
   *how to read an empty result*. A model cannot infer either from a signature.
2. **Return a uniform envelope** with a `status` enum the model dispatches on.
   One result shape across every tool, never prose to be parsed.
3. **`@tool` returns the function unwrapped.** No SDK is imported, so tools are
   unit-testable by calling them, and swapping SDKs is one edit in your factory.
4. **Inline parameter annotations.** A module-level annotated alias used as a
   parameter type can break SDK schema generation for the whole agent (G10).

## Verify

```bash
python3 scripts/validate_config.py control \
    --allow-prefix my_tools. --import-path . [--strict]
```

Checks every agent builds, every prompt resolves, every tool imports, the
default exists, display names match real tools, and no fragment key is being
silently dropped. Non-zero exit on error. Run it in CI on every control-tree
change.

```bash
python3 tests/selftest.py       # 47 checks, no test framework needed
python3 -m pytest tests/ -q     # full suite
```

## The rules

1. **The tool allowlist is empty by default.** Config names code; nothing is
   importable until you declare a prefix. Never widen it to a bare package root
   you do not control.
2. **Fail at boot, not at first use.** Build every agent at startup so a typo
   in any definition stops the process, rather than surfacing when a user picks
   that agent.
3. **Never let a missing tool or prompt pass quietly.** An agent that loses a
   capability invents an answer; an agent that crashes gets fixed.
4. **Foundation prompts are roster-wide.** One edit changes every agent, so
   only genuinely universal rules go there — and re-run evaluations across the
   whole roster afterwards (G9).
5. **Alias, do not rename.** Keep old ids as hidden aliases sharing a YAML
   anchor, so saved sessions keep resolving (G6).
6. **Unknown keys are preserved, not rejected.** Carry your own metadata on
   agents via `AgentSpec.extra` — but know that fragment-*level* keys are
   dropped (G4).

## Removal

1. Delete the `agentconfig` package and your factory function.
2. Construct agents in Python again.

YAML loading leaves no runtime state to unwind. `AgentVersionStore` authoring
persists versions and assignments under a host-configured root; preserve that
user data when removing the package. See CONTRACT.md for the store API and
POSIX locking and durability limits.

## Reference

- `README.md` — why declarative, design decisions, what changed in extraction
- `CONTRACT.md` — the exact YAML schema; all a reimplementation needs
- `GOTCHAS.md` — ten production failures, symptom-first
- `examples/` — a complete working control tree, tool modules, and the factory
