"""The integration seam, worked: connectors behind agent-callable tools.

This is the shape the box was extracted from — a set of tools an LLM agent
calls with generated query text. Copy it, replace the projections, delete
the tools you do not need.

Four things this file demonstrates, all of which are the point:

1. **Wiring is one call.** ``connect(config)`` at startup; connectors are
   built lazily and cached.
2. **Projection stays here.** The connectors return generic shapes; the
   field names, the caps, the vocabulary of your domain live in this file
   and never enter the package.
3. **Failure is a return value.** Every tool returns a JSON string. A tool
   that raises into an agent runtime produces a stack trace where an
   explanation was needed.
4. **The grant is visible.** Every mutation this file is allowed to make
   is a policy object constructed below, at the composition root, in one
   block you can read in ten seconds. A tool that mutates takes its policy
   from that block; a tool that does not, cannot.

Run it directly to see the wiring, the configured-service report and the
grants, without contacting anything::

    python3 examples/agent_tools.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from azdata import (
    AzureDataConfig,
    ProvisionPolicy,
    SearchDocuments,
    WritePolicy,
    connect,
)

# One config, resolved once at startup and frozen. In a real application
# this lives in the composition root next to the rest of your wiring.
CONFIG = AzureDataConfig.from_env()
CONNECTORS = connect(CONFIG)

# ---------------------------------------------------------------------------
# The grants. Everything this process may mutate is here and nowhere else.
#
# Read them as a permission list. Nothing below this block widens them: a
# connector built without one of these objects is read-only, and delete is
# a grant of its own, so the ingest path physically cannot remove a
# document however wrong its input is.
# ---------------------------------------------------------------------------

#: Load documents and items. Verification defaults on — an accepted write
#: is not a stored one, and this path is where that bites.
INGEST = WritePolicy.writable(verify_writes=True)

#: Delete, and *only* delete. allow_write stays False on purpose: a
#: retention job that can also write is a retention job that can restore
#: what it just removed.
RETENTION = WritePolicy(allow_delete=True, verify_writes=True)

#: Create or update infrastructure. No delete: teardown is separate below.
DEPLOY = ProvisionPolicy.deployable()

#: Destroy infrastructure. Held apart from DEPLOY so the two never travel
#: together by accident.
TEARDOWN = ProvisionPolicy.deployable(allow_delete=True)

KNOWLEDGE_INDEX = "knowledge-base"


def _mutation_summary(payload: str) -> str:
    """Project a write envelope into the agent's vocabulary.

    The same reason ``project_doc`` exists on the read side: the envelope
    is the package's shape, and an agent should be handed the two or three
    facts it can act on rather than every field the connector emitted.
    """
    parsed = json.loads(payload)
    if parsed.get("error"):
        return json.dumps({"status": "failed", "reason": parsed["detail"]})
    failed = parsed.get("failed") or []
    return json.dumps(
        {
            "status": "ok" if not failed else "partial",
            "operation": parsed["operation"],
            "written": parsed["count"],
            "verified": parsed["verified"],
            "rejected": [{"key": f["key"], "reason": f["detail"]} for f in failed],
        }
    )


def _provision_summary(payload: str) -> str:
    """Project a deploy envelope. ``drift`` is the field worth surfacing.

    A non-empty drift means ARM accepted the write and something reverted
    it, so the agent is building on infrastructure that is not in the
    requested state.
    """
    parsed = json.loads(payload)
    if parsed.get("error"):
        return json.dumps({"status": "failed", "reason": parsed["detail"]})
    return json.dumps(
        {
            "status": "ok",
            "resource": f"{parsed['resource_kind']}/{parsed['name']}",
            "created": parsed.get("created"),
            "deleted": parsed.get("deleted"),
            "state": parsed.get("state") or "unknown",
            "drift": parsed.get("drift") or {},
        }
    )


async def query_graph(query: str) -> str:
    """Run a Gremlin traversal. Writes are refused; a limit is injected.

    The connector already returns a JSON string, so this tool is a
    one-liner. It exists as a separate function so the docstring the agent
    reads describes your graph, not the transport.
    """
    return await CONNECTORS.gremlin.execute(query)


async def query_telemetry(query: str) -> str:
    """Run a KQL query, projecting the generic shape into your vocabulary.

    ``project`` is where a domain lives. Renaming columns, dropping
    internal fields, or capping row width belongs here — never inside the
    connector, which must stay reusable by the next caller.
    """

    def project(shaped: dict) -> dict:
        return {
            "fields": [column["name"] for column in shaped["columns"]],
            "records": shaped["rows"],
            "record_count": len(shaped["rows"]),
        }

    return await CONNECTORS.kql.execute(query, project=project)


async def search_knowledge(question: str) -> str:
    """Retrieve documents. Note the required per-hit projection.

    The connector cannot know which field holds your text, so it refuses to
    guess. Text-field priority, the length cap and the score rounding are
    all decisions with consequences for whoever reads the result.
    """
    text_fields = ("chunk", "content", "text", "body")

    def project_doc(doc: dict) -> dict:
        text = next((str(doc[f]) for f in text_fields if doc.get(f)), "")
        return {
            "title": doc.get("title") or doc.get("filename") or "untitled",
            "text": text[:2000],
            "score": round(float(doc.get("@search.score", 0.0)), 3),
        }

    # The SDK is synchronous; keep it off the event loop.
    return await asyncio.to_thread(
        CONNECTORS.search.execute,
        question,
        index_name="knowledge-base",
        semantic_config="knowledge-base-semantic",
        project_doc=project_doc,
        top_k=5,
    )


async def query_ontology(gql: str) -> str:
    """Run a GQL query against a Fabric GraphModel.

    This connector returns a dict rather than a string, precisely so the
    projection below can happen before serialisation.
    """
    result = await CONNECTORS.graph.execute(gql)
    if result.get("error"):
        return json.dumps(result)
    return json.dumps({"rows": result["data"], "row_count": len(result["data"])})


async def load_session(session_id: str) -> dict | None:
    """Read one document from Cosmos NoSQL, with the breaker respected.

    The container handle is yours; the connector owns connection,
    resilience and lifecycle, not your query.
    """
    store = CONNECTORS.cosmos("sessions", "conversations")
    store.check_breaker()
    try:
        async for item in store.container.query_items(
            query="SELECT TOP 1 * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": session_id}],
        ):
            store.ok()
            return item
        store.ok()
        return None
    except Exception as exc:
        raise store.fail(exc) from exc


# ---------------------------------------------------------------------------
# Write plane. Every tool below names one of the grants declared at the top.
# ---------------------------------------------------------------------------


async def index_knowledge(documents: list[dict]) -> str:
    """Upsert documents into the knowledge index.

    ``upload`` rather than ``create`` because re-running a load is the
    normal case and only ``upload`` is idempotent. Verification is on
    through ``INGEST``: Search accepts a document seconds before it is
    retrievable, so an unverified success here means nothing.
    """
    writer = CONNECTORS.documents(KNOWLEDGE_INDEX, policy=INGEST)
    return _mutation_summary(await writer.upload(documents))


async def retire_knowledge(document_ids: list[str]) -> str:
    """Delete documents by key, under a grant that cannot write.

    Built directly rather than through ``CONNECTORS.documents(...)``: that
    method caches one connector per index name, so a second call for the
    same index returns the first connector *and its policy*. Asking for a
    delete-granted writer after an ingest-granted one would silently hand
    back the ingest one and refuse the delete.
    """
    writer = SearchDocuments.from_config(
        CONFIG,
        CONNECTORS.credential_provider,
        index_name=KNOWLEDGE_INDEX,
        policy=RETENTION,
    )
    return _mutation_summary(await writer.delete(document_ids))


async def record_readings(readings: list[dict]) -> str:
    """Write telemetry items to Cosmos NoSQL.

    ``partition_key_field`` is the caller's schema and has no default. Get
    it wrong and writes succeed while point reads 404 and deletes no-op,
    which is the failure the whole Cosmos write plane exists to prevent.
    """
    writer = CONNECTORS.items(
        "telemetry",
        "readings",
        partition_key_field="site",
        policy=INGEST,
    )
    return _mutation_summary(await writer.upload(readings))


async def record_assets(assets: list[dict]) -> str:
    """Upsert vertices into the configured graph.

    Every literal in the generated traversal is escaped, so an asset named
    ``o'brien`` is a name rather than a syntax error, and a value shaped
    like a second statement is a value.
    """
    writer = CONNECTORS.elements(
        "asset",
        partition_key_field="site",
        policy=INGEST,
    )
    return _mutation_summary(await writer.upload(assets))


# ---------------------------------------------------------------------------
# Deploy plane. Only for a run that legitimately owns the resource it is
# standing up. Long-lived infrastructure still belongs in Bicep.
# ---------------------------------------------------------------------------


async def ensure_knowledge_index() -> str:
    """Create or update the knowledge index, and prove it stayed created.

    The field list is the schema, so it lives here rather than in the
    package. ``ensure`` re-reads afterwards and reports a declared field
    that is not in the live index as drift \u2014 the failure that otherwise
    surfaces as documents silently dropping a value months later.
    """
    provisioner = CONNECTORS.provision_search_index(KNOWLEDGE_INDEX, policy=DEPLOY)
    return _provision_summary(
        await provisioner.ensure(
            {
                "name": KNOWLEDGE_INDEX,
                "fields": [
                    {"name": "id", "type": "Edm.String", "key": True},
                    {"name": "title", "type": "Edm.String", "searchable": True},
                    {"name": "chunk", "type": "Edm.String", "searchable": True},
                ],
            }
        )
    )


async def ensure_reading_container() -> str:
    """Create or update the Cosmos container the write plane loads into.

    The spec is ARM-shaped and passed through untouched. The partition key
    path is the one field compared on the read-back, because it is the one
    whose corruption is silent.
    """
    provisioner = CONNECTORS.provision_cosmos_container(
        "telemetry", "readings", policy=DEPLOY
    )
    return _provision_summary(
        await provisioner.ensure(
            {
                "location": CONFIG.location,
                "properties": {
                    "resource": {
                        "id": "readings",
                        "partitionKey": {"paths": ["/site"], "kind": "Hash"},
                    },
                    "options": {"throughput": 400},
                },
            }
        )
    )


async def teardown_knowledge_index() -> str:
    """Delete the index. Note the separate policy object.

    ``TEARDOWN`` is the only grant in this file that permits a delete of
    infrastructure, and it is used by exactly one function.
    """
    provisioner = CONNECTORS.provision_search_index(KNOWLEDGE_INDEX, policy=TEARDOWN)
    return _provision_summary(await provisioner.teardown())


async def _demo() -> None:
    print("configured services:")
    for name, ready in CONNECTORS.configured().items():
        print(f"  {name:<12} {'yes' if ready else 'no'}")
    print("\ngrants held by this process:")
    for label, policy in (("ingest", INGEST), ("retention", RETENTION)):
        print(
            f"  {label:<12} write={policy.allow_write} "
            f"delete={policy.allow_delete} verify={policy.verify_writes}"
        )
    for label, policy in (("deploy", DEPLOY), ("teardown", TEARDOWN)):
        print(
            f"  {label:<12} create={policy.allow_create} "
            f"delete={policy.allow_delete} verify={policy.verify_after_write}"
        )
    print(
        "\nUnconfigured connectors return an error envelope naming the "
        "missing setting rather than raising:"
    )
    print(" ", await query_graph("g.V().limit(1)"))
    await CONNECTORS.aclose()


if __name__ == "__main__":
    asyncio.run(_demo())
