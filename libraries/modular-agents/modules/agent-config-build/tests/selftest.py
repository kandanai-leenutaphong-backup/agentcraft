"""selftest — proves the box works with no test framework installed.

Run: ``python3 tests/selftest.py``. Exits non-zero on any failure.

Covers the three fail-loud guarantees (unresolvable tool, empty prompt,
disallowed import prefix), the include-merge rules, prompt composition order,
and the seam. Checks that pin a documented gotcha are labelled with its number.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "examples"))

import agentconfig
from agentconfig import AgentNotFound, AgentSpec, PromptLoadError

_EXAMPLE = _ROOT / "examples" / "control"
_FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)


def raises(exc_types, fn) -> bool:
    """True when calling fn raises one of exc_types."""
    try:
        fn()
    except exc_types:
        return True
    except Exception:
        return False
    return False


def _use_example() -> None:
    agentconfig.invalidate_config_cache()
    agentconfig.configure(_EXAMPLE, allowed_tool_prefixes=("my_tools.",))


def _write_tree(root: Path, base: str, fragments: dict[str, str],
                prompts: dict[str, str]) -> Path:
    """Materialise a throwaway control tree and point the loader at it."""
    control = root / "control"
    (control / "agents").mkdir(parents=True, exist_ok=True)
    (control / "prompts").mkdir(parents=True, exist_ok=True)
    (control / "agent_config.yaml").write_text(base, encoding="utf-8")
    for name, text in fragments.items():
        (control / "agents" / name).write_text(text, encoding="utf-8")
    for name, text in prompts.items():
        path = control / "prompts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    agentconfig.invalidate_config_cache()
    agentconfig.configure(control, allowed_tool_prefixes=("my_tools.",))
    return control


# `agents:` comes last so a test can append an agent definition to this string.
_MIN_BASE = """
prompts_dir: prompts
agents:
  default: solo
"""


def main() -> int:
    print("loading and merging")
    _use_example()
    cfg = agentconfig.load_agent_config()
    check("base config loads", bool(cfg))
    check("include: consumed by the merge", "include" not in cfg)
    check("base top-level keys survive the merge", "runtime" in cfg)

    block = agentconfig.load_agents_block()
    ids = [aid for aid, _ in agentconfig.iter_agents(block)]
    check("fragment agents merged into base",
          ids == ["researcher", "assistant", "summariser"])
    check("'default' excluded from agent ids", "default" not in ids)
    check("default agent resolves",
          agentconfig.default_agent_id() == "researcher")
    check("tool display names available",
          agentconfig.get_tool_display_names().get("search_notes") == "Search Notes")

    print("spec building")
    spec = agentconfig.build_spec("researcher")
    check("returns an AgentSpec", isinstance(spec, AgentSpec))
    check("name resolved", spec.name == "Researcher")
    check("model passed through", spec.model == "gpt-5.4")
    check("tools imported in configured order",
          [t.__name__ for t in spec.tools] == ["search_notes", "word_count"])
    check("foundation prompt prepended",
          spec.instructions.startswith("# House style"))
    check("per-agent prompt appended", "# Researcher" in spec.instructions)
    check("spec is immutable",
          raises(Exception, lambda: setattr(spec, "name", "x")))

    hidden = agentconfig.build_spec("summariser")
    check("surface: hidden detected", hidden.is_hidden is True)
    check("visible agent not hidden", spec.is_hidden is False)
    check("tool-free agent allowed", hidden.tools == ())
    check("unknown per-agent keys reach extra (G4)",
          hidden.extra.get("role") == "summarizer" and "triggers" in hidden.extra)
    check("known keys absent from extra",
          not {"name", "model", "tools"} & set(hidden.extra))

    check("default resolved when id omitted",
          agentconfig.build_spec().agent_id == "researcher")
    check("unknown agent id raises AgentNotFound",
          raises(AgentNotFound, lambda: agentconfig.build_spec("nope")))
    check("reserved key is not an agent",
          raises(AgentNotFound, lambda: agentconfig.build_spec("default")))

    all_specs = agentconfig.build_all_specs()
    check("build_all_specs covers the roster", set(all_specs) == set(ids))

    print("the seam")
    built = agentconfig.build_agents(lambda s: ("built", s.agent_id))
    check("factory called once per agent", len(built) == len(ids))
    check("factory output returned verbatim",
          built["researcher"] == ("built", "researcher"))

    print("aliasing")
    alias = agentconfig.build_spec("assistant")
    check("YAML anchor shares prompt text (G6)",
          alias.instructions == spec.instructions)
    check("YAML anchor shares tool list (G6)",
          [t.__name__ for t in alias.tools] == [t.__name__ for t in spec.tools])

    print("fail-closed tool resolution")
    check("disallowed prefix raises (G2)",
          raises(ValueError, lambda: agentconfig.resolve_tool(
              "os.path:join", allowed_prefixes=("my_tools.",))))
    check("empty allowlist blocks everything (G2)",
          raises(ValueError, lambda: agentconfig.resolve_tool(
              "my_tools.notes:search_notes", allowed_prefixes=())))
    check("missing function raises (G1)",
          raises(AttributeError, lambda: agentconfig.resolve_tool(
              "my_tools.notes:nope", allowed_prefixes=("my_tools.",))))
    check("malformed spec raises",
          raises(ValueError, lambda: agentconfig.resolve_tool(
              "my_tools.notes", allowed_prefixes=("my_tools.",))))
    check("unknown @server tool raises",
          raises(ValueError, lambda: agentconfig.resolve_tool("@server:nothing")))
    check("skip mode tolerates a bad spec (G1)",
          agentconfig.resolve_tools(["my_tools.notes:nope"],
                                    allowed_prefixes=("my_tools.",),
                                    on_missing="skip") == [])

    agentconfig.register_server_tool(
        "echo", lambda params: {"kind": "echo", **params})
    check("registered @server tool resolves",
          agentconfig.resolve_tool('@server:echo:{"a":1}')
          == {"kind": "echo", "a": 1})

    print("tool decorator")
    from my_tools.notes import search_notes
    from my_tools.text import _normalise, summarise_text
    check("stamped function is a tool", agentconfig.is_tool(search_notes))
    check("unstamped function is not", not agentconfig.is_tool(_normalise))
    check("docstring becomes description",
          "Search the note store"
          in agentconfig.tool_metadata(search_notes)["description"])
    check("decorator returns the function unwrapped",
          search_notes("onboarding")["status"] == "ok")
    check("explicit description overrides docstring",
          agentconfig.tool_metadata(summarise_text)["description"]
          == "Return the first N sentences of a passage.")

    print("fail-loud config errors")
    with tempfile.TemporaryDirectory() as tmp:
        _write_tree(Path(tmp), _MIN_BASE + """
  solo:
    name: Solo
    model: m
    instructions:
      - missing/nope.md
    tools: []
""", {}, {})
        check("missing prompt file raises PromptLoadError (G3)",
              raises(PromptLoadError, lambda: agentconfig.build_spec("solo")))

    with tempfile.TemporaryDirectory() as tmp:
        _write_tree(Path(tmp), _MIN_BASE + """
  solo:
    name: Solo
    model: m
    instructions:
      - empty.md
    tools: []
""", {}, {"empty.md": "   \n"})
        check("empty prompt file raises PromptLoadError (G3)",
              raises(PromptLoadError, lambda: agentconfig.build_spec("solo")))

    with tempfile.TemporaryDirectory() as tmp:
        _write_tree(Path(tmp), _MIN_BASE + """
  solo:
    name: Solo
    model: m
    instructions: []
    tools: []
""", {}, {})
        check("empty instructions list is allowed",
              agentconfig.build_spec("solo").instructions == "")

    with tempfile.TemporaryDirectory() as tmp:
        _write_tree(Path(tmp), """
include:
  - agents/a.yaml
  - agents/b.yaml
agents:
  default: dupe
prompts_dir: prompts
""", {
            "a.yaml": "agents:\n  dupe:\n    name: A\n    model: m\n    tools: []\n",
            "b.yaml": "agents:\n  dupe:\n    name: B\n    model: m\n    tools: []\n",
        }, {})
        check("duplicate agent id across fragments fails loud (G5)",
              raises(ValueError, agentconfig.load_agents_block))

    with tempfile.TemporaryDirectory() as tmp:
        _write_tree(Path(tmp), """
include:
  - agents/gone.yaml
agents:
  default: x
""", {}, {})
        check("missing include fragment fails loud",
              raises(RuntimeError, agentconfig.load_agents_block))

    with tempfile.TemporaryDirectory() as tmp:
        control = _write_tree(Path(tmp), _MIN_BASE + """
  solo:
    name: Solo
    model: m
    instructions:
      - ok.md
    tools: []
""", {}, {"ok.md": "first"})
        check("prompt text loads",
              agentconfig.build_spec("solo").instructions == "first")
        (control / "prompts" / "ok.md").write_text("second", encoding="utf-8")
        agentconfig.invalidate_config_cache()
        check("cache invalidation picks up an edit (G7)",
              agentconfig.build_spec("solo").instructions == "second")

    print("path traversal")
    with tempfile.TemporaryDirectory() as tmp:
        control = _write_tree(Path(tmp), _MIN_BASE, {}, {"ok.md": "x"})
        check("prompt path escaping prompts_dir is rejected",
              raises(ValueError, lambda: agentconfig.load_instructions(
                  ["../../etc/passwd"], control / "prompts")))

    print("opt-in strict configuration")
    with tempfile.TemporaryDirectory() as tmp:
        control = _write_tree(Path(tmp), """
include: [agents/solo.yaml]
agents: {default: solo}
tool_display_names: {base_tool: Base}
runtime: {owner: host}
""", {"solo.yaml": "agents: {solo: {model: fixture}}\ntool_display_names: {other: Other}\n"}, {})
        config_path = control / "agent_config.yaml"
        sources: list[tuple[Path, bytes]] = []
        legacy = agentconfig.load_agent_config(config_path)
        strict = agentconfig.load_agent_config(config_path, strict=True, sources=sources)
        check("strict valid roster matches default API", strict == legacy)
        check("strict preserves base scalars", strict["runtime"] == {"owner": "host"})
        check("strict source bytes preserve base/include order", sources == [
            (path, path.read_bytes()) for path in (config_path, control / "agents" / "solo.yaml")])
        check("legacy cache is unchanged by strict loading",
              agentconfig.load_agent_config(config_path) is legacy)
        config_path.write_text("agents: {}\nagents: {}\n", encoding="utf-8")
        agentconfig.invalidate_config_cache()
        check("default retains duplicate YAML last-key-wins",
              agentconfig.load_agent_config(config_path)["agents"] == {})
        check("strict rejects duplicates even after a permissive cache hit",
              raises(ValueError, lambda: agentconfig.load_agent_config(config_path, strict=True)))
        outside = Path(tmp) / "outside.yaml"
        outside.write_text("agents: {outside: {}}\n", encoding="utf-8")
        config_path.write_text("agents: {}\ninclude: [../outside.yaml]\n", encoding="utf-8")
        agentconfig.invalidate_config_cache()
        check("default retains external include paths",
              "outside" in agentconfig.load_agent_config(config_path)["agents"])
        check("strict rejects include escape",
              raises(ValueError, lambda: agentconfig.load_agent_config(config_path, strict=True)))
        for invalid in (
            "agents: {}\ninclude: [agents/missing.yaml]\n",
            "agents: {}\ninclude: [null]\n",
            "agents: {}\ninclude: null\n",
            "agents: {}\nprompts_dir: ../outside\n",
            "agents: []\n",
            "agents: {}\ntool_display_names: []\n",
            "",
        ):
            config_path.write_text(invalid, encoding="utf-8")
            check(f"strict rejects invalid config {invalid!r}", raises(
                (ValueError, RuntimeError), lambda: agentconfig.load_agent_config(config_path, strict=True)))
        fragment = control / "agents" / "solo.yaml"
        for fragment_text in (
            "agents: {default: solo}\n",
            "agents: {solo: {}, solo: {}}\n",
            "agents: {}\ntool_display_names: {base_tool: Replacement}\n",
        ):
            config_path.write_text(
                "agents: {default: solo}\ninclude: [agents/solo.yaml]\ntool_display_names: {base_tool: Base}\n",
                encoding="utf-8")
            fragment.write_text(fragment_text, encoding="utf-8")
            check(f"strict refuses fragment collision {fragment_text!r}", raises(
                ValueError, lambda: agentconfig.load_agent_config(config_path, strict=True)))
        missing = control / "missing.yaml"
        check("default missing base remains an empty mapping", agentconfig.load_agent_config(missing) == {})
        check("strict missing base refuses", raises(
            FileNotFoundError, lambda: agentconfig.load_agent_config(missing, strict=True)))

    _use_example()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
