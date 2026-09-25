#!/usr/bin/env python3
"""Load and verify the GridIQ mock dataset in the rg-test-grid stores.

Every data-plane call uses an Entra token from the signed-in az CLI identity.
No key, connection string or SAS is read, printed or stored.

Invoked by deploy.sh; run directly only with the same environment:
    python3 -B stores.py <check-data|load-kql|load-graph|load-search|verify|record> --outputs FILE
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "out"
RECORDS = HERE / "records"
SEARCH_API = "2024-07-01"
OPENAI_API = "2024-10-21"
KQL_CHUNK_ROWS = 3000
RBAC_WAIT_S = 900
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.]+$")
KQL_TABLES = (("WatcherAlarmsAll", "kql/WatcherAlarmsAll.csv"), ("WatcherScadaAll", "kql/WatcherScadaAll.csv"))


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, flush=True)


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"missing environment variable {name}; run through deploy.sh")
    return value


def load_outputs(path: str) -> dict:
    raw = json.loads(Path(path).read_text())
    return {k: v["value"] for k, v in raw.items()}


_CRED = None


def credential():
    global _CRED
    if _CRED is None:
        from azure.identity import AzureCliCredential
        _CRED = AzureCliCredential(tenant_id=env("AZURE_TENANT_ID"), process_timeout=60)
    return _CRED


_TOKENS: dict[str, tuple[str, float]] = {}


def token(scope: str) -> str:
    cached = _TOKENS.get(scope)
    if cached and cached[1] - time.time() > 300:
        return cached[0]
    tok = credential().get_token(scope)
    _TOKENS[scope] = (tok.token, float(tok.expires_on))
    return tok.token


def write_record(step: str, payload: dict) -> Path:
    RECORDS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for n in range(100):
        path = RECORDS / (f"{stamp}_{step}.json" if n == 0 else f"{stamp}_{step}-{n}.json")
        try:
            with open(path, "x", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True, default=str)
                fh.write("\n")
            log(f"record: {path.relative_to(HERE)}")
            return path
        except FileExistsError:
            continue
    raise SystemExit("could not allocate a new record name")


def manifest() -> dict:
    return json.loads((DATA / "manifest.json").read_text())


def check_data() -> dict:
    man = manifest()
    bad = []
    for rel, meta in man["files"].items():
        body = (DATA / rel).read_bytes()
        if hashlib.sha256(body).hexdigest() != meta["sha256"] or len(body) != meta["bytes"]:
            bad.append(rel)
    if bad:
        raise SystemExit(f"out/ differs from manifest.json: {bad}")
    log(f"data: {len(man['files'])} files match manifest.json sha256")
    return man


def retry(fn, what: str, *, attempts: int = 6, wait: float = 10.0, deadline_s: float | None = None,
          transient=lambda exc: True):
    start = time.time()
    n = 0
    while True:
        n += 1
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - classified by `transient`
            elapsed = time.time() - start
            limit_hit = (deadline_s is not None and elapsed > deadline_s) or (deadline_s is None and n >= attempts)
            if limit_hit or not transient(exc):
                raise
            log(f"  retry {what} ({n}, {int(elapsed)}s): {type(exc).__name__}: {str(exc)[:160]}")
            time.sleep(wait)


# ---------------------------------------------------------------- KQL (ADX)

def kusto(outputs: dict):
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(outputs["adxQueryUri"], credential())
    return KustoClient(kcsb)


def kql(client, db: str, query: str) -> list[dict]:
    result = client.execute_query(db, query)
    return result.primary_results[0].to_dict()["data"]


def schema_commands() -> dict[str, tuple[str, list[str]]]:
    text = (DATA / "kql/schema.kql").read_text()
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\.create-merge table (\w+) \((.*)\)\s*$", line.strip())
        if m:
            cols = [c.split(":")[0].strip() for c in m.group(2).split(",")]
            out[m.group(1)] = (line.strip(), cols)
    return out


def load_kql(outputs: dict) -> dict:
    db = outputs["adxDatabase"]
    client = kusto(outputs)
    schema = schema_commands()
    receipt = {"step": "load-kql", "started": utcnow(), "cluster": outputs["adxQueryUri"], "database": db, "tables": {}}
    retry(lambda: kql(client, db, "print 1"), "adx reachability", deadline_s=RBAC_WAIT_S, wait=20)
    for table, (cmd, _cols) in schema.items():
        retry(lambda c=cmd: client.execute_mgmt(db, c), f"create-merge {table}")
    for table, rel in KQL_TABLES:
        rows = list(csv.reader(io.StringIO((DATA / rel).read_text(encoding="utf-8"))))
        header, body = rows[0], rows[1:]
        if header != schema[table][1]:
            raise SystemExit(f"{rel} header {header} != schema columns {schema[table][1]}")
        retry(lambda t=table: client.execute_mgmt(db, f".clear table {t} data"), f"clear {table}")
        chunks = 0
        for i in range(0, len(body), KQL_CHUNK_ROWS):
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(body[i:i + KQL_CHUNK_ROWS])
            command = f".ingest inline into table {table} with (format='csv') <|\n{buf.getvalue()}"
            retry(lambda c=command: client.execute_mgmt(db, c), f"ingest {table} chunk {chunks}")
            chunks += 1
        count = kql(client, db, f"{table} | count")[0]["Count"]
        receipt["tables"][table] = {"source_rows": len(body), "chunks": chunks, "rows_after": count}
        log(f"load-kql: {table} rows={count} (source {len(body)}, {chunks} inline chunks)")
        if count != len(body):
            raise SystemExit(f"{table}: {count} rows after load, expected {len(body)}")
    receipt["finished"] = utcnow()
    return receipt


def verify_kql(outputs: dict, man: dict) -> dict:
    db = outputs["adxDatabase"]
    client = kusto(outputs)
    alarm_rows = list(csv.DictReader(io.StringIO((DATA / "kql/WatcherAlarmsAll.csv").read_text(encoding="utf-8"))))
    expected = {
        "WatcherScadaAll.rows": man["counts"]["scada_rows"],
        "WatcherAlarmsAll.rows": man["counts"]["alarm_rows"],
        "WatcherScadaAll.distinct_TagId": man["counts"]["tags"],
        "WatcherAlarmsAll.distinct_alarm_label": len({r["alarm_label"] for r in alarm_rows}),
    }
    observed = {
        "WatcherScadaAll.rows": kql(client, db, "WatcherScadaAll | count")[0]["Count"],
        "WatcherAlarmsAll.rows": kql(client, db, "WatcherAlarmsAll | count")[0]["Count"],
        "WatcherScadaAll.distinct_TagId": kql(client, db, "WatcherScadaAll | distinct TagId | count")[0]["Count"],
        "WatcherAlarmsAll.distinct_alarm_label": kql(client, db, "WatcherAlarmsAll | distinct alarm_label | count")[0]["Count"],
    }
    span = kql(client, db, "WatcherScadaAll | summarize min(timestamp_aest), max(timestamp_aest)")[0]
    return {
        "expected": expected,
        "observed": observed,
        "scada_time_span": [str(v) for v in span.values()],
        "expected_source": "manifest.json counts; distinct_alarm_label computed from out/kql/WatcherAlarmsAll.csv",
        "ok": expected == observed,
    }


# ---------------------------------------------------------------- Gremlin (Cosmos DB)

class Gremlin:
    def __init__(self, outputs: dict):
        self.outputs = outputs
        self.client = None
        self.expires = 0.0

    def _connect(self):
        from gremlin_python.driver import client as gremlin_client, serializer
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001 - replacing a dead client
                pass
        _TOKENS.pop("https://cosmos.azure.com/.default", None)
        tok = token("https://cosmos.azure.com/.default")
        self.expires = _TOKENS["https://cosmos.azure.com/.default"][1]
        self.client = gremlin_client.Client(
            url=self.outputs["cosmosGremlinEndpoint"],
            traversal_source="g",
            username=f"/dbs/{self.outputs['cosmosDatabase']}/colls/{self.outputs['cosmosGraph']}",
            password=tok,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    def submit(self, query: str, bindings: dict | None = None) -> list:
        def once():
            if self.client is None or self.expires - time.time() < 300:
                self._connect()
            try:
                return self.client.submit(query, bindings or {}).all().result()
            except Exception:
                self.client = None
                raise
        return retry(once, "gremlin", attempts=8, wait=5,
                     transient=lambda e: any(s in str(e) for s in ("429", "TooManyRequests", "RequestRateTooLarge",
                                                                  "Connection", "closed", "timeout", "1008", "503")))

    def close(self):
        if self.client is not None:
            self.client.close()


def _gremlin_ready(g: Gremlin) -> None:
    def probe():
        g.client = None
        return g.submit("g.V().limit(1).count()")
    retry(probe, "gremlin auth/reachability", deadline_s=RBAC_WAIT_S, wait=30)


def load_graph(outputs: dict) -> dict:
    pk = env("GRAPH_PK")
    vertices = [json.loads(line) for line in (DATA / "graph/vertices.jsonl").read_text().splitlines() if line.strip()]
    edges = [json.loads(line) for line in (DATA / "graph/edges.jsonl").read_text().splitlines() if line.strip()]
    receipt = {"step": "load-graph", "started": utcnow(), "endpoint": outputs["cosmosGremlinEndpoint"],
               "database": outputs["cosmosDatabase"], "graph": outputs["cosmosGraph"], "pk": pk}
    g = Gremlin(outputs)
    _gremlin_ready(g)
    before = {"vertices": g.submit("g.V().has('pk',pk).count()", {"pk": pk})[0],
              "edges": g.submit("g.E().has('pk',pk).count()", {"pk": pk})[0]}
    for n, v in enumerate(vertices, 1):
        if v["properties"].get("pk") != pk or not SAFE_NAME.match(v["label"]):
            raise SystemExit(f"vertex {v['id']}: unexpected pk or label")
        parts = ["g.V(vid).has('pk',pk).fold().coalesce(unfold(), addV('%s').property('id',vid).property('pk',pk)" % v["label"]]
        bindings = {"vid": v["id"], "pk": pk}
        i = 0
        for key, value in v["properties"].items():
            if key in ("pk", "id"):
                continue
            if not SAFE_NAME.match(key):
                raise SystemExit(f"vertex {v['id']}: unsafe property key {key!r}")
            parts.append(".property('%s',p%d)" % (key, i))
            bindings[f"p{i}"] = value
            i += 1
        parts.append(").id()")
        got = g.submit("".join(parts), bindings)
        if got != [v["id"]]:
            raise SystemExit(f"vertex upsert {v['id']} returned {got}")
        if n % 50 == 0:
            log(f"load-graph: {n}/{len(vertices)} vertices")
    for n, e in enumerate(edges, 1):
        if e["properties"].get("pk") != pk or not SAFE_NAME.match(e["label"]):
            raise SystemExit(f"edge {e['id']}: unexpected pk or label")
        query = ("g.V(ov).has('pk',pk).coalesce(outE('%s').hasId(eid), "
                 "addE('%s').to(g.V(iv).has('pk',pk)).property('id',eid).property('pk',pk)).id()") % (e["label"], e["label"])
        got = g.submit(query, {"ov": e["out"], "iv": e["in"], "eid": e["id"], "pk": pk})
        if got != [e["id"]]:
            raise SystemExit(f"edge upsert {e['id']} returned {got}")
        if n % 50 == 0:
            log(f"load-graph: {n}/{len(edges)} edges")
    after = {"vertices": g.submit("g.V().has('pk',pk).count()", {"pk": pk})[0],
             "edges": g.submit("g.E().has('pk',pk).count()", {"pk": pk})[0]}
    g.close()
    receipt.update(before=before, after=after, source={"vertices": len(vertices), "edges": len(edges)}, finished=utcnow())
    log(f"load-graph: before={before} after={after}")
    if after != {"vertices": len(vertices), "edges": len(edges)}:
        raise SystemExit(f"graph counts after load {after} != source")
    return receipt


def verify_graph(outputs: dict, man: dict) -> dict:
    pk = env("GRAPH_PK")
    g = Gremlin(outputs)
    _gremlin_ready(g)
    observed = {
        "vertices_pk": g.submit("g.V().has('pk',pk).count()", {"pk": pk})[0],
        "edges_pk": g.submit("g.E().has('pk',pk).count()", {"pk": pk})[0],
        "vertices_all": g.submit("g.V().count()")[0],
        "edges_all": g.submit("g.E().count()")[0],
    }
    g.close()
    expected = {"vertices_pk": man["counts"]["vertices"], "edges_pk": man["counts"]["edges"],
                "vertices_all": man["counts"]["vertices"], "edges_all": man["counts"]["edges"]}
    return {"expected": expected, "observed": observed, "pk": pk, "ok": expected == observed}


# ---------------------------------------------------------------- Azure AI Search

def http(method: str, url: str, scope: str, body=None, timeout: int = 60) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token(scope)}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8-sig", "replace")


SEARCH_SCOPE = "https://search.azure.com/.default"


def search_url(outputs: dict, path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{outputs['searchEndpoint']}{path}{sep}api-version={SEARCH_API}"


def search_ok(outputs: dict, method: str, path: str, body=None, what: str = "search") -> dict | str:
    def once():
        status, text = http(method, search_url(outputs, path), SEARCH_SCOPE, body)
        if status >= 300:
            raise RuntimeError(f"HTTP {status}: {text[:300]}")
        return json.loads(text) if text.strip().startswith(("{", "[")) else text
    return once() if what == "once" else retry(
        once, what, deadline_s=RBAC_WAIT_S, wait=20,
        transient=lambda e: any(f"HTTP {c}" in str(e) for c in (401, 403, 429, 502, 503)))


def index_dirs() -> list[Path]:
    return sorted(p for p in (DATA / "search").iterdir() if p.is_dir())


def rewrite_index(ix: dict, outputs: dict) -> dict:
    for vz in ix.get("vectorSearch", {}).get("vectorizers", []):
        if vz.get("kind") != "azureOpenAI":
            raise SystemExit(f"{ix['name']}: unsupported vectorizer kind {vz.get('kind')}")
        params = vz["azureOpenAIParameters"]
        params["resourceUri"] = outputs["aisOpenAIEndpoint"].rstrip("/")
        params["deploymentId"] = outputs["embedDeployment"]
        params["modelName"] = outputs["embedModel"]
        params.pop("apiKey", None)
        params.pop("authIdentity", None)
    if "${" in json.dumps(ix):
        raise SystemExit(f"{ix['name']}: unresolved placeholder after rewrite")
    return ix


def vector_field(ix: dict) -> dict:
    vfs = [f for f in ix["fields"] if f.get("dimensions")]
    if len(vfs) != 1:
        raise SystemExit(f"{ix['name']}: expected one vector field, found {[f['name'] for f in vfs]}")
    return vfs[0]


def openai_client(outputs: dict):
    from azure.identity import get_bearer_token_provider
    from openai import AzureOpenAI
    return AzureOpenAI(
        azure_endpoint=outputs["aisOpenAIEndpoint"],
        azure_ad_token_provider=get_bearer_token_provider(credential(), "https://cognitiveservices.azure.com/.default"),
        api_version=OPENAI_API,
        max_retries=10,
    )


def load_search(outputs: dict) -> dict:
    receipt = {"step": "load-search", "started": utcnow(), "endpoint": outputs["searchEndpoint"],
               "embedding": {"endpoint": outputs["aisOpenAIEndpoint"], "deployment": outputs["embedDeployment"],
                             "embedded_field": "chunk"}, "indexes": {}}
    search_ok(outputs, "GET", "/indexes?$select=name", what="search control-plane RBAC")
    oai = openai_client(outputs)
    for d in index_dirs():
        ix = rewrite_index(json.loads((d / "index.json").read_text()), outputs)
        if ix["name"] != d.name:
            raise SystemExit(f"{d}: index name {ix['name']} != directory")
        vf = vector_field(ix)
        search_ok(outputs, "PUT", f"/indexes/{ix['name']}?allowIndexDowntime=false", ix, what=f"put index {ix['name']}")
        docs = [json.loads(line) for line in (d / "documents.jsonl").read_text().splitlines() if line.strip()]
        texts = [doc["chunk"][:8000] for doc in docs]

        def embed():
            return oai.embeddings.create(input=texts, model=outputs["embedDeployment"])
        resp = retry(embed, f"embed {ix['name']}", deadline_s=RBAC_WAIT_S, wait=30,
                     transient=lambda e: type(e).__name__ in ("PermissionDeniedError", "RateLimitError", "APIConnectionError",
                                                                "InternalServerError", "AuthenticationError"))
        vectors = [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]
        if any(len(v) != vf["dimensions"] for v in vectors):
            raise SystemExit(f"{ix['name']}: embedding length != {vf['dimensions']}")
        batch = [{**doc, vf["name"]: vec, "@search.action": "mergeOrUpload"} for doc, vec in zip(docs, vectors)]
        result = search_ok(outputs, "POST", f"/indexes/{ix['name']}/docs/index", {"value": batch},
                           what=f"upload {ix['name']}")
        succeeded = sum(1 for r in result["value"] if r.get("status"))
        receipt["indexes"][ix["name"]] = {"documents": len(docs), "succeeded": succeeded, "vector_field": vf["name"],
                                          "dimensions": vf["dimensions"], "embedding_tokens": resp.usage.total_tokens}
        log(f"load-search: {ix['name']} uploaded {succeeded}/{len(docs)} into {vf['name']} ({resp.usage.total_tokens} tokens)")
        if succeeded != len(docs):
            raise SystemExit(f"{ix['name']}: {succeeded}/{len(docs)} documents accepted")
    receipt["finished"] = utcnow()
    return receipt


def verify_search(outputs: dict, man: dict) -> dict:
    expected_counts = man["counts"]["search_documents"]
    out = {"indexes": {}, "ok": True}
    for d in index_dirs():
        ix = json.loads((d / "index.json").read_text())
        name = ix["name"]
        vf = vector_field(ix)["name"]
        key = next(f["name"] for f in ix["fields"] if f.get("key"))
        count = None
        for _ in range(12):
            count = int(str(search_ok(outputs, "GET", f"/indexes/{name}/docs/$count", what=f"count {name}")).strip())
            if count == expected_counts[name]:
                break
            time.sleep(5)
        live = search_ok(outputs, "GET", f"/indexes/{name}", what=f"get {name}")
        vz = live["vectorSearch"]["vectorizers"][0]["azureOpenAIParameters"]
        semantic = (live.get("semantic") or {}).get("configurations") or []
        body = {
            "search": "KESTREL MARLOW",
            "top": 3,
            "select": f"{key},title,chunk",
            "vectorQueries": [{"kind": "text", "text": "KESTREL MARLOW grid incident", "fields": vf, "k": 3}],
        }
        if semantic:
            body.update(queryType="semantic", semanticConfiguration=semantic[0]["name"])
        res = retry(lambda b=body: search_ok(outputs, "POST", f"/indexes/{name}/docs/search", b, what="once"),
                    f"hybrid {name}", attempts=8, wait=15)
        hits = res.get("value", [])
        naming = [h[key] for h in hits if re.search(r"KESTREL|MARLOW", f"{h.get('title', '')} {h.get('chunk', '')}")]
        reranked = bool(hits) and all("@search.rerankerScore" in h for h in hits)
        entry = {
            "expected_documents": expected_counts[name],
            "observed_documents": count,
            "vector_field": vf,
            "vectorizer": {"resourceUri": vz.get("resourceUri"), "deploymentId": vz.get("deploymentId"),
                           "apiKey_present": bool(vz.get("apiKey"))},
            "hybrid": {
                "mode": "keyword+vector+semantic" if semantic else "keyword+vector (index.json defines no semantic configuration)",
                "semantic_configuration": semantic[0]["name"] if semantic else None,
                "hits": len(hits),
                "hits_naming_kestrel_or_marlow": naming,
                "reranker_scores_present": reranked,
                "semantic_partial_reason": res.get("@search.semanticPartialResponseReason"),
                "top_title": hits[0].get("title") if hits else None,
            },
        }
        ok = (count == expected_counts[name] and bool(naming) and not vz.get("apiKey")
              and (reranked and not res.get("@search.semanticPartialResponseReason") if semantic else True))
        entry["ok"] = ok
        out["indexes"][name] = entry
        out["ok"] = out["ok"] and ok
        log(f"verify-search: {name} docs={count}/{expected_counts[name]} hits={len(hits)} naming={len(naming)} "
            f"semantic={'yes' if semantic else 'n/a'} reranked={reranked} ok={ok}")
    return out


# ---------------------------------------------------------------- Blob storage

def verify_blobs(outputs: dict, man: dict) -> dict:
    from azure.storage.blob import BlobServiceClient
    svc = BlobServiceClient(outputs["blobEndpoint"], credential=credential())
    container = svc.get_container_client(outputs["storageContainer"])
    listed = {b.name: b for b in retry(lambda: list(container.list_blobs()), "list blobs", deadline_s=RBAC_WAIT_S, wait=20)}
    expected = {}
    for d in index_dirs():
        body = (d / "report.pdf").read_bytes()
        expected[f"{d.name}/report.pdf"] = {"bytes": len(body), "md5": base64.b64encode(hashlib.md5(body).digest()).decode()}
    observed = {}
    for name, blob in listed.items():
        md5 = blob.content_settings.content_md5
        observed[name] = {"bytes": blob.size, "md5": base64.b64encode(bytes(md5)).decode() if md5 else None}
    return {"container": outputs["storageContainer"], "expected": expected, "observed": observed,
            "ok": expected == observed}


# ---------------------------------------------------------------- entry point

def verify(outputs: dict, label: str) -> int:
    man = check_data()
    result = {"step": "verify", "label": label, "started": utcnow()}
    sections = (("kql", verify_kql), ("graph", verify_graph), ("search", verify_search), ("blobs", verify_blobs))
    for name, fn in sections:
        try:
            result[name] = fn(outputs, man)
        except Exception as exc:  # noqa: BLE001 - one failed leg must not hide the others
            result[name] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}"}
        log(f"verify: {name} ok={result[name]['ok']}")
        if name in ("kql", "graph", "blobs") and "observed" in result[name]:
            if name == "blobs":
                log(f"  blobs: {sorted(result[name]['observed'])}")
            else:
                log(f"  expected={result[name]['expected']}")
                log(f"  observed={result[name]['observed']}")
    result["ok"] = all(result[name]["ok"] for name, _ in sections)
    result["finished"] = utcnow()
    write_record(f"verify-{label}" if label else "verify", result)
    log(f"verify: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["check-data", "load-kql", "load-graph", "load-search", "verify", "record"])
    ap.add_argument("--outputs", help="az deployment group show ... --query properties.outputs JSON file")
    ap.add_argument("--label", default="", help="verify record label")
    ap.add_argument("--step", help="record: step name (payload JSON on stdin)")
    args = ap.parse_args()
    if args.command == "check-data":
        check_data()
        return 0
    if args.command == "record":
        write_record(args.step, json.load(sys.stdin))
        return 0
    outputs = load_outputs(args.outputs)
    if args.command == "verify":
        return verify(outputs, args.label)
    check_data()
    fn = {"load-kql": load_kql, "load-graph": load_graph, "load-search": load_search}[args.command]
    write_record(args.command, fn(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
