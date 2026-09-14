"""Settings — read once at startup, frozen, and never able to stop the process.

WHY THIS EXISTS
---------------
An environment read deep inside a handler is unreviewable, and a typo becomes
a runtime 401 rather than a startup fact. One object, built at the
composition root, listing everything the process needs.

Two rules are inherited from ``azdata``'s config deliberately:

* **Parse with fallback.** An unparseable number falls back to its default
  rather than raising. One bad variable must not stop an explorer whose whole
  job is to be reachable when the estate is not.
* **Empty means unconfigured.** Without a subscription there is nothing to
  browse, so the root renders ``unconfigured`` naming the variable, is never
  probed and never guessed.

ONE COORDINATE, NOT SIX
-----------------------
The tree is subscription-wide: a resource group, a storage account, a Cosmos
account, a Search endpoint and a Kusto cluster are all *discovered*, not
configured. ``AZDATA_SUBSCRIPTION_ID`` is the only coordinate that must be
set. ``AZDATA_RESOURCE_GROUP`` is optional and narrows the root to one group,
which is how a deployment scopes an operator to part of an estate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from azdata import AzureDataConfig

#: Final server clamp on one expansion, and the ``max_items`` handed down.
MAX_CHILDREN = 500

#: Per-node detail bounds. A browser renders these; anything larger is a
#: payload rather than a label, and one large value multiplies by 500.
MAX_DETAIL_KEYS = 40
MAX_DETAIL_VALUE_CHARS = 500

#: One expansion's discovery budget, and the whole request's budget. The
#: request budget is larger so a timed-out discovery still renders as data.
DISCOVERY_TIMEOUT_SECS = 15.0
REQUEST_TIMEOUT_SECS = 20.0

#: One content read. Larger than a discovery budget because a megabyte over a
#: cold TLS handshake legitimately takes longer than a listing.
CONTENT_TIMEOUT_SECS = 25.0

#: A content read's ceiling, applied before the read starts. One mebibyte is
#: the largest object a browser pane can usefully hold at once; a hundred rows
#: is the largest sample a human scans without paging.
MAX_CONTENT_BYTES = 1_048_576
MAX_CONTENT_ROWS = 100

#: Rendered text is capped separately from the bytes: pretty-printing JSON can
#: double it, and a megabyte of text in one DOM node is a hang.
MAX_TEXT_CHARS = 200_000

#: How many bytes of an unreadable object become a hex preview.
MAX_HEX_PREVIEW_BYTES = 512

#: Estate search bounds. The term is a human's, so it is short by nature and
#: long is a sign of something other than a search.
MAX_SEARCH_TERM_CHARS = 200
MAX_SEARCH_HITS = 200

#: Listing caches, single-flighted per key. Opening a resource group and then
#: each of its type groups must cost one listing, not thirteen.
INVENTORY_TTL_SECS = 30.0

#: Where the built SPA lives, relative to the component root.
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

#: Set by the Container Apps runtime. Its presence means "this is Azure", and
#: it is what disables the local development principal bypass.
AZURE_MARKER_VAR = "CONTAINER_APP_NAME"

#: The one coordinate the tree cannot be built without.
REQUIRED_VARIABLE = "AZDATA_SUBSCRIPTION_ID"


def _flag(env: dict[str, str], name: str) -> bool:
    return env.get(name, "").strip() in {"1", "true", "True", "yes", "on"}


def _number(env: dict[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Settings:
    """Everything the process needs, resolved once."""

    azure: AzureDataConfig = field(default_factory=AzureDataConfig)

    fake_discovery: bool = False
    dev_principal: bool = False
    running_in_azure: bool = False
    static_dir: Path = DEFAULT_STATIC_DIR

    max_children: int = MAX_CHILDREN
    discovery_timeout_secs: float = DISCOVERY_TIMEOUT_SECS
    request_timeout_secs: float = REQUEST_TIMEOUT_SECS
    content_timeout_secs: float = CONTENT_TIMEOUT_SECS
    inventory_ttl_secs: float = INVENTORY_TTL_SECS
    max_content_bytes: int = MAX_CONTENT_BYTES
    max_content_rows: int = MAX_CONTENT_ROWS

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        src = dict(os.environ if env is None else env)
        running_in_azure = bool(src.get(AZURE_MARKER_VAR, "").strip())
        static = src.get("RESOURCE_EXPLORER_STATIC_DIR", "").strip()
        return cls(
            azure=AzureDataConfig.from_env(src),
            fake_discovery=_flag(src, "RESOURCE_EXPLORER_FAKE_DISCOVERY"),
            # The bypass cannot exist in Azure regardless of how the app is
            # configured: the marker variable wins over the flag, in code.
            dev_principal=(
                _flag(src, "RESOURCE_EXPLORER_DEV_PRINCIPAL") and not running_in_azure
            ),
            running_in_azure=running_in_azure,
            static_dir=Path(static) if static else DEFAULT_STATIC_DIR,
            max_children=max(
                1,
                min(
                    MAX_CHILDREN,
                    int(_number(src, "RESOURCE_EXPLORER_MAX_CHILDREN", MAX_CHILDREN)),
                ),
            ),
            discovery_timeout_secs=_number(
                src, "RESOURCE_EXPLORER_DISCOVERY_TIMEOUT_SECS", DISCOVERY_TIMEOUT_SECS
            ),
            request_timeout_secs=_number(
                src, "RESOURCE_EXPLORER_REQUEST_TIMEOUT_SECS", REQUEST_TIMEOUT_SECS
            ),
            content_timeout_secs=_number(
                src, "RESOURCE_EXPLORER_CONTENT_TIMEOUT_SECS", CONTENT_TIMEOUT_SECS
            ),
            inventory_ttl_secs=_number(
                src, "RESOURCE_EXPLORER_INVENTORY_TTL_SECS", INVENTORY_TTL_SECS
            ),
            max_content_bytes=max(
                1,
                min(
                    MAX_CONTENT_BYTES,
                    int(
                        _number(
                            src, "RESOURCE_EXPLORER_MAX_CONTENT_BYTES", MAX_CONTENT_BYTES
                        )
                    ),
                ),
            ),
            max_content_rows=max(
                1,
                min(
                    MAX_CONTENT_ROWS,
                    int(
                        _number(
                            src, "RESOURCE_EXPLORER_MAX_CONTENT_ROWS", MAX_CONTENT_ROWS
                        )
                    ),
                ),
            ),
        )

    @property
    def index_path(self) -> Path:
        return self.static_dir / "index.html"

    @property
    def assets_dir(self) -> Path:
        return self.static_dir / "assets"

    @property
    def static_ready(self) -> bool:
        return self.index_path.is_file()

    @property
    def subscription_id(self) -> str:
        return self.azure.subscription_id

    @property
    def resource_group(self) -> str:
        """Set to narrow the root to one group; empty means the whole estate."""
        return self.azure.resource_group

    @property
    def configured(self) -> bool:
        """Fixture mode is configured by construction: it carries its own estate."""
        return self.fake_discovery or bool(self.subscription_id)


__all__ = [
    "AZURE_MARKER_VAR",
    "CONTENT_TIMEOUT_SECS",
    "DEFAULT_STATIC_DIR",
    "DISCOVERY_TIMEOUT_SECS",
    "INVENTORY_TTL_SECS",
    "MAX_CHILDREN",
    "MAX_CONTENT_BYTES",
    "MAX_CONTENT_ROWS",
    "MAX_DETAIL_KEYS",
    "MAX_DETAIL_VALUE_CHARS",
    "MAX_HEX_PREVIEW_BYTES",
    "MAX_SEARCH_HITS",
    "MAX_SEARCH_TERM_CHARS",
    "MAX_TEXT_CHARS",
    "REQUEST_TIMEOUT_SECS",
    "REQUIRED_VARIABLE",
    "Settings",
]
