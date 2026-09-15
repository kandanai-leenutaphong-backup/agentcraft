"""Azure Resource Manager control-plane access over one Entra ID identity.

Consolidated from three hand-rolled copies: `app/cybereye/backend/graph_service.py`
resolving a Cosmos read-only key, and the byte-identical `arm.py` in each of the two
pipelines. No API key, account key, or connection string is read from configuration.
"""

from __future__ import annotations

from .client import ArmClient, ArmError, RETRYABLE_STATUS, resource_path
from .config import (
    DEFAULT_ARM_ENDPOINT,
    DEFAULT_ARM_SCOPE,
    DEFAULT_ENV_PREFIX,
    ArmConfig,
    ArmConfigError,
)

__all__ = [
    "ArmClient",
    "ArmConfig",
    "ArmConfigError",
    "ArmError",
    "DEFAULT_ARM_ENDPOINT",
    "DEFAULT_ARM_SCOPE",
    "DEFAULT_ENV_PREFIX",
    "RETRYABLE_STATUS",
    "resource_path",
]
