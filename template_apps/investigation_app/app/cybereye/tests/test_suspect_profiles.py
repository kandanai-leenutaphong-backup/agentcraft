from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from pydantic import ValidationError

from app.cybereye.backend.agents.profiles import ProfileError, SuspectProfiles, UpdateSuspectProfile
from app.cybereye.backend.agents.tools.diagnosis import EvidenceLedger
from app.cybereye.backend.security.principal import Principal


OWNER = Principal(id="entra:tenant:owner", issuer="entra")
OTHER = Principal(id="entra:tenant:other", issuer="entra")


def update_payload(**changes):
    return {"profile_id": "suspect", "expected_revision": 0,
            "identity": {"account": "synthetic-analyst", "display_name": "Synthetic analyst"},
            "activity": [{"timestamp": "2026-08-13T02:30:00Z", "summary": "SYNTHETIC credential use",
                          "evidence_ids": ["event-1"]}], **changes}


def evidence():
    ledger = EvidenceLedger()
    ledger.note_call("call-1", {"query": "EventsUnified | take 1"})
    ledger.record("call-1", "query_events_kql", "Events", {"rows": [
        {"resource_id": "event-1", "source_time": "2026-08-13T02:30:00Z"}]})
    return ledger


def test_persist_owner_revision_and_provenance(tmp_path):
    service = SuspectProfiles(tmp_path / "profiles.sqlite3")
    update = UpdateSuspectProfile(**update_payload())
    saved = service.update(OWNER, update, evidence())
    assert saved.revision == 1
    assert saved.citations[0].retrieval.retrieval_id == "call-1"
    assert SuspectProfiles(service.path).get(OWNER, "suspect") == saved
    assert service.list(OTHER) == []
    with pytest.raises(ProfileError, match="profile_not_found"):
        service.get(OTHER, "suspect")
    with pytest.raises(ProfileError, match="stale_profile_revision"):
        service.update(OTHER, update.model_copy(update={"expected_revision": 1}), evidence())
    with pytest.raises(ProfileError, match="stale_profile_revision"):
        service.update(OWNER, update, evidence())
    assert service.get(OWNER, "suspect") == saved


def test_unsupported_and_unauthorized_never_write(tmp_path):
    service = SuspectProfiles(tmp_path / "profiles.sqlite3")
    update = UpdateSuspectProfile(**update_payload())
    with pytest.raises(ProfileError, match="unsupported_profile_citations"):
        service.update(OWNER, update, EvidenceLedger())
    with pytest.raises(ProfileError, match="profile_forbidden"):
        service.update(Principal(id="untrusted"), update, evidence())
    advisory = EvidenceLedger()
    advisory.record("advisory", "search_mitre_attack", "Knowledge", {
        "category": "mitre_attack", "rows": [{"doc_id": "event-1"}]})
    with pytest.raises(ProfileError, match="profile_activity_requires_telemetry"):
        service.update(OWNER, update, advisory)
    assert service.list(OWNER) == []


@pytest.mark.parametrize("changes", [
    {"expected_revision": -1}, {"expected_revision": True}, {"profile_id": "../escape"},
    {"identity": {"account": " ", "display_name": "name"}}, {"activity": []},
    {"activity": [{"timestamp": "2026-08-13", "summary": "test", "evidence_ids": ["event-1"]}]},
    {"owner": OTHER.id},
])
def test_invalid_fields(changes):
    with pytest.raises(ValidationError):
        UpdateSuspectProfile(**update_payload(**changes))


def test_concurrent_compare_and_swap(tmp_path):
    service = SuspectProfiles(tmp_path / "profiles.sqlite3")
    update = UpdateSuspectProfile(**update_payload())

    def save():
        try:
            return service.update(OWNER, update, evidence()).revision
        except ProfileError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert sorted(map(str, results)) == ["1", "stale_profile_revision"]


@pytest.mark.asyncio
async def test_native_profile_tool_and_api_share_owner_evidence_and_revision(monkeypatch, tmp_path):
    import _auth_support
    from azdata import HttpResponse
    from test_chat_sessions import frames
    from test_native_agent import completion, native_asgi_support

    async with native_asgi_support(monkeypatch, tmp_path) as fixture:
        client = fixture.client
        profile_path = "/api/cyber/suspect-profiles/suspect"
        session = (await client.post("/api/sessions")).json()["session_id"]
        fixture.data_replies.append(HttpResponse(200, [
            {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult",
             "TableName": "PrimaryResult", "Columns": [
                 {"ColumnName": "resource_id", "ColumnType": "string"},
                 {"ColumnName": "source_time", "ColumnType": "datetime"}],
             "Rows": [["event-1", "2026-08-13T02:30:00Z"]]},
            {"FrameType": "DataSetCompletion", "HasErrors": False}]))

        def tool_reply(name, arguments):
            return completion([({"role": "assistant", "tool_calls": [{"index": 0, "id": name,
                "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}, None),
                ({}, "tool_calls")])

        fixture.replies.extend([
            tool_reply("get_suspect_profile", {"profile_id": "suspect"}),
            tool_reply("query_events_kql", {"query": "EventsUnified | project resource_id, source_time", "max_rows": 1}),
            tool_reply("update_suspect_profile", update_payload()),
            completion([({"role": "assistant", "content": "SYNTHETIC profile saved."}, None), ({}, "stop")]),
        ])
        events = frames((await client.post(f"/api/chat/{session}", json={"message": "Create SYNTHETIC profile"})).text)
        assert events[-1][0] == "done", events
        assert events[-1][1]["status"] == "completed", events
        result = next(data["result"] for name, data in events
                      if name == "tool_result" and data["name"] == "update_suspect_profile")
        assert result["profile"]["revision"] == 1, events
        response = await client.get(profile_path)
        saved = response.json()
        assert saved == result["profile"]
        assert response.headers["cache-control"] == "no-store, private"
        assert SuspectProfiles(fixture.app.state.profiles.path).get(_auth_support.DEFAULT, "suspect").revision == 1
        run_id = events[-1][1]["run_id"]
        payload = {**update_payload(expected_revision=1), "evidence_run_id": run_id}
        for changes, code in [({"expected_revision": 0}, 409), ({"activity": []}, 422),
                              ({"evidence_run_id": "unseen"}, 422),
                              ({"activity": [{**payload["activity"][0], "evidence_ids": ["unsupported"]}]}, 422),
                              ({"owner_id": _auth_support.OTHER.id}, 422)]:
            assert (await client.put(profile_path, json={**payload, **changes})).status_code == code
            assert (await client.get(profile_path)).json() == saved
        with _auth_support.as_principal(_auth_support.OTHER):
            assert (await client.get(profile_path)).status_code == 404
            assert (await client.get("/api/cyber/suspect-profiles")).json() == []
            assert (await client.put(profile_path, json=payload)).status_code == 422
        with _auth_support.anonymous():
            assert (await client.get(profile_path)).status_code == 401
            assert (await client.put(profile_path, json=payload)).status_code == 401
        updated = await client.put(profile_path, json=payload)
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert (await client.get(profile_path)).json() == updated.json()
        fixture.replies.extend([
            tool_reply("get_suspect_profile", {"profile_id": "suspect"}),
            tool_reply("update_suspect_profile", update_payload(expected_revision=2)),
            completion([({"role": "assistant", "content": "SYNTHETIC update refused."}, None), ({}, "stop")]),
        ])
        refused = frames((await client.post(f"/api/chat/{session}", json={"message": "Try old evidence"})).text)
        result = next(data["result"] for name, data in refused
                      if name == "tool_result" and data["name"] == "update_suspect_profile")
        assert result == {"error": "unsupported_profile_citations"}
        assert (await client.get(profile_path)).json() == updated.json()
        assert (await client.put(profile_path, json={**payload, "expected_revision": 2})).status_code == 422
        assert fixture.external_attempts == []