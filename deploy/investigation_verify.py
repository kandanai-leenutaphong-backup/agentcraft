from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import uuid
from urllib.parse import urlencode


def restart_probe(config, acceptance_path, cli):
    import httpx
    from signed_dev_access import RequestSigner, load_private_key, sign_headers

    accepted = json.loads(acceptance_path.read_text())
    if accepted.get("status") != "external-verified":
        raise ValueError("successful_external_receipt_required")
    origin = config["runtime"]["origin"]
    key = load_private_key(str(Path.home() / ".local/state/agentcraft/rg-agentcraft-dev/caller.ed25519"))
    signer = RequestSigner(key, origin=origin)
    agent_path = "/api/cyber/agent-editor/agents/" + accepted["acceptance"]["agent_id"]
    before = signer.request("GET", agent_path)
    assert before.status == 200
    profile_path = accepted["acceptance"].get("profile", {}).get("path")
    profile_before = signer.request("GET", profile_path) if profile_path else None
    if profile_before is not None:
        assert profile_before.status == 200
    headers = sign_headers(key, "GET", "/api/whoami")
    common = ("--subscription", config["subscription_id"], "--resource-group", config["resource_group"],
              "--name", config["names"]["app"])
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        assert client.get(origin + "/api/whoami", headers=headers).status_code == 200
        revision = cli("containerapp", "show", *common, "--query", "properties.latestReadyRevisionName")
        replica_args = ("--subscription", config["subscription_id"], "--resource-group", config["resource_group"],
                "--name", config["names"]["app"], "--revision", revision, "--query", "[].name")
        before_replicas = cli("containerapp", "replica", "list", *replica_args)
        assert isinstance(before_replicas, list) and before_replicas
        cli("containerapp", "revision", "restart", "--subscription", config["subscription_id"],
            "--resource-group", config["resource_group"], "--revision", revision)
        deadline = __import__('time').monotonic() + 180
        ready = False
        attempts = 0
        while __import__('time').monotonic() < deadline and attempts < 120:
            attempts += 1
            after_replicas = cli("containerapp", "replica", "list", *replica_args)
            if not after_replicas or set(before_replicas).intersection(after_replicas):
                continue
            try:
                reply = signer.request("GET", "/api/whoami", timeout_seconds=15)
                if reply.status == 200:
                    ready = True
                    break
            except Exception:
                continue
        assert ready
        assert client.get(origin + "/api/whoami", headers=headers).status_code == 401
    after = signer.request("GET", agent_path)
    assert after.status == 200 and json.loads(before.body) == json.loads(after.body)
    if profile_before is not None:
        profile_after = signer.request("GET", profile_path)
        assert profile_after.status == 200 and json.loads(profile_before.body) == json.loads(profile_after.body)
    return {"revision": revision, "readiness_attempts": attempts, "replay_after_restart": 401,
            "before_replicas": before_replicas, "after_replicas": after_replicas,
            "profile_unchanged": profile_before is not None, "profile_path": profile_path,
            "authored_state_unchanged": True, "agent_id": accepted["acceptance"]["agent_id"],
            "state_sha256": hashlib.sha256(after.body).hexdigest()}


def browser_probe(config_path, evidence):
    from playwright.sync_api import sync_playwright
    from signed_dev_access import RequestSigner, load_private_key, new_piloted_context
    from investigation import load_config

    config = load_config(config_path)
    origin = config["runtime"]["origin"]
    key = load_private_key(str(Path.home() / ".local/state/agentcraft/rg-agentcraft-dev/caller.ed25519"))
    signer = RequestSigner(key, origin=origin, allow_mutations=True)
    browsers = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux*/chrome"))
    if not browsers:
        raise RuntimeError("existing_chromium_missing")
    report = {"persona": "Analyst tracing public emulation alarm to event/entity provenance; knows Windows events, not internal IDs",
              "checks": [], "screenshots": [], "browser_errors": [], "human_signin": "not_verified"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(browsers[-1]))
        try:
            with new_piloted_context(browser, signer=signer) as pilot:
                page = pilot.context.new_page()
                page.set_default_timeout(30000)
                page.on("pageerror", lambda error: report["browser_errors"].append(type(error).__name__))
                for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(origin)
                    cases = page.get_by_role("region", name="Public investigation", exact=True)
                    cases.get_by_role("button", name="Attack Range rundll32 DLL in Temp emulation", exact=True).click()
                    cases.get_by_role("button", name="rundll32-temp-dll-v1", exact=True).click()
                    cases.get_by_role("button", name=__import__('re').compile(r"^Event 1 ")).click()
                    reference = cases.get_by_test_id("public-event-id").inner_text()
                    assert reference.startswith("event://scenario-")
                    for role in ("host", "user", "process"):
                        cases.get_by_role("button", name=f"Open {role} graph", exact=True).click()
                        cases.locator(".graph-stage .graph-node").first.wait_for()
                        detail = cases.locator(".graph-detail")
                        assert "6bc794b7f65562148c872fde1e7412ab3c173f4c" in detail.inner_text()
                        cases.locator(".graph-stage").scroll_into_view_if_needed()
                        geometry = cases.evaluate("element => ({width:element.getBoundingClientRect().width,scroll:element.scrollWidth,client:element.clientWidth,page:document.documentElement.clientWidth,pageScroll:document.documentElement.scrollWidth,nodes:element.querySelectorAll('.graph-node').length})")
                        assert geometry["width"] > 0 and geometry["nodes"] > 1
                        assert geometry["scroll"] <= geometry["client"] + 1 and geometry["pageScroll"] <= geometry["page"] + 1
                        path = evidence / f"browser-{name}-{role}-{uuid.uuid4().hex}.png"
                        page.screenshot(path=str(path), full_page=False)
                        report["screenshots"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "viewport": [width, height]})
                        report["checks"].append({"viewport": name, "role": role, "geometry": geometry})
                        detail.get_by_role("button", name=reference, exact=True).click()
                        assert cases.get_by_test_id("public-event-id").inner_text() == reference
                    cases.get_by_role("button", name="Source provenance", exact=True).click()
                    source = cases.get_by_test_id("public-source")
                    assert "5ac4747551f733d673cd6828a55732b7b542d3552698325cbdac2df2a69aa62f" in source.inner_text()
                    source.scroll_into_view_if_needed()
                    path = evidence / f"browser-{name}-source-{uuid.uuid4().hex}.png"
                    page.screenshot(path=str(path), full_page=False)
                    report["screenshots"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "viewport": [width, height]})
                    cases.get_by_role("button", name="Refresh cases", exact=True).focus()
                    page.keyboard.press("Tab")
                    focused = page.evaluate("() => ({tag:document.activeElement.tagName,outline:getComputedStyle(document.activeElement).outlineStyle})")
                    assert focused["tag"] == "BUTTON" and focused["outline"] != "none"
                    report["checks"].append({"viewport": name, "source_readback": True, "keyboard": focused})
                assert not report["browser_errors"] and pilot.failure_count == 0
                report["signer_failures"] = pilot.failure_count
        finally:
            browser.close()
    return report


def external_probe(config_path, *, model=False, profile_write=False, progress=lambda value: None):
    import httpx
    from signed_dev_access import RequestSigner, load_private_key, sign_headers
    from investigation import load_config
    from investigation_loader import load_package, PACKAGE_SHA256

    config = load_config(config_path)
    origin = config["runtime"]["origin"]
    key = load_private_key(str(Path.home() / ".local/state/agentcraft/rg-agentcraft-dev/caller.ed25519"))
    signer = RequestSigner(key, origin=origin, allow_mutations=True)
    package = config_path.resolve().parents[2] / "template_apps/investigation_app/deploy/data/public-investigation/packages" / PACKAGE_SHA256
    manifest, documents = load_package(package)
    checks = []

    def request(method, path, payload=None, expected=200):
        body = json.dumps(payload).encode() if payload is not None else b""
        reply = signer.request(method, path, body=body, content_type="application/json", timeout_seconds=300,
                               max_response_bytes=8_000_000)
        checks.append({"method": method, "path": path.split("?")[0], "status": reply.status,
                       "bytes": len(reply.body), "sha256": hashlib.sha256(reply.body).hexdigest()})
        progress(checks[-1])
        if reply.status != expected:
            raise RuntimeError("external_status_" + str(reply.status))
        return json.loads(reply.body) if reply.body else None

    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for path in ("/", "/api/whoami", "/assets/unknown", "/unknown"):
            reply = client.get(origin + path)
            assert reply.status_code == 401, (path, reply.status_code)
            checks.append({"check": "anonymous", "path": path, "status": reply.status_code})
        headers = sign_headers(key, "GET", "/api/whoami")
        assert client.get(origin + "/api/whoami", headers=headers).status_code == 200
        assert client.get(origin + "/api/whoami", headers=headers).status_code == 401
        altered = sign_headers(key, "GET", "/api/whoami")
        altered["X-Request-Context"] = "foreign"
        assert client.get(origin + "/api/whoami", headers=altered).status_code == 401
        foreign = RequestSigner(key, origin=origin, context_slug="foreign", allow_mutations=True)
        assert foreign.request("GET", "/api/whoami").status == 403
        checks.append({"check": "replay-tamper-foreign-owner", "statuses": [401, 401, 403]})
        progress(checks[-1])
    identity = request("GET", "/api/whoami")
    assert identity["id"] == f"devkey:{config['runtime']['fingerprint']}:default"
    profile = request("GET", "/api/cyber/public/profile")
    assert profile["partition"] == manifest["partition"]
    partition = {"partition": manifest["partition"]}
    cases = request("GET", "/api/cyber/public/cases?" + urlencode(partition))
    case = next(item for item in documents["cosmos"] if item["kind"] == "incident")
    assert case["id"] in json.dumps(cases)
    alarms = request("GET", "/api/cyber/public/alarms?" + urlencode({**partition, "case_id": case["id"]}))
    alarm = next(item for item in documents["cosmos"] if item["kind"] == "alarm")
    assert alarm["id"] in json.dumps(alarms)
    for event in (item for item in documents["cosmos"] if item["kind"] == "event"):
        evidence = request("GET", "/api/cyber/public/evidence?" + urlencode({**partition, "resource_id": event["resource_id"]}))
        assert event["source"]["raw_sha256"] in json.dumps(evidence)
        for role in ("host", "user", "process"):
            graph = request("GET", "/api/cyber/graph/node?" + urlencode({"id": event["entity_refs"][role]}))
            assert event["entity_refs"][role] in json.dumps(graph)
    knowledge = request("GET", "/api/cyber/knowledge/type/T1218.011")
    assert "T1218.011" in json.dumps(knowledge)
    request("GET", "/api/cyber/public/cases?partition=foreign", expected=422)
    catalogue = request("GET", "/api/cyber/agent-editor")
    builtin = catalogue["agents"][0]
    original = request("GET", "/api/cyber/agent-editor/agents/" + builtin["id"])
    draft = {key: original[key] for key in ("name", "model", "system_prompt", "instruction_files", "tool_ids")}
    draft.update(name="Deployment verification", version_name="live-baseline", base_version=0, expected_latest_version=0)
    created = request("POST", "/api/cyber/agent-editor/agents", draft, expected=201)
    agent_id = created["agent_id"]
    request("GET", "/api/cyber/agent-editor/agents/" + agent_id)
    updated = {**draft, "base_version": 1, "expected_latest_version": 1, "version_name": "live-cas"}
    request("POST", f"/api/cyber/agent-editor/agents/{agent_id}/versions", updated, expected=201)
    request("POST", f"/api/cyber/agent-editor/agents/{agent_id}/versions", updated, expected=409)
    model_result = {"status": "not_run", "cost": "unknown"}
    profile_result = {"status": "not_run"}
    if model:
        session = request("POST", "/api/sessions", {})
        prompt = "Use list_public_cases, then list_public_alarms and get_public_evidence for one case. Report exact source references and state that this is public emulation, not malicious ground truth. Do not update profiles or definitions."
        profile_id = "deployment-" + uuid.uuid4().hex[:16]
        if profile_write:
            event = next(item for item in documents["cosmos"] if item["kind"] == "event")
            prompt = ("Deployment acceptance with real public emulation evidence, not a malicious-person assertion. "
                "First call get_public_evidence for partition " + manifest["partition"] + " and resource_ids " + json.dumps([event["resource_id"]]) +
                ". Then call update_suspect_profile once with profile_id " + profile_id + ", expected_revision 0, "
                'identity {"account":"deployment-test-public-emulation","display_name":"Deployment verification only"}, '
                "activity containing one entry with timestamp " + event["timestamp"] +
                ', summary "Public emulation process creation, deployment verification only", evidence_ids ' + json.dumps([event["resource_id"]]) +
                ". Preserve returned evidence provenance. Do not infer malicious intent. Report the actual save outcome.")
        body = json.dumps({"message": prompt}).encode()
        reply = signer.request("POST", "/api/chat/" + session["session_id"], body=body,
            content_type="application/json", timeout_seconds=300, max_response_bytes=8_000_000)
        assert reply.status == 200
        retained = request("GET", f"/api/sessions/{session['session_id']}/result")
        model_result = {"status": retained.get("status", retained.get("result", {}).get("status", "unknown")),
                        "session_id": session["session_id"], "response_sha256": hashlib.sha256(reply.body).hexdigest(),
                        "native_tool_event_count": reply.body.count(b"event: tool_result"), "cost": "unknown"}
        assert model_result["native_tool_event_count"] > 0
        assert model_result["status"] == "completed"
        if profile_write:
            path = "/api/cyber/suspect-profiles/" + profile_id
            saved = request("GET", path)
            assert saved["revision"] == 1 and saved["citations"]
            assert event["resource_id"] in json.dumps(saved["citations"])
            done = [json.loads(block.split("data: ", 1)[1]) for block in reply.body.decode().split("\n\n")
                if block.startswith("event: done\n")]
            assert done and done[-1].get("run_id")
            payload = {key: saved[key] for key in ("profile_id", "identity", "activity")}
            payload.update(expected_revision=0, evidence_run_id=done[-1]["run_id"])
            request("PUT", path, payload, expected=409)
            payload["expected_revision"] = 1
            changed = request("PUT", path, payload)
            assert changed["revision"] == 2
            assert request("GET", path) == changed
            profile_result = {"status": "verified", "path": path, "revision": 2, "native_write": True,
                      "http_same_rule": True, "stale_refusal": 409, "citations_verified": True}
    return {"checks": checks, "owner": identity["id"], "agent_id": agent_id, "model": model_result,
            "profile": profile_result, "package_sha256": PACKAGE_SHA256, "human_signin": "not_verified"}


def state_probe():
    from agentconfig import AgentDraft, AgentStoreError, AgentVersionStore, AssignAgent, SaveAgent
    from azure.identity.aio import DefaultAzureCredential
    from app.cybereye.backend.agents.cosmos_state import CosmosOwnerDocuments

    owner = "deployment-probe:" + uuid.uuid4().hex
    def storage():
        return CosmosOwnerDocuments(endpoint=os.environ["CYBEREYE_COSMOS_ENDPOINT"],
            database=os.environ["CYBEREYE_COSMOS_DATABASE"], container=os.environ["CYBEREYE_STATE_CONTAINER"],
            namespace="agents", credential_factory=lambda: DefaultAzureCredential(exclude_interactive_browser_credential=True))
    def store(backend):
        return AgentVersionStore(Path("/state/probe"), builtin_id="probe_builtin",
            builtin=AgentDraft(name="Probe", model="probe", system_prompt="Deployment verification only"),
            validate=lambda draft: None, validate_assignment=lambda draft: None, storage=backend)
    backend = storage()
    try:
        first = store(backend)
        request = SaveAgent(name="Probe", model="probe", system_prompt="Deployment verification only")
        saved = first.save(owner, request)
        assigned = first.assign(owner, AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0))
    finally:
        backend.close()
    left, right = storage(), storage()
    try:
        first, second = store(left), store(right)
        assert first.get(owner, saved.agent_id) == saved
        assert first.assignment(owner) == assigned
        try:
            second.get(owner + ":foreign", saved.agent_id)
        except AgentStoreError as error:
            assert error.status == 404
        else:
            raise AssertionError("foreign_owner_accepted")
        def save(current):
            try:
                return current.save(owner, request.model_copy(update={"base_version": 1, "expected_latest_version": 1}), saved.agent_id).version
            except AgentStoreError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, (first, second)))
        assert sorted(results) == [2, 409]
        assert second.get(owner, saved.agent_id, 1) == saved
        assert second.assignment(owner) == assigned
        return {"restart_instances": True, "owner_refusal": True, "concurrent_results": sorted(results),
                "immutable_version": True, "assignment_pinned": True,
                "retained_probe_owner_sha256": hashlib.sha256(owner.encode()).hexdigest()}
    finally:
        left.close()
        right.close()


async def table_probe():
    from entra_auth import AzureTableRecordStore, SessionService, new_flow
    from signed_dev_access import AzureTableReplayLedger

    endpoint = os.environ["AUTH_SESSION_TABLE_ENDPOINT"]
    table = os.environ["AUTH_SESSION_TABLE_NAME"]
    stores = [AzureTableRecordStore(endpoint=endpoint, table_name=table, partition_key=partition)
              for partition in ("session", "flow", "session", "flow")]
    services = [SessionService(store=stores[index], flow_store=stores[index + 1], max_lifetime=timedelta(minutes=5))
                for index in (0, 2)]
    ledgers = [AzureTableReplayLedger(endpoint=os.environ["DEV_REPLAY_TABLE_ENDPOINT"],
               table_name=os.environ["DEV_REPLAY_TABLE_NAME"]) for _ in range(2)]
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    try:
        flow = new_flow()
        await services[0].start_flow(flow, ttl=timedelta(minutes=5))
        claims = await asyncio.gather(*(service.claim_flow(flow.flow_id, flow.state) for service in services))
        assert sum(claim is not None for claim in claims) == 1
        assert await services[1].claim_flow(flow.flow_id, flow.state) is None
        identifier, _ = await services[0].create({"principal_id": "deployment-probe-not-a-user"}, token_expires_at=expires)
        assert await services[1].resolve(identifier) == {"principal_id": "deployment-probe-not-a-user"}
        await services[1].revoke(identifier)
        assert await services[0].resolve(identifier) is None
        replay = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        claimed = await asyncio.gather(*(ledger.claim(replay, expires) for ledger in ledgers))
        assert sorted(claimed) == [False, True]
        await ledgers[0].close()
        recreated = AzureTableReplayLedger(endpoint=os.environ["DEV_REPLAY_TABLE_ENDPOINT"], table_name=os.environ["DEV_REPLAY_TABLE_NAME"])
        try:
            assert await recreated.claim(replay, expires) is False
        finally:
            await recreated.close()
        return {"flow_atomic_consume": True, "session_cross_instance": True, "revocation": True,
                "replay_atomic": True, "replay_recreated_client_refusal": True,
                "human_signin": "not_verified", "replay_row": "retained until expiry; no early purge"}
    finally:
        for item in [*stores, *ledgers]:
            await item.close()


def private_probe():
    import urllib.error
    import urllib.request

    paths = ("/", "/api/health", "/assets/unknown", "/unknown")
    statuses = {}
    for path in paths:
        try:
            response = urllib.request.urlopen("http://127.0.0.1:8080" + path, timeout=15)
            status = response.status
            response.close()
        except urllib.error.HTTPError as error:
            status = error.code
        assert status == 401, (path, status)
        statuses[path] = status
    print(json.dumps({"status": "verified", "stage": "private-anonymous", "statuses": statuses}), flush=True)
    state = state_probe()
    print(json.dumps({"status": "verified", "stage": "cosmos-state", "result": state}), flush=True)
    tables = asyncio.run(table_probe())
    return {"anonymous": statuses, "state": state, "tables": tables}


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("private", "external", "browser"))
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args()
    try:
        result = (private_probe() if args.action == "private" else browser_probe(args.config, args.evidence)
              if args.action == "browser" else external_probe(args.config, model=args.model))
        print(json.dumps({"status": "verified", "observed_at": datetime.now(timezone.utc).isoformat(), **result}), flush=True)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "payload": "omitted"}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()