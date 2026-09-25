"""Agent composition from configuration.yaml through agentconfig's public API."""

import hashlib
import importlib.util
import inspect
import json
import os
import re
import sys
import types
from dataclasses import replace
from pathlib import Path

from agentconfig import AgentSpec, load_agent_config, load_instructions, resolve_tools

ROOT = Path(__file__).resolve().parent
TOOL_MODULE = "agent_tools"
PACKAGE_ENV = "AGENT_PACKAGE_DIR"
BUILTIN_PACKAGE_MEMBERS = ("configuration.yaml", "prompts", TOOL_MODULE + ".py")
RUNTIME_MODULES = frozenset({"main", "composition", "tool_calls", TOOL_MODULE, "agentconfig", "llm_interface",
                             "agentcraft_core", "agent_package"})
PACKAGE_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
REQUIRED_FIELDS = frozenset({"name", "model", "instructions"})
AGENT_FIELDS = REQUIRED_FIELDS | {"description", "tools"}
OPTIMIZATION_DIR = ROOT / ".agent_configs"
CANDIDATE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
INLINE_FIELDS = frozenset({"name", "instructions", "model", "temperature", "skills", "tools"})


def package_root(environ) -> Path | None:
    """`AGENT_PACKAGE_DIR` when set (must be a directory holding configuration.yaml); None selects the built-in app."""
    if PACKAGE_ENV not in environ:
        return None
    value = environ[PACKAGE_ENV].strip()
    root = Path(value).resolve() if value else None
    if root is None or not root.is_dir() or not (root / "configuration.yaml").is_file():
        raise ValueError(f"{PACKAGE_ENV}={value!r} is not an agent package directory with configuration.yaml")
    return root


def _package_files(root, members):
    for member in members:
        base = root / member
        if base.is_symlink():
            raise ValueError(f"package symlink refused: {member}")
        if base.is_file():
            yield base
            continue
        for directory, subdirectories, names in os.walk(base):
            subdirectories[:] = sorted(name for name in subdirectories if name != "__pycache__")
            for name in sorted(names + subdirectories):
                path = Path(directory) / name
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    raise ValueError(f"package symlink or special file refused: {path.relative_to(root)}")
                if path.is_file():
                    yield path


def package_manifest(package: Path | None = None) -> dict:
    """{relative path: file sha256} and `sha256` of that map as sorted-key JSON; `__pycache__` excluded."""
    root, members = (ROOT, BUILTIN_PACKAGE_MEMBERS) if package is None else (Path(package), (".",))
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in _package_files(root, members)}
    return {"files": dict(sorted(files.items())),
            "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def _importable_elsewhere(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return True


def _load_package_module(package, name):
    """A single `<package>/<name>.py`, executed without sys.path changes; shadowing names refuse."""
    if (not PACKAGE_MODULE.fullmatch(name) or name in sys.stdlib_module_names or name in RUNTIME_MODULES
            or _importable_elsewhere(name)):
        raise ValueError(f"package tool module refused: {name!r}")
    path = package / f"{name}.py"
    if path.is_symlink() or not path.is_file() or path.resolve().parent != package.resolve():
        raise ValueError(f"package tool module missing or outside the package: {name!r}")
    module = types.ModuleType(f"agent_package.{name}")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def resolve_package_tools(package: Path, entries) -> list:
    """`module:function` entries resolved only from modules inside the package; re-exported callables refuse."""
    modules, tools = {}, []
    for entry in entries:
        name, separator, function_name = entry.partition(":")
        if not separator or not function_name.isidentifier():
            raise ValueError(f"unknown tool refused: {entry!r}")
        if name not in modules:
            modules[name] = _load_package_module(package, name)
        function = modules[name].__dict__.get(function_name)
        if not inspect.isfunction(function) or function.__module__ != modules[name].__name__:
            raise ValueError(f"unknown tool refused: {entry!r}")
        tools.append(function)
    return tools


def load_spec(path: Path | None = None, package: Path | None = None) -> AgentSpec:
    """Exactly one default agent. Built-in: tools only from `agent_tools`. Package: tools only from its own modules."""
    path = (ROOT if package is None else Path(package)) / "configuration.yaml" if path is None else path
    config = load_agent_config(path, strict=True)
    if set(config) != {"agents", "prompts_dir"} or config["prompts_dir"] != "prompts":
        raise ValueError("unexpected configuration keys or prompts directory")
    roster = config["agents"]
    default = roster.get("default") if isinstance(roster, dict) else None
    if not isinstance(default, str) or set(roster) != {"default", default}:
        raise ValueError("exactly one default agent required")
    agent = roster[default]
    if not isinstance(agent, dict) or not REQUIRED_FIELDS <= set(agent) <= AGENT_FIELDS:
        raise ValueError("unexpected agent fields")
    for key in ("name", "model"):
        if not isinstance(agent[key], str) or not agent[key].strip():
            raise ValueError(f"agent {key} is required")
    tools = agent.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
        raise ValueError("unknown tool refused")
    if package is not None:
        resolved = resolve_package_tools(Path(package), tools)
    elif any(not item.startswith(TOOL_MODULE + ":") for item in tools):
        raise ValueError("unknown tool refused")
    else:
        try:
            resolved = resolve_tools(tools, allowed_prefixes=(TOOL_MODULE,))
        except (ImportError, AttributeError, TypeError) as error:
            raise ValueError("unknown tool refused") from error
    instructions = load_instructions(agent["instructions"], path.parent / config["prompts_dir"], strict=True)
    return AgentSpec(agent_id=default, name=agent["name"], description=agent.get("description", ""),
                     model=agent["model"], instructions=instructions, tools=tuple(resolved), surface="hidden")


def apply_optimization(spec, config):
    """Instructions are the only field a native candidate may change; model drift, skills, tools, temperature refuse."""
    if config is None:
        raise ValueError("native optimization configuration missing")
    if not isinstance(config.skills, list) or not isinstance(config.tool_definitions, list):
        raise ValueError("native skills and tools must be lists")
    if (config.model not in (None, spec.model) or config.skills or config.tool_definitions
            or config.temperature is not None or getattr(config, "skills_dir", None)
            or getattr(config, "has_skills", False)):
        raise ValueError("only instructions may change")
    if not isinstance(config.instructions, str) or not config.instructions.strip():
        raise ValueError("native instructions missing")
    return replace(spec, instructions=config.instructions)


def load_optimized_spec(credential, config_dir=OPTIMIZATION_DIR, path=None, package=None):
    """(spec, identity additions). Native `load_config` only when a candidate is requested or baked; else baseline."""
    spec = load_spec(path, package)
    candidate = os.environ.get("OPTIMIZATION_CANDIDATE_ID", "").strip()
    inline = os.environ.get("OPTIMIZATION_CONFIG", "").strip()
    if candidate and not CANDIDATE_ID.fullmatch(candidate):
        raise ValueError("unsafe candidate identity")
    if inline:
        value = json.loads(inline)
        if not isinstance(value, dict) or set(value) - INLINE_FIELDS:
            raise ValueError("unapproved native candidate fields")
    if not (candidate or inline or Path(config_dir).is_dir()):
        return spec, {}
    from azure.ai.agentserver.optimization import load_config

    # Explicit config_dir: OPTIMIZATION_LOCAL_DIR cannot redirect loading outside the package.
    config = load_config(config_dir=config_dir, credential=credential)
    if config is None:
        if candidate or inline:
            raise ValueError("requested native candidate failed to load")
        return spec, {}
    source = config.source.split(":", 1)[0]
    if inline and config.source != "env:OPTIMIZATION_CONFIG":
        raise ValueError("native inline override failed to load")
    # load_config falls back to baseline/ yet still labels it with the requested candidate id.
    if candidate and not inline and (config.candidate_id != candidate or not (
            source == "api" or (source == "local" and Path(config.source[len("local:"):]).name == candidate))):
        raise ValueError("requested native candidate failed to load")
    applied = apply_optimization(spec, config)
    digest = hashlib.sha256(json.dumps({"instructions": applied.instructions, "model": applied.model},
                                       sort_keys=True).encode()).hexdigest()
    label = config.candidate_id or candidate or ("inline" if inline else "baseline")
    return applied, {"optimization_source": source, "optimization_candidate_id": label,
                     "optimization_config_sha256": digest}
