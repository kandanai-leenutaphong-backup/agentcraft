"""Config-driven query-test battery. The host owns data access, rules and meaning."""

from .battery import (
    BATTERY_COMPLETED,
    RULE_COMPLETED,
    RULE_STARTED,
    run_battery,
    run_battery_async,
    stream_battery,
)
from .config import (
    MAX_CONFIGURATION_BYTES,
    MAX_EXTRA_KEYS,
    MAX_RULES_PER_SET,
    MAX_RULE_SETS,
    configuration_digest,
    normalize_config,
    normalize_window,
    selected_rules,
)
from .errors import ConfigurationError, RuleExecutionError

__all__ = [
    "BATTERY_COMPLETED",
    "ConfigurationError",
    "MAX_CONFIGURATION_BYTES",
    "MAX_EXTRA_KEYS",
    "MAX_RULES_PER_SET",
    "MAX_RULE_SETS",
    "RULE_COMPLETED",
    "RULE_STARTED",
    "RuleExecutionError",
    "configuration_digest",
    "normalize_config",
    "normalize_window",
    "run_battery",
    "run_battery_async",
    "selected_rules",
    "stream_battery",
]
