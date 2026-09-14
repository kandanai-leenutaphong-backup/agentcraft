from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .contracts import ConfigurationError, EVIDENCE, Limits, OPERATIONS, freeze

GRANTS = frozenset(OPERATIONS) - {"schema", "provision"} | frozenset(
    f"{plane}.{action}" for plane, actions in (
        ("schema", ("list", "read", "create", "update", "delete")),
        ("provision", ("plan", "read", "create", "update", "delete")),
    ) for action in actions
)


@dataclass(frozen=True)
class Policy:
    principal: str
    grants: frozenset[str] = frozenset({"read", "query"})
    limits: Limits = field(default_factory=Limits)
    minimum_verification: Mapping[str, str] = field(default_factory=dict)
    max_concurrency: int = 4
    destructive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.principal, str) or not self.principal.strip() or len(self.principal) > 256:
            raise ConfigurationError("a bounded principal identifier is required")
        if (not isinstance(self.grants, (set, frozenset, tuple, list))
            or not all(isinstance(grant, str) for grant in self.grants) or not set(self.grants) <= GRANTS):
            raise ConfigurationError("unknown policy grant")
        if not isinstance(self.limits, Limits) or not self.limits.valid():
            raise ConfigurationError("invalid policy limits")
        if type(self.max_concurrency) is not int or not 1 <= self.max_concurrency <= 64:
            raise ConfigurationError("max_concurrency must be between 1 and 64")
        if type(self.destructive) is not bool:
            raise ConfigurationError("destructive must be a boolean")
        if (not isinstance(self.minimum_verification, Mapping)
            or not all(isinstance(operation, str) and isinstance(evidence, str) and operation in GRANTS and evidence in EVIDENCE
                           for operation, evidence in self.minimum_verification.items())):
            raise ConfigurationError("invalid minimum verification policy")
        object.__setattr__(self, "grants", frozenset(self.grants))
        object.__setattr__(self, "minimum_verification", freeze(self.minimum_verification))