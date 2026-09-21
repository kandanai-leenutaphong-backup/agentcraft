from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path

PACKAGE_SHA256 = "c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_package(directory):
    payload = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != PACKAGE_SHA256:
        raise ValueError("package_digest_mismatch")
    manifest = json.loads(payload)
    for name, metadata in manifest["artifacts"].items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise ValueError("package_path_invalid")
        content = path.read_bytes()
        if len(content) != metadata["bytes"] or hashlib.sha256(content).hexdigest() != metadata["sha256"]:
            raise ValueError("package_artifact_mismatch")
    documents = {name: json.loads((directory / f"{name}.json").read_bytes()) for name in ("cosmos", "gremlin", "search")}
    if (len(documents["cosmos"]), len(documents["gremlin"]["vertices"]), len(documents["gremlin"]["edges"]),
            len(documents["search"])) != (4, 10, 19, 3135):
        raise ValueError("package_counts_mismatch")
    return manifest, documents


def graph_properties(properties):
    return {name: json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (list, dict)) else value for name, value in properties.items()}


def graph_upsert(element, *, edge=False):
    bindings = {"partition": element["properties"]["partition"], "identifier": element["id"], "label": element["label"]}
    if edge:
        bindings.update(source=element["from_id"], target=element["to_id"])
        query = ("g.V([partition,source]).coalesce(outE(label).hasId(identifier),"
                 "addE(label).to(__.V([partition,target])).property('id',identifier))")
    else:
        query = "g.V([partition,identifier]).fold().coalesce(unfold(),addV(label).property('id',identifier).property('partition',partition))"
    properties = graph_properties({**element["properties"], "generation": PACKAGE_SHA256})
    for index, (name, value) in enumerate(sorted(properties.items())):
        if name == "partition":
            continue
        bindings[f"name{index}"] = name
        bindings[f"value{index}"] = value
        query += f".property(name{index},value{index})"
    return query + ".id()", bindings


def verify_graph(client, manifest, graph):
    partition = manifest["partition"]
    observed = {}
    for kind, traversal in (("vertices", "V"), ("edges", "E")):
        rows = client.submit(f"g.{traversal}().has('partition',partition).limit(100)", {"partition": partition}).all().result(timeout=60)
        expected = {item["id"]: item for item in graph[kind]}
        if {row["id"] for row in rows} != set(expected) or len(rows) != len(expected):
            raise ValueError("graph_id_readback_mismatch")
        for row in rows:
            wanted = expected[row["id"]]
            if row["label"] != wanted["label"]:
                raise ValueError("graph_label_readback_mismatch")
            if kind == "edges" and (row["outV"] != wanted["from_id"] or row["inV"] != wanted["to_id"]):
                raise ValueError("graph_edge_readback_mismatch")
            properties = row["properties"]
            for name, value in graph_properties({**wanted["properties"], "generation": PACKAGE_SHA256}).items():
                if kind == "edges" and name == "partition":
                    continue
                actual = properties.get(name)
                if isinstance(actual, list):
                    if len(actual) != 1:
                        raise ValueError("graph_property_cardinality_mismatch")
                    actual = actual[0]["value"]
                if actual != value:
                    raise ValueError("graph_provenance_readback_mismatch")
        observed[kind] = {"count": len(rows), "ids_sha256": digest(sorted(expected)), "provenance_verified": True}
    return observed


async def load_stores(config, manifest, documents, *, credential):
    from azdata import (ConnectorConfig, ContentValue, Limits, Policy, QueryRequest, ReadRequest,
                        RecordInput, RecordKey, ResourceAddress, SchemaRequest, UpsertRequest, connect)

    names = config["names"]
    endpoint = f"https://{names['cosmos']}.documents.azure.com"
    search_endpoint = f"https://{names['search']}.search.windows.net"
    cosmos_config = ConnectorConfig(endpoint, ResourceAddress({"database": "investigation", "container": "telemetry"}),
        (f"{names['cosmos']}.documents.azure.com",), partition_key_field="partition")
    search_config = ConnectorConfig(search_endpoint, ResourceAddress({"index": "public-mitre"}),
        (f"{names['search']}.search.windows.net",))
    policy = Policy("deployment-public-ingestion", {"read", "query", "upsert", "schema.read", "schema.create"},
        limits=Limits(timeout_seconds=120, max_items=100, max_input_bytes=2_000_000, max_output_bytes=2_000_000))

    def success(result):
        if result.status != "success" or any(item.status != "success" for item in result.items):
            print(json.dumps({"status": "failed", "stage": "connector", "service": result.service,
                "operation": result.operation, "result_status": result.status,
                "codes": [error.code for error in result.errors] + [item.error.code for item in result.items if item.error]}), flush=True)
            raise RuntimeError("ingestion_connector_" + result.status)

    async with connect("cosmos", cosmos_config, credential=credential, policy=policy) as cosmos, \
            connect("search", search_config, credential=credential, policy=policy) as search:
        schema = await search.schema(SchemaRequest(action="read"))
        if schema.status == "not_found":
            sample = documents["search"][0]
            fields = [{"name": name, "type": "Collection(Edm.String)" if isinstance(value, list) else
                       "Edm.Boolean" if isinstance(value, bool) else "Edm.String", "key": name == "id",
                       "searchable": isinstance(value, str) and name in {"title", "content", "body", "definition"},
                       "filterable": name not in {"content", "body", "definition", "summary"}, "retrievable": True}
                      for name, value in {**sample, "generation": PACKAGE_SHA256}.items()]
            success(await search.schema(SchemaRequest(action="create", definition={"name": "public-mitre", "fields": fields})))
        else:
            success(schema)
        for connector, name in ((cosmos, "cosmos"), (search, "search")):
            items = documents[name]
            for start in range(0, len(items), 50):
                chunk = items[start:start + 50]
                records = tuple(RecordInput(RecordKey({"id": item["id"]}, item.get("partition")),
                    ContentValue({**item, "generation": PACKAGE_SHA256})) for item in chunk)
                success(await connector.upsert(UpsertRequest(mode="replace", records=records)))
            for start in range(0, len(items), 50):
                chunk = items[start:start + 50]
                result = await connector.read(ReadRequest(keys=tuple(RecordKey({"id": item["id"]}, item.get("partition")) for item in chunk)))
                success(result)
                if len(result.items) != len(chunk):
                    raise ValueError("store_readback_count_mismatch")
                for expected, actual in zip(chunk, result.items):
                    data = actual.content.to_native()
                    if any(data.get(key) != value for key, value in {**expected, "generation": PACKAGE_SHA256}.items()):
                        raise ValueError("store_readback_content_mismatch")
        counted = await cosmos.query(QueryRequest(dialect="cosmos-sql", expression="SELECT COUNT(1) AS count FROM c WHERE c.partition = @partition",
            parameters={"@partition": manifest["partition"]}, service_options={"cosmos": {"partition": manifest["partition"]}}))
        success(counted)
        if counted.items[0].content.to_native() != {"count": 4}:
            raise ValueError("cosmos_count_mismatch")
    return {name: {"count": len(documents[name]), "ids_sha256": digest(sorted(item["id"] for item in documents[name])),
                   "content_verified": True} for name in ("cosmos", "search")}


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    from investigation import load_config
    from azure.identity.aio import DefaultAzureCredential
    from gremlin_python.driver.client import Client
    from gremlin_python.driver.serializer import GraphSONSerializersV2d0

    manifest, documents = load_package(args.package)
    config = load_config(args.config)
    key = os.environ.get("GREMLIN_INGESTION_KEY", "")
    if not key:
        raise ValueError("platform_writer_credential_missing")
    client = Client(f"wss://{config['names']['gremlin']}.gremlin.cosmos.azure.com:443/", "g",
        username="/dbs/investigation/colls/ontology", password=key,
        message_serializer=GraphSONSerializersV2d0())
    try:
        for iteration in (1, 2):
            for kind in ("vertices", "edges"):
                print(json.dumps({"status": "started", "stage": "graph-" + kind, "pass": iteration}), flush=True)
                for element in documents["gremlin"][kind]:
                    query, bindings = graph_upsert(element, edge=kind == "edges")
                    if client.submit(query, bindings).all().result(timeout=60) != [element["id"]]:
                        raise ValueError("graph_upsert_ack_mismatch")
            graph = verify_graph(client, manifest, documents["gremlin"])
            print(json.dumps({"status": "verified", "stage": "graph", "pass": iteration, "counts": {kind: graph[kind]["count"] for kind in graph}}), flush=True)

            async def load():
                async with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
                    return await load_stores(config, manifest, documents, credential=credential)

            stores = asyncio.run(load())
            print(json.dumps({"status": "verified", "pass": iteration, "package_sha256": PACKAGE_SHA256,
                              "observed_at": datetime.now(timezone.utc).isoformat(), "graph": graph, "stores": stores}), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "payload": "omitted"}), flush=True)
        raise SystemExit(1) from None