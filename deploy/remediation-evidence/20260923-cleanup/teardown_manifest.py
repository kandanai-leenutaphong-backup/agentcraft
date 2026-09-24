"""Execute a digest-pinned teardown manifest: re-read, identity-check, delete, read back.

Dry run by default (reads only). `--execute` performs deletions in the fixed dependency order.
Every delete writes an intent line before and a result line with read-back after to an fsynced ledger.

    python3 -B deploy/remediation-evidence/20260923-cleanup/teardown_manifest.py \
        --manifest <manifest.json> --manifest-sha256 <digest> --run <oplog-run> [--execute]
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
OUT = ROOT / "teardown"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
TERMINAL = {"succeeded", "completed", "failed", "cancelled", "canceled", "incomplete", "expired"}
ACR_PULL = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
os.environ.update(PYTHONDONTWRITEBYTECODE="1", AZURE_CORE_COLLECT_TELEMETRY="false",
                  AZURE_LOGGING_ENABLE_LOG_FILE="false", AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no")
sys.dont_write_bytecode = True


class Absent(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def plain(value):
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: "<redacted>" if k.lower() in {"sas_uri", "token", "credential", "credentials", "password", "api_key"}
                else plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def not_found(error):
    return getattr(error, "status_code", None) == 404 or type(error).__name__ in {"ResourceNotFoundError", "NotFoundError"}


class Recorder:
    def __init__(self, args):
        self.args = args
        self.ledger = OUT / f"{STAMP}-ledger.jsonl"
        self.outcomes = []
        self.last_check = 0.0

    def write(self, label, value):
        path = OUT / f"{STAMP}-{label}.json"
        payload = (json.dumps(plain(value), indent=2, sort_keys=True, default=str) + "\n").encode()
        with path.open("xb") as handle:
            handle.write(payload)
        return path

    def line(self, event):
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(plain(event), sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.clock()

    def clock(self, force=False):
        if self.args.run and (force or time.monotonic() - self.last_check >= 45):
            subprocess.run([sys.executable, "-B", str(REPO / ".github/tools/oplog.py"), "check", "--run", self.args.run,
                            "--log", str(OUT / "worker-oplog.jsonl")], check=False, capture_output=True)
            self.last_check = time.monotonic()

    def step(self, kind, ident, read, check, delete, polls=4, interval=5.0, extra=None):
        """read() returns live state or raises Absent; check(state) returns a refusal reason or None."""
        base = {"kind": kind, "id": ident, **(extra or {})}
        if self.args.only_id and ident not in self.args.only_id:
            return None
        try:
            before = read()
        except Absent as absent:
            return self.finish(base | {"outcome": "already-absent", "pre_read": str(absent)})
        except Exception as error:
            return self.finish(base | {"outcome": "blocked", "reason": f"pre-read failed: {type(error).__name__}: {str(error)[:500]}"})
        refusal = check(before)
        if refusal:
            return self.finish(base | {"outcome": "refused", "reason": refusal, "pre_state": before})
        if not self.args.execute:
            return self.finish(base | {"outcome": "planned", "pre_state": before})
        self.line(base | {"event": "intent", "at": now(), "pre_state": before})
        error_text = returned = None
        started = time.monotonic()
        try:
            returned = plain(delete(before))
        except Exception as error:
            error_text = f"{type(error).__name__}: status={getattr(error, 'status_code', None)}: {str(error)[:800]}"
        seconds = round(time.monotonic() - started, 3)
        after = None
        for attempt in range(polls):
            try:
                after = read()
            except Absent as absent:
                return self.finish(base | {"outcome": "deleted", "delete_error": error_text, "delete_seconds": seconds, "delete_returned": returned,
                                           "readback": f"absent: {absent}", "readback_attempts": attempt + 1}, ledger=True)
            except Exception as error:
                after = f"readback error {type(error).__name__}: {str(error)[:300]}"
            if attempt + 1 < polls:
                time.sleep(interval)
        return self.finish(base | {"outcome": "still-present" if error_text is None else "delete-failed",
                                   "delete_error": error_text, "delete_seconds": seconds, "delete_returned": returned,
                                   "readback": after}, ledger=True)

    def finish(self, record, ledger=False):
        record.setdefault("at", now())
        if ledger:
            self.line(record | {"event": "result"})
        self.outcomes.append(record)
        print(json.dumps({k: record.get(k) for k in ("kind", "id", "outcome", "reason", "delete_error")}, default=str)[:400], flush=True)
        return record


def cli(arguments, timeout=180):
    if "--subscription" not in arguments:
        raise ValueError("explicit subscription required")
    result = subprocess.run(["az", *arguments, "--only-show-errors", "--output", "json"], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        text = result.stderr.strip()
        if any(token in text for token in ("NotFound", "not found", "could not be found", "does not exist", "MANIFEST_UNKNOWN",
                                            "manifest unknown", "NAME_UNKNOWN")):
            raise Absent(text[:300])
        raise RuntimeError(text[:800])
    return json.loads(result.stdout) if result.stdout.strip() else None


def sdk_read(function):
    try:
        return plain(function())
    except Exception as error:
        if not_found(error):
            raise Absent(f"{type(error).__name__} 404")
        raise


def candidates(manifest, kind):
    return [item for item in manifest["items"] if item["kind"] == kind and item["disposition"] == "delete-candidate"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--subscription", default="67255afe-8670-4401-a1b8-df6ca63a3516")
    parser.add_argument("--tenant", default="c79ab2bb-79cb-47f1-b4da-b6852fe45ff7")
    parser.add_argument("--endpoint", default="https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry")
    parser.add_argument("--resource-group", default="personal-llm")
    parser.add_argument("--account", default="han-primary-foundry-resource")
    parser.add_argument("--registry", default="agentcraftdev67255")
    parser.add_argument("--agent", action="append", help="Experiment-owned agent; all its sessions and versions are in scope")
    parser.add_argument("--run", help="oplog run id checked every 45 s into teardown/worker-oplog.jsonl")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--phase", action="append", help="Restrict to named phases (default all, in order)")
    parser.add_argument("--only-id", action="append", help="Restrict steps to these exact ids")
    args = parser.parse_args()
    args.manifest = args.manifest.resolve()

    raw = args.manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
        raise SystemExit("manifest digest mismatch; refusing")
    manifest = json.loads(raw)
    agents = args.agent or [item["id"] for item in candidates(manifest, "agent")]
    manifest_agents = {item["id"] for item in candidates(manifest, "agent")}
    if not set(agents) <= manifest_agents:
        raise SystemExit("agent outside manifest delete-candidates; refusing")
    OUT.mkdir(exist_ok=True)
    rec = Recorder(args)
    sub = ["--subscription", args.subscription]
    account = cli(["account", "show", *sub, "--query", "{id:id,tenantId:tenantId}"])
    if account["id"] != args.subscription or account["tenantId"] != args.tenant:
        raise SystemExit(f"subscription/tenant mismatch: {account}")
    phases = args.phase or ["nonterminal", "sessions", "responses", "jobs", "eval_runs", "evals", "versions", "agents",
                            "evaluators", "datasets", "blobs", "model_deployment", "acr_manifests", "acr_pull", "final"]
    rec.write("start", {"at": now(), "execute": args.execute, "manifest": str(args.manifest.relative_to(REPO)),
                        "manifest_sha256": args.manifest_sha256, "account": account, "agents": agents, "phases": phases})

    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with AzureCliCredential(tenant_id=args.tenant, process_timeout=30) as credential, \
            AIProjectClient(endpoint=args.endpoint, credential=credential, allow_preview=True, retry_total=0,
                            connection_timeout=15, read_timeout=60) as project, \
            project.get_openai_client(max_retries=0, timeout=60) as client:

        def run(name):
            rec.clock(force=True)
            print(f"== phase {name}", flush=True)
            return name in phases

        if run("nonterminal"):
            jobs = [plain(job) for job in project.beta.agents.list_optimization_jobs(limit=100)]
            owned = {item["id"] for item in candidates(manifest, "optimization_job")}
            rec.write("pre-optimization-jobs", jobs)
            for job in jobs:
                if job.get("status") not in TERMINAL and job["id"] in owned:
                    rec.step("optimization_job_cancel", job["id"], lambda j=job: sdk_read(lambda: project.beta.agents.get_optimization_job(j["id"])),
                             lambda s: None if s.get("status") not in TERMINAL else "already terminal",
                             lambda s, j=job: project.beta.agents.cancel_optimization_job(j["id"]))

        if run("sessions"):
            for agent in agents:
                try:
                    listed = [plain(s) for s in project.agents.list_sessions(agent, limit=100)]
                except Exception as error:
                    if not not_found(error):
                        raise
                    rec.finish({"kind": "hosted_session", "id": f"{agent}/*", "outcome": "already-absent",
                                "pre_read": f"parent agent 404: {str(error)[:200]}"})
                    continue
                rec.write(f"pre-sessions-{agent}", listed)
                for session in listed:
                    sid = session["agent_session_id"]

                    def delete_session(state, agent=agent, sid=sid):
                        try:
                            project.agents.delete_session(agent, sid)
                        except Exception as error:
                            if getattr(error, "status_code", None) not in (400, 409):
                                raise
                            project.agents.stop_session(agent, sid)
                            project.agents.delete_session(agent, sid)

                    rec.step("hosted_session", sid, lambda a=agent, s=sid: sdk_read(lambda: project.agents.get_session(a, s)),
                             lambda state, s=sid: None if state.get("agent_session_id") == s else "session identity mismatch",
                             delete_session, extra={"agent": agent})

        if run("responses"):
            by_agent = {}
            for item in candidates(manifest, "stored_response"):
                owner = item["details"]["agent"]
                if owner not in agents:
                    raise SystemExit(f"response owner outside scope: {item['id']}")
                by_agent.setdefault(owner, []).append(item["id"])
            for owner, identifiers in by_agent.items():
                with project.get_openai_client(agent_name=owner, max_retries=0, timeout=60) as scoped:
                    for rid in identifiers:
                        def delete_response(state, rid=rid, scoped=scoped):
                            if state.get("status") not in TERMINAL:
                                scoped.responses.cancel(rid)
                            raw = scoped.responses.with_raw_response.delete(rid)
                            return {"http": raw.status_code, "body": raw.text[:500]}

                        # openai client surfaces this endpoint's 404 as APIConnectionError; read raw HTTP instead.
                        def read_response(rid=rid, scoped=scoped):
                            import httpx
                            reply = httpx.get(f"{scoped.base_url}responses/{rid}", params=dict(scoped._custom_query or {}), timeout=60,
                                              headers={"Authorization": "Bearer " + credential.get_token("https://ai.azure.com/.default").token})
                            if reply.status_code == 404:
                                raise Absent("HTTP 404 " + reply.json().get("error", {}).get("message", "")[:160])
                            reply.raise_for_status()
                            return {k: v for k, v in reply.json().items() if k in ("id", "status", "created_at", "model")}

                        rec.step("stored_response", rid, read_response,
                                 lambda state, rid=rid: None if state.get("id") == rid else "response identity mismatch",
                                 delete_response, extra={"agent": owner})

        eval_ids = [item["id"] for item in candidates(manifest, "evaluation")]

        def eval_runs_snapshot(label):
            snapshot = {}
            for eid in eval_ids:
                try:
                    snapshot[eid] = [{"id": r.id, "status": r.status} for r in client.evals.runs.list(eval_id=eid, limit=100)]
                except Exception as error:
                    snapshot[eid] = f"{type(error).__name__}: {str(error)[:200]}"
            rec.write(label, snapshot)
            return snapshot

        if run("jobs"):
            eval_runs_snapshot("pre-jobs-eval-runs")
            for item in candidates(manifest, "optimization_job"):
                jid = item["id"]
                rec.step("optimization_job", jid, lambda j=jid: sdk_read(lambda: project.beta.agents.get_optimization_job(j)),
                         lambda s, j=jid: "job identity mismatch" if s.get("id") != j else
                         (f"nonterminal status {s.get('status')}" if s.get("status") not in TERMINAL else None),
                         lambda s, j=jid: project.beta.agents.delete_optimization_job(j),
                         extra={"cascade": [c["id"] for c in candidates(manifest, "optimization_candidate") if c["parent"].endswith(jid)]})
            eval_runs_snapshot("post-jobs-eval-runs")

        if run("eval_runs"):
            for item in candidates(manifest, "evaluation_run"):
                rid, eid = item["id"], item["details"]["eval_id"]

                def delete_run(state, rid=rid, eid=eid):
                    if state.get("status") not in TERMINAL:
                        client.evals.runs.cancel(rid, eval_id=eid)
                    client.evals.runs.delete(rid, eval_id=eid)

                rec.step("evaluation_run", rid, lambda rid=rid, eid=eid: {k: v for k, v in sdk_read(
                    lambda: client.evals.runs.retrieve(rid, eval_id=eid)).items() if k in ("id", "eval_id", "status", "name", "created_at")},
                    lambda s, rid=rid, eid=eid: None if s.get("id") == rid and s.get("eval_id") in (eid, None) else "run identity mismatch",
                    delete_run, extra={"eval_id": eid})

        if run("evals"):
            owned_runs = {item["id"] for item in candidates(manifest, "evaluation_run")}
            for eid in eval_ids:
                def read_eval(eid=eid):
                    state = {k: v for k, v in sdk_read(lambda: client.evals.retrieve(eid)).items() if k in ("id", "name", "created_at")}
                    state["remaining_runs"] = [r.id for r in client.evals.runs.list(eval_id=eid, limit=100)]
                    return state

                def check_eval(s, eid=eid):
                    if s.get("id") != eid:
                        return "eval identity mismatch"
                    protected = [r for r in s["remaining_runs"] if r not in owned_runs]
                    return f"protected children remain: {len(protected)} unknown-provenance runs; no cascading delete" if protected else None

                rec.step("evaluation", eid, read_eval, check_eval, lambda s, eid=eid: client.evals.delete(eid))

        if run("versions"):
            for agent in agents:
                try:
                    listed = [plain(v) for v in project.agents.list_versions(agent, limit=100, include_drafts=True)]
                except Exception as error:
                    if not_found(error):
                        continue
                    raise
                rec.write(f"pre-versions-{agent}", listed)
                for version in listed:
                    number = version["version"]
                    rec.step("agent_version", f"{agent}:{number}",
                             lambda a=agent, n=number: {k: v for k, v in sdk_read(lambda: project.agents.get_version(a, n)).items()
                                                        if k in ("id", "name", "version", "status", "draft", "created_at")},
                             lambda s, a=agent, n=number: None if s.get("name") == a and str(s.get("version")) == str(n) else "version identity mismatch",
                             lambda s, a=agent, n=number: project.agents.delete_version(a, n), extra={"agent": agent})

        principals = {}
        if run("agents"):
            for agent in agents:
                for path in sorted(ROOT.glob(f"*-versions-{agent}.json"))[-1:]:
                    for version in json.loads(path.read_text()).get("result", []):
                        for key in ("instance_identity", "blueprint"):
                            principal = (version.get(key) or {}).get("principal_id")
                            if principal:
                                principals[principal] = agent
            rec.write("pre-agent-principals", {p: _sp(p) | {"agent": a} for p, a in principals.items()})
            for agent in agents:
                rec.step("agent", agent, lambda a=agent: {k: v for k, v in sdk_read(lambda: project.agents.get(a)).items() if k in ("id", "name", "state")},
                         lambda s, a=agent: None if s.get("name") == a else "agent identity mismatch",
                         lambda s, a=agent: project.agents.delete(a, force=False))
            rec.write("post-agent-principals", {p: _sp(p) | {"agent": a} for p, a in principals.items()})

        if run("evaluators"):
            for item in candidates(manifest, "evaluator_version"):
                name, version = item["details"]["name"], item["details"]["version"]
                rec.step("evaluator_version", item["id"],
                         lambda n=name, v=version: {k: val for k, val in sdk_read(lambda: project.beta.evaluators.get_version(n, v)).items()
                                                    if k in ("id", "name", "version", "created_by", "created_at")},
                         lambda s, n=name, v=version: None if s.get("name") == n and str(s.get("version")) == v else "evaluator identity mismatch",
                         lambda s, n=name, v=version: project.beta.evaluators.delete_version(n, v))

        if run("datasets"):
            for item in candidates(manifest, "dataset_version"):
                name, version = item["details"]["name"], item["details"]["version"]
                rec.step("dataset_version", item["id"],
                         lambda n=name, v=version: {k: val for k, val in sdk_read(lambda: project.datasets.get(n, v)).items()
                                                    if k in ("id", "name", "version", "data_uri", "dataUri", "created_by", "createdBy")},
                         lambda s, item=item: None if s.get("id") == item["id"] and s.get("dataUri", s.get("data_uri")) == item["details"]["data_uri"] else "dataset identity mismatch",
                         lambda s, n=name, v=version: project.datasets.delete(n, v))

        if run("blobs"):
            for item in candidates(manifest, "blob"):
                host, _, path = item["id"].removeprefix("https://").partition("/")
                container, _, blob = path.partition("/")
                target = ["--account-name", host.split(".")[0], "--container-name", container, "--name", blob, "--auth-mode", "login", *sub]
                rec.step("blob", item["id"], lambda t=target: cli(["storage", "blob", "show", *t, "--query", "{name:name,snapshot:snapshot,versionId:versionId}"], 60),
                         lambda s, blob=blob: None if s and s.get("name") == blob else "blob identity mismatch",
                         lambda s, t=target: cli(["storage", "blob", "delete", *t], 60))

        if run("model_deployment"):
            for item in candidates(manifest, "model_deployment"):
                name = item["details"]["name"]
                target = ["--name", args.account, "--resource-group", args.resource_group, "--deployment-name", name, *sub]
                rec.step("model_deployment", item["id"], lambda t=target: cli(["cognitiveservices", "account", "deployment", "show", *t]),
                         lambda s, item=item: None if s.get("id") == item["id"] and s["properties"]["model"]["name"] == item["details"]["model"]["name"]
                         and s["properties"]["model"]["version"] == item["details"]["model"]["version"] else "deployment identity/model mismatch",
                         lambda s, t=target: cli(["cognitiveservices", "account", "deployment", "delete", *t], 600), polls=12, interval=15)

        if run("acr_manifests"):
            owned = {item["id"].split("/", 1)[1] for item in candidates(manifest, "acr_manifest")}
            for repo_item in candidates(manifest, "acr_repository"):
                repository = repo_item["id"].split("/", 1)[1]
                try:
                    live = cli(["acr", "manifest", "list-metadata", "--registry", args.registry, "--name", repository, *sub])
                except Absent:
                    live = []
                rec.write(f"pre-acr-{repository}", live)
                for entry in live:
                    ref = f"{repository}@{entry['digest']}"
                    target = ["--registry", args.registry, "--name", ref, *sub]
                    rec.step("acr_manifest", f"{args.registry}.azurecr.io/{ref}",
                             lambda t=target: {k: v for k, v in cli(["acr", "manifest", "show-metadata", *t]).items() if k in ("digest", "tags", "createdTime")},
                             lambda s, ref=ref: None if ref in owned else "digest not a manifest delete-candidate",
                             lambda s, t=target: cli(["acr", "manifest", "delete", *t, "--yes"]), extra={"tags": entry.get("tags")})
                try:
                    remaining = cli(["acr", "manifest", "list-metadata", "--registry", args.registry, "--name", repository, *sub])
                except Absent as absent:
                    remaining = f"absent: {absent}"
                rec.write(f"post-acr-{repository}", remaining)

        if run("acr_pull"):
            for item in candidates(manifest, "role_assignment"):
                scope, name = item["id"].rsplit("/providers/Microsoft.Authorization/roleAssignments/", 1)

                def read_role(scope=scope, name=name):
                    found = cli(["role", "assignment", "list", "--scope", scope, *sub, "--query", f"[?name=='{name}']"])
                    if not found:
                        raise Absent("role assignment not listed at scope")
                    return found[0]

                def check_role(state, item=item):
                    if state.get("id") != item["id"] or state.get("principalId") != item["details"]["principalId"] \
                            or not state.get("roleDefinitionId", "").endswith(ACR_PULL):
                        return "role assignment identity/principal/role mismatch"
                    remaining = []
                    for agent in agents:
                        try:
                            project.agents.get(agent)
                            remaining.append(agent)
                        except Exception as error:
                            if not not_found(error):
                                remaining.append(f"{agent}: {type(error).__name__}")
                    return f"registry consumers remain: {remaining}" if remaining else None

                rec.step("role_assignment", item["id"], read_role, check_role,
                         lambda s: cli(["role", "assignment", "delete", "--ids", s["id"], *sub]))

        if run("final"):
            final = {"agents": [a.name for a in project.agents.list(limit=100)],
                     "optimization_jobs_nonterminal": [j.id for j in project.beta.agents.list_optimization_jobs(limit=100)
                                                        if plain(j).get("status") not in TERMINAL],
                     "model_deployments": [d["name"] for d in cli(["cognitiveservices", "account", "deployment", "list", "--name", args.account,
                                                                   "--resource-group", args.resource_group, *sub])],
                     "acr_repositories": cli(["acr", "repository", "list", "--name", args.registry, *sub])}
            rec.write("final-state", final)
            print(json.dumps(final), flush=True)

    counts = {}
    for record in rec.outcomes:
        key = f"{record['kind']}:{record['outcome']}"
        counts[key] = counts.get(key, 0) + 1
    summary = rec.write("summary", {"at": now(), "execute": args.execute, "counts": counts, "outcomes": rec.outcomes,
                                    "ledger": str(rec.ledger.relative_to(REPO)) if rec.ledger.exists() else None})
    print(json.dumps({"summary": str(summary.relative_to(REPO)), "counts": counts}, indent=1))


def _sp(principal):
    result = subprocess.run(["az", "ad", "sp", "show", "--id", principal, "--query", "{id:id,displayName:displayName,appId:appId}",
                             "--only-show-errors", "--output", "json"], capture_output=True, text=True, timeout=60)
    return {"exit_code": result.returncode, "result": json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None,
            "stderr": result.stderr.strip()[:300]}


if __name__ == "__main__":
    main()
