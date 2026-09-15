"""Deterministic CyberEye detector package."""

from .composition import declaration, default_configuration, rule_from_declaration
from .engine import DetectorEngine
from .rules import Rule, registry

__all__ = [
    "DetectorEngine", "Rule", "declaration", "default_configuration",
    "registry", "rule_from_declaration",
]
