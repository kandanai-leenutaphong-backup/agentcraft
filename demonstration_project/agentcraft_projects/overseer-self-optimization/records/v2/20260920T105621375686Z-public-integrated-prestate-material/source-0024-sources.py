"""The catalogue of data sources CyberEye is connected to.

Extending CyberEye with a new source is housekeeping, not surgery: declare it here with
what it holds and what it can answer, give it a probe that proves it is reachable, and it
becomes discoverable at `/api/cyber/sources` and assertable in the test suite.

A declaration is a statement of availability, not a promise that any rule or tool uses it.
Nothing is forced through a common abstraction; the point is to know what is connected, what
it can answer, and where to reach it.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import settings

#: What a source is for. Kinds are descriptive, not a dispatch mechanism.
Kind = str


@dataclass(frozen=True, slots=True)
class DataSource:
    source_id: str
    name: str
    kind: Kind
    #: What the source contains, in one line an analyst would recognise.
    holds: str
    #: Questions this source can answer. Read this before writing a new rule or tool.
    answers: tuple[str, ...]
    #: How code reaches it, as an import path or attribute.
    reached_by: str
    #: Environment keys that configure it.
    settings: tuple[str, ...]
    #: A source the app cannot start without.
    required: bool
    #: Proves reachability. Must never raise; report the failure instead.
    probe: Callable[..., dict[str, Any]] = field(repr=False, default=lambda: {})

    def declaration(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id, "name": self.name, "kind": self.kind,
            "holds": self.holds, "answers": list(self.answers),
            "reached_by": self.reached_by, "settings": list(self.settings),
            "required": self.required,
        }


def _unsupplied(name: str) -> dict[str, Any]:
    return {"available": False, "detail": f"no live {name} client supplied to the probe"}


def catalogue() -> tuple[DataSource, ...]:
    """Every source this deployment is connected to."""
    from ..knowledge.search import status as knowledge_status

    return (
        DataSource(
            source_id="telemetry",
            name=f"Azure Data Explorer · {settings.adx_database}.{settings.table}",
            kind="telemetry",
            holds="The static event export, one row per observed event.",
            answers=(
                "What happened to a host, an account, or an address in a window",
                "Which rows support a situation, cited by resource_id",
                "Categorical activity profiles for authentication, DNS, network, and sessions",
            ),
            reached_by="request.app.state.adx · ToolContext.adx",
            settings=("ADX_CLUSTER_URI", "ADX_DATABASE", "CYBEREYE_TABLE", "CYBEREYE_EXTRA_TABLES"),
            required=True,
            probe=lambda adx=None: adx.health() if adx else _unsupplied("telemetry"),
        ),
        DataSource(
            source_id="ontology",
            name=f"Cosmos DB for Gremlin · {settings.graph_database}/{settings.graph_name}",
            kind="graph",
            holds="Entities observed in the export and the relationships between them.",
            answers=(
                "How two entities relate, and where their reaches meet",
                "What an entity is connected to, at a chosen hop count",
                "Which relationships were active inside a time window",
            ),
            reached_by="request.app.state.graph",
            settings=("GREMLIN_ACCOUNT", "GREMLIN_DATABASE", "GREMLIN_GRAPH", "GREMLIN_RESOURCE_GROUP",
                      "GREMLIN_SUBSCRIPTION_ID"),
            required=False,
            probe=lambda graph=None: graph.status() if graph else _unsupplied("graph"),
        ),
        DataSource(
            source_id="knowledge_base",
            name="MITRE ATT&CK knowledge index",
            kind="knowledge",
            holds="Pinned MITRE ATT&CK analytics and detection strategies, in Azure AI Search.",
            answers=(
                "What ATT&CK says about an observed behaviour",
                "Which technique identifiers relate to a behaviour class",
            ),
            reached_by="backend.agents.tools.knowledge_base.search_mitre_attack",
            settings=("CYBEREYE_SEARCH_ENDPOINT", "CYBEREYE_MITRE_SEARCH_INDEX"),
            required=False,
            probe=knowledge_status,
        ),
        DataSource(
            source_id="situation_types",
            name="MITRE ATT&CK situation types",
            kind="knowledge",
            holds="ATT&CK techniques and tactics used to classify a scanned situation.",
            answers=(
                "Which recognised technique a situation most resembles",
                "What ATT&CK says that technique looks like, with citations",
            ),
            reached_by="backend.knowledge.situation_types.search_situation_types",
            settings=("CYBEREYE_SEARCH_ENDPOINT", "CYBEREYE_MITRE_SEARCH_INDEX"),
            required=False,
            probe=knowledge_status,
        ),
    )


#: A probe answers within this many seconds or is reported unreachable. A catalogue that
#: blocks is worse than one that says "no answer": a starting ADX cluster stalled it for 2m.
PROBE_TIMEOUT_SECONDS = 5.0


async def verify(adx: Any = None, graph: Any = None,
           timeout: float = PROBE_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Declaration plus a bounded, concurrent reachability check for every source."""
    sources = catalogue()

    async def run(source: DataSource) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout):
                if source.source_id == "telemetry":
                    value = source.probe(adx=adx)
                elif source.source_id == "ontology":
                    value = source.probe(graph=graph)
                else:
                    value = source.probe()
                return await value if inspect.isawaitable(value) else value
        except TimeoutError:
            return {"available": False, "detail": f"no answer within {timeout:g}s"}
        except Exception:
            return {"available": False, "detail": "source_probe_failed"}

    probes = {source.probe: source for source in sources}
    statuses = dict(zip(probes, await asyncio.gather(*(run(source) for source in probes.values()))))

    results: list[dict[str, Any]] = []
    for source in sources:
        status = statuses[source.probe]
        reachable = bool(status.get("available", status.get("reachable", False)))
        results.append({**source.declaration(), "reachable": reachable, "status": status})
    return results
