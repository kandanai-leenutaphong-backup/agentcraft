"""Agent config loader — YAML roster with include-merge and injectable paths.

Module role:
    Reads and caches ``agent_config.yaml``. Paths are injectable: the consumer
    either passes ``config_path`` per call, or configures a process-wide default
    control directory once via :func:`set_default_control_dir` (the consumer's
    composition root does this at import). With no default
    configured and no path passed, the zero-arg helpers fail loud rather than
    guessing a project root — this package ships no filesystem assumptions.

Layering:
    stdlib + PyYAML only. Imports nothing outside this package.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Reserved keys in the agents: block that are NOT agent definitions ────────
_RESERVED_KEYS = frozenset({"default", "mode"})

# ── Injectable process-wide defaults (configured by the consumer) ────────────
# The control directory holding ``agent_config.yaml`` and ``prompts/``. The
# package ships no hardcoded project root; the consumer sets it from its
# composition root (see ``examples/build_agent.py``).
_default_control_dir: Path | None = None
# Fallback agent id when a config omits the ``default`` key. Empty = no
# fallback (domain-blind); a consumer sets its own landing agent.
_default_agent_fallback: str = ""

# ── Module-level caches ──────────────────────────────────────────────────────
# Base config path -> (mtime signature over base + every include fragment, the
# merged config, the resolved include paths). The signature spans the fragments
# so an edit to any include invalidates the cache even when the base file is
# unchanged (dev hot-reload correctness); the deployed image reads once at boot.
_cached_configs: dict[Path, tuple[tuple[int, ...], dict[str, Any], list[Path]]] = {}
_cached_agents_blocks: dict[Path, dict[str, Any]] = {}


def set_default_control_dir(path: Path | str) -> None:
    """Register the process-wide default control directory.

    Idempotent. Called once by the consumer's composition root so the zero-arg
    loaders resolve ``<control>/agent_config.yaml`` and ``<control>/prompts``.
    """
    global _default_control_dir
    _default_control_dir = Path(path).resolve()


def set_default_agent_fallback(agent_id: str) -> None:
    """Register the fallback agent id used when a config omits ``default``."""
    global _default_agent_fallback
    _default_agent_fallback = agent_id or ""


def _control_dir() -> Path:
    """Return the configured default control dir or fail loud."""
    if _default_control_dir is None:
        raise RuntimeError(
            "agentconfig: no default control directory configured. "
            "Call set_default_control_dir(<path>) at composition time, or pass "
            "config_path explicitly."
        )
    return _default_control_dir


def _default_config_path() -> Path:
    """Resolve the default ``agent_config.yaml`` path from the control dir."""
    return _control_dir() / "agent_config.yaml"


def _read_config_yaml(path: Path) -> dict[str, Any]:
    """Parse one YAML config file into a mapping (fail loud on bad YAML/shape)."""
    try:
        with open(path) as f:
            parsed = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", path.name, e)
        raise
    if not isinstance(parsed, dict):
        raise ValueError(f"{path.name} root must be a mapping")
    return parsed


def _resolve_includes(base: dict[str, Any], base_path: Path) -> list[Path]:
    """Resolve the base config's ``include:`` list to absolute fragment paths.

    Paths are relative to the base file's directory (the control dir).
    """
    includes = base.get("include") or []
    if not isinstance(includes, list):
        raise ValueError("agent_config.yaml 'include' must be a list of paths")
    return [(base_path.parent / str(rel)).resolve() for rel in includes]


def _mtime_signature(paths: list[Path]) -> tuple[int, ...]:
    """Change-detector: each file's mtime in order; a missing file signs as -1."""
    sig: list[int] = []
    for p in paths:
        try:
            sig.append(p.stat().st_mtime_ns)
        except OSError:
            sig.append(-1)
    return tuple(sig)


def _merge_config(base: dict[str, Any], fragment_paths: list[Path]) -> dict[str, Any]:
    """Merge include fragments' ``agents`` + ``tool_display_names`` into the base.

    Fragments contribute agent definitions and tool display names only. Scalar
    top-level keys stay owned by the base file: the ``default`` agent lives
    inside the base ``agents:`` block, and ``prompts_dir`` / ``foundation_prompts``
    are single-valued. A duplicate agent id across sources fails loud so a
    copy-paste slip surfaces at boot, not as a silently shadowed agent.
    """
    merged = dict(base)
    merged.pop("include", None)
    agents: dict[str, Any] = dict(merged.get("agents") or {})
    display: dict[str, Any] = dict(merged.get("tool_display_names") or {})
    for frag_path in fragment_paths:
        if not frag_path.exists():
            raise RuntimeError(f"agent_config include fragment not found: {frag_path}")
        frag = _read_config_yaml(frag_path)
        for aid, adef in (frag.get("agents") or {}).items():
            if aid in _RESERVED_KEYS:
                continue  # default/mode are owned by the base agents: block
            if aid in agents:
                raise ValueError(
                    f"duplicate agent id '{aid}' defined in include {frag_path.name}"
                )
            agents[aid] = adef
        for tname, disp in (frag.get("tool_display_names") or {}).items():
            display[tname] = disp
    merged["agents"] = agents
    if display:
        merged["tool_display_names"] = display
    return merged


def load_agent_config(config_path: Path | None = None) -> dict[str, Any]:
    """Parse an agent config YAML file, merging any ``include:`` fragments.

    The base file may carry an ``include:`` list of fragment paths (relative to
    the base file's directory). Each fragment's ``agents:`` and
    ``tool_display_names:`` blocks are merged into the base, so a large agent
    roster can be split across per-domain files (e.g. ``agents/sales.yaml`` +
    ``agents/support.yaml``) while the runtime still loads one config. Scalar keys
    (the ``default`` agent inside ``agents:``, ``prompts_dir``,
    ``foundation_prompts``) stay owned by the base file; duplicate agent ids
    across fragments fail loud. A base with no ``include:`` behaves exactly as
    a single-file config.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir's ``agent_config.yaml``.

    Returns:
        Parsed + merged YAML dict, or empty dict if the base file is not found.
    """
    path = (config_path or _default_config_path()).resolve()
    if not path.exists():
        logger.warning("agent_config.yaml not found at %s", path)
        return {}
    # Cache hit only when the base AND every previously-resolved fragment are
    # unchanged. A base edit bumps the base mtime; a fragment edit bumps that
    # fragment's mtime — either invalidates the signature.
    cached = _cached_configs.get(path)
    if cached:
        cached_sig, cached_cfg, cached_fragments = cached
        if _mtime_signature([path, *cached_fragments]) == cached_sig:
            return cached_cfg
    base = _read_config_yaml(path)
    fragment_paths = _resolve_includes(base, path)
    merged = _merge_config(base, fragment_paths)
    signature = _mtime_signature([path, *fragment_paths])
    _cached_configs[path] = (signature, merged, fragment_paths)
    _cached_agents_blocks.pop(path, None)
    return merged


def get_prompts_dir(config_path: Path | None = None) -> Path:
    """Return the prompts directory path from config.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir.

    Returns:
        Resolved absolute path to the prompts directory.
    """
    # The prompts dir is resolved relative to the control directory that holds
    # the config file: ``<control>/<prompts_dir>``.
    control = config_path.resolve().parent if config_path else _control_dir()
    cfg = load_agent_config(config_path)
    rel = cfg.get("prompts_dir", "prompts")
    return control / rel


def invalidate_config_cache() -> None:
    """Clear both the YAML LRU cache and the agents block cache."""
    from ._prompts import invalidate_foundation_prompt_cache

    _cached_configs.clear()
    _cached_agents_blocks.clear()
    invalidate_foundation_prompt_cache()


def get_control_dir() -> Path:
    """Return the configured control/ directory.

    The consumer-configured default control dir. Callers that need the
    directory (persistence roots, request-scope construction) call this.
    """
    return _control_dir()


# ── Typed agent lookup ───────────────────────────────────────────────────────

class AgentNotFound(ValueError):
    """Raised when ``resolve_agent_cfg`` cannot locate an agent ID.

    Subclass of ``ValueError`` so existing ``except ValueError`` handlers keep
    working unchanged.

    Attributes:
        agent_id: The ID that failed to resolve (may be empty if no default).
        available: List of agent IDs present in the config (excludes reserved keys).
    """

    def __init__(self, agent_id: str, available: list[str]):
        self.agent_id = agent_id
        self.available = available
        if not agent_id:
            msg = (
                "No agent_id specified and no 'default' key in agent_config.yaml "
                "agents block."
            )
        else:
            msg = (
                f"Agent '{agent_id}' not found in agent_config.yaml. "
                f"Available agents: {available}"
            )
        super().__init__(msg)


def resolve_agent_cfg(agent_id: str | None) -> tuple[str, dict[str, Any]]:
    """Resolve an agent ID (or default) to ``(target_id, agent_cfg)``.

    Single source of truth for the "load agents block → pick default if none
    specified → look up by id → raise typed error if missing" sequence.

    Raises:
        AgentNotFound: when the resolved id is missing from the config.
    """
    config = load_agents_block()
    target_id = agent_id or get_default_id(config)
    if not target_id:
        raise AgentNotFound("", [aid for aid, _ in iter_agents(config)])

    agent_cfg = find_agent(config, target_id)
    if not isinstance(agent_cfg, dict):
        raise AgentNotFound(target_id, [aid for aid, _ in iter_agents(config)])

    return target_id, agent_cfg


# ── Agents block functions ───────────────────────────────────────────────────

def load_agents_block(config_path: Path | None = None) -> dict[str, Any]:
    """Load and cache the agents block from agent_config.yaml.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir.

    Returns:
        The parsed ``agents:`` dict.

    Raises:
        ValueError: If the config is missing or has no ``agents:`` block.
    """
    resolved_path = (config_path or _default_config_path()).resolve()
    if resolved_path in _cached_agents_blocks:
        return _cached_agents_blocks[resolved_path]

    config = load_agent_config(resolved_path)
    if not config:
        raise ValueError(
            "agent_config.yaml not found or empty. "
            "Create control/agent_config.yaml with an agents: block."
        )

    agents_block = config.get("agents")
    if not agents_block:
        raise ValueError(
            "agent_config.yaml has no 'agents:' block. "
            "Add agents with a 'default' key and agent definitions."
        )

    _cached_agents_blocks[resolved_path] = agents_block
    logger.info(
        "Loaded agents config: %d agent(s)",
        len([k for k in agents_block if k not in _RESERVED_KEYS]),
    )
    return agents_block


def get_default_id(config: dict[str, Any]) -> str:
    """Return the default agent ID from the config block.

    Falls back to the configured ``_default_agent_fallback`` (empty by default)
    when the config omits the ``default`` key.
    """
    return config.get("default", _default_agent_fallback)


def default_agent_id() -> str:
    """Resolve the default agent identifier from ``agent_config.yaml``.

    Returns:
        Configured default agent id, or the registered fallback when the config
        is missing, malformed, or has no usable default.
    """
    try:
        config = load_agent_config()
    except Exception:
        return _default_agent_fallback
    agents_block = (config or {}).get("agents") or {}
    candidate = agents_block.get("default")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return _default_agent_fallback


def iter_agents(config: dict[str, Any]):
    """Iterate over (agent_id, agent_config) pairs, skipping reserved keys."""
    for key, value in config.items():
        if key not in _RESERVED_KEYS and isinstance(value, dict):
            yield key, value


def find_agent(config: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Look up a specific agent's config by ID."""
    if agent_id in _RESERVED_KEYS:
        return None
    return config.get(agent_id)


def get_tool_display_names(config_path: Path | None = None) -> dict[str, str]:
    """Return the tool_display_names mapping from agent_config.yaml.

    Maps tool function names (e.g. 'find_orders') to human-readable labels
    (e.g. 'Find Orders') for display in a chat UI.

    Returns:
        Dict mapping function name → readable display name. Empty dict if the
        section is not present.
    """
    cfg = load_agent_config(config_path)
    names = cfg.get("tool_display_names", {})
    if not isinstance(names, dict):
        return {}
    return {str(k): str(v) for k, v in names.items()}
