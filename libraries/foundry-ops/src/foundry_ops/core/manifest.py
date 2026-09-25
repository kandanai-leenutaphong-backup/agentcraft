"""Digest-pinned run manifests: bind one reviewed JSON document to one allowed action and one series."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any

from .errors import RefusedError
from .records import RECORD_NAME, EvidenceLedger, sha256_hex

PinSource = bytes | str | os.PathLike[str]


@dataclass(frozen=True)
class RunManifest:
    path: Path
    sha256: str
    raw: bytes
    value: Mapping[str, Any]
    action: str

    @property
    def series(self) -> str:
        return self.value["series"]

    @property
    def agent(self) -> str | None:
        return self.value.get("agent")

    def bind(self, ledger: EvidenceLedger, name: str = "run-manifest.json") -> dict[str, Any]:
        """Retain exact manifest bytes once; a different manifest under the same series is refused."""
        return ledger.retain_bytes(name, self.raw, allow_identical=True)


def _field(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _pin_bytes(source: PinSource) -> bytes:
    return source if isinstance(source, bytes) else Path(source).read_bytes()


def load_run_manifest(path: str | os.PathLike[str], *, expected_sha256: str, action: str,
                      allowed_root: str | os.PathLike[str], pins: Mapping[str, PinSource] | None = None,
                      purpose: str = "migration-development", schema_version: int = 1,
                      series_pattern: str = r"migration-[a-z0-9-]+",
                      agent_pattern: str | None = r"agentcraft-migration-[a-z0-9-]+",
                      forbidden_agents: frozenset[str] = frozenset(),
                      allowed_fields: Collection[str] | None = None) -> RunManifest:
    """Refuse before any side effect unless path, bytes, schema, purpose, action, series, agent and pins match.

    `pins` maps a (dotted) manifest field to the bytes or file whose SHA-256 it must equal.
    `allowed_fields`, when given, refuses any other top-level field (names listed, values never).
    """
    source = Path(path)
    if source.is_symlink() or not source.resolve().is_relative_to(Path(allowed_root).resolve()):
        raise RefusedError("manifest_path", "run manifest outside its allowed root")
    raw = source.read_bytes()
    if sha256_hex(raw) != expected_sha256:
        raise RefusedError("manifest_digest", "run manifest digest mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != schema_version:
        raise RefusedError("manifest_schema", "unsupported run manifest schema")
    if allowed_fields is not None:
        unknown = sorted(str(key) for key in value if key not in allowed_fields)
        if unknown:
            raise RefusedError("manifest_field", "unknown manifest fields: " + ", ".join(unknown))
    if value.get("purpose") != purpose:
        raise RefusedError("manifest_purpose", "foreign or historical manifest purpose")
    actions = value.get("actions")
    if not isinstance(actions, list) or action not in actions:
        raise RefusedError("manifest_action", f"action not allowed by manifest: {action}")
    series = value.get("series")
    if not isinstance(series, str) or not re.fullmatch(series_pattern, series) or not RECORD_NAME.fullmatch(series):
        raise RefusedError("manifest_series", "invalid run series")
    if agent_pattern is not None:
        agent = value.get("agent")
        if not isinstance(agent, str) or not re.fullmatch(agent_pattern, agent) or agent in forbidden_agents:
            raise RefusedError("manifest_agent", "foreign or accepted agent refused")
    drifted = sorted(key for key, pinned in (pins or {}).items() if _field(value, key) != sha256_hex(_pin_bytes(pinned)))
    if drifted:
        raise RefusedError("manifest_pin", "pin drift: " + ", ".join(drifted))
    return RunManifest(path=source.resolve(), sha256=expected_sha256, raw=raw, value=value, action=action)


def series_directory(base: str | os.PathLike[str], series: str) -> Path:
    """Create or reuse `<base>/<series>`; refuse symlinks and escapes."""
    root = Path(base).resolve()
    if not RECORD_NAME.fullmatch(series):
        raise RefusedError("manifest_series", "invalid run series")
    directory = root / series
    if directory.is_symlink() or not directory.resolve().is_relative_to(root):
        raise RefusedError("foreign_path", "series directory escapes its evidence root")
    directory.mkdir(exist_ok=True)
    return directory
