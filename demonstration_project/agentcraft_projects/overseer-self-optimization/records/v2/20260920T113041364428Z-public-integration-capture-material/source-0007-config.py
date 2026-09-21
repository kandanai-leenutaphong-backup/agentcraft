"""CyberEye runtime configuration."""

from __future__ import annotations

import os
import re
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(APP_ROOT / ".env", override=False)

#: KQL cannot parameterise an identifier, so a table name must be proven safe by shape.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


@dataclass(frozen=True, slots=True)
class Settings:
    app_root: Path = APP_ROOT
    telemetry_profile: str = os.getenv("CYBEREYE_TELEMETRY_PROFILE", "adx")
    cosmos_endpoint: str = os.getenv("CYBEREYE_COSMOS_ENDPOINT", "")
    cosmos_database: str = os.getenv("CYBEREYE_COSMOS_DATABASE", "")
    cosmos_container: str = os.getenv("CYBEREYE_COSMOS_CONTAINER", "")
    public_manifest_path: str = os.getenv("CYBEREYE_PUBLIC_MANIFEST", "")
    public_manifest_sha256: str = os.getenv("CYBEREYE_PUBLIC_MANIFEST_SHA256", "")
    adx_cluster_uri: str = os.getenv("ADX_CLUSTER_URI", "")
    adx_database: str = os.getenv("ADX_DATABASE", "PerthCyber")
    #: The telemetry table every rule, tool, and query is bound to.
    table: str = os.getenv("CYBEREYE_TABLE", "EventsUnified")
    #: Additional tables a query may be rooted at. Adding a source means adding it here.
    extra_tables: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("CYBEREYE_EXTRA_TABLES", "").split(",") if item.strip()
    )
    openai_endpoint: str = os.getenv("CYBEREYE_OPENAI_ENDPOINT", "")
    model: str = os.getenv("CYBEREYE_MODEL", "gpt-5.6-luna")
    allow_model_calls: bool = os.getenv("CYBEREYE_ALLOW_MODEL_CALLS", "false").lower() == "true"
    agent_store_dir: str = os.getenv("CYBEREYE_AGENT_STORE_DIR", str(APP_ROOT / ".local" / "agents"))
    agent_models: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("CYBEREYE_AGENT_MODELS", "").split(",") if item.strip()
    )
    detector_config_path: str = os.getenv("CYBEREYE_DETECTOR_CONFIG_PATH", str(APP_ROOT / "control/situation_detector.json"))
    graph_account: str = os.getenv("GREMLIN_ACCOUNT", "")
    graph_database: str = os.getenv("GREMLIN_DATABASE", "airportgraph")
    graph_name: str = os.getenv("GREMLIN_GRAPH", "ontology")
    graph_resource_group: str = os.getenv("GREMLIN_RESOURCE_GROUP", "")
    #: Needed to resolve the Gremlin read-only key from ARM at runtime.
    graph_subscription_id: str = os.getenv("GREMLIN_SUBSCRIPTION_ID", "")
    #: The knowledge index. Retrieval is Azure AI Search only; there is no local corpus.
    search_endpoint: str = os.getenv("CYBEREYE_SEARCH_ENDPOINT", "")
    knowledge_index: str = os.getenv("CYBEREYE_MITRE_SEARCH_INDEX", "")
    max_rows: int = int(os.getenv("CYBEREYE_MAX_ROWS", "200"))
    query_timeout_seconds: int = int(os.getenv("CYBEREYE_QUERY_TIMEOUT_SECONDS", "30"))
    cors_origins: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv(
            "CYBEREYE_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",") if item.strip()
    )

    @property
    def tables(self) -> tuple[str, ...]:
        """Every table a read-only query may be rooted at."""
        return (self.table, *self.extra_tables)

    def validate(self) -> None:
        if self.telemetry_profile not in {"adx", "public-cosmos"}:
            raise RuntimeError("unknown CYBEREYE_TELEMETRY_PROFILE")
        missing = [
            name for name, value in (
                *(((("ADX_CLUSTER_URI", self.adx_cluster_uri),)) if self.telemetry_profile == "adx" else (
                    ("CYBEREYE_COSMOS_ENDPOINT", self.cosmos_endpoint),
                    ("CYBEREYE_COSMOS_DATABASE", self.cosmos_database),
                    ("CYBEREYE_COSMOS_CONTAINER", self.cosmos_container),
                    ("CYBEREYE_PUBLIC_MANIFEST", self.public_manifest_path),
                    ("CYBEREYE_PUBLIC_MANIFEST_SHA256", self.public_manifest_sha256),
                )),
                ("CYBEREYE_OPENAI_ENDPOINT", self.openai_endpoint),
            ) if not value
        ]
        if missing:
            raise RuntimeError("missing required settings: " + ", ".join(missing))
        if not self.agent_store_dir.strip():
            raise RuntimeError("CYBEREYE_AGENT_STORE_DIR must name a local configuration directory")
        if self.max_rows < 1 or self.max_rows > 1000:
            raise RuntimeError("CYBEREYE_MAX_ROWS must be between 1 and 1000")
        bad = [name for name in self.tables if not IDENTIFIER.fullmatch(name)]
        if bad:
            raise RuntimeError("table names must be bare identifiers: " + ", ".join(bad))
        if self.telemetry_profile == "public-cosmos":
            self.public_manifest()

    def public_manifest(self) -> dict:
        if self.telemetry_profile != "public-cosmos":
            raise ValueError("public source profile not selected")
        payload = Path(self.public_manifest_path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.public_manifest_sha256:
            raise ValueError("public package manifest digest mismatch")
        manifest = json.loads(payload)
        if manifest.get("schema_version") != 1 or manifest.get("series_id") != "public-investigation-20260920":
            raise ValueError("unsupported public package manifest")
        return manifest


settings = Settings()
