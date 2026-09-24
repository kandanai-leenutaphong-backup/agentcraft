"""Hosted-agent lifecycle over caller-owned `AIProjectClient` and agent-scoped OpenAI clients.

No SDK import happens here: clients are passed in, versions are created through the SDK's `body=` form,
and not-found is recognised by status code. Every mutation is preceded by a ledger intent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import time
from typing import Any

from .bounds import collect_bounded, poll_until
from .errors import ReadbackError, RefusedError, UnresolvedIntentError, VerificationError
from .logs import DEFAULT_KEYWORDS, exception_lines
from .records import EvidenceLedger, error_summary, to_plain
from .verify import check_active_version, is_not_found, read_stored_response, safe_identifier

PENDING_VERSION_STATUSES = frozenset({"creating", "pending"})
NONTERMINAL_RESPONSE_STATUSES = frozenset({"queued", "in_progress"})
CANCEL_EVENTS = frozenset({"response.created", "response.content_part.added"})
TEARDOWN_PHASES = ("responses", "sessions", "versions")


def hosted_definition(image: str, *, cpu: str = "1", memory: str = "2Gi", protocol: str = "responses",
                      protocol_version: str = "2.0.0") -> dict[str, Any]:
    if "@sha256:" not in image:
        raise RefusedError("mutable_image", "hosted image must be pinned by digest")
    return {"kind": "hosted", "cpu": cpu, "memory": memory, "container_configuration": {"image": image},
            "protocol_versions": [{"protocol": protocol, "version": protocol_version}]}


def agent_reference(agent_name: str, version: str) -> dict[str, str]:
    return {"type": "agent_reference", "name": safe_identifier(agent_name, "agent name"), "version": str(version)}


def _read_or_none(read: Callable[[], Any]) -> Any:
    try:
        return to_plain(read())
    except Exception as error:
        if is_not_found(error):
            return None
        raise


def wait_active(project: Any, *, agent_name: str, version: str, seconds: float = 300.0, interval: float = 5.0,
                sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    result = poll_until(
        lambda: to_plain(project.agents.get_version(agent_name=agent_name, agent_version=version)),
        lambda state: state.get("status") == "active", interval=interval, seconds=seconds,
        abort=lambda state: None if state.get("status") in PENDING_VERSION_STATUSES | {"active"}
        else f"version status {state.get('status')!r}; inspect, do not redeploy",
        sleep=sleep, clock=clock)
    if not result.settled:
        raise ReadbackError("readiness_deadline", "version not active before deadline; inspect before retry")
    return result.value


def deploy_version(project: Any, ledger: EvidenceLedger, *, key: str, agent_name: str,
                   definition: Mapping[str, Any], metadata: Mapping[str, str],
                   previous_version: str | None = None, previous_image: str | None = None,
                   seconds: float = 300.0, interval: float = 5.0, sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Create one immutable hosted version, wait active, read back exact identity.

    Records `deploy-<key>-intent.json`, `-created.json`, `-active.json`. A rerun resumes from the
    created record; an intent without it is unresolved. An existing agent requires `previous_version`
    to equal its latest version and a different image.
    """
    safe_identifier(agent_name, "agent name")
    active, created_name = f"deploy-{key}-active.json", f"deploy-{key}-created.json"
    if ledger.exists(active):
        return ledger.read(active)
    image = definition["container_configuration"]["image"]
    if ledger.exists(created_name):
        created = ledger.read(created_name)
    else:
        existing = _read_or_none(lambda: project.agents.get(agent_name=agent_name))
        if existing is not None:
            latest = str(((existing.get("versions") or {}).get("latest") or {}).get("version"))
            if previous_version is None:
                raise RefusedError("agent_exists", "agent exists; explicit owned previous version required")
            if latest != str(previous_version):
                raise RefusedError("latest_drift", "latest version drift; no overwrite")
            if previous_image == image:
                raise RefusedError("image_unchanged", "new version requires a distinct immutable image")
        elif previous_version is not None:
            raise RefusedError("previous_missing", "previous owned agent missing")
        body = {"definition": dict(definition), "metadata": dict(metadata)}
        ledger.intent(f"deploy-{key}", {"agent_name": agent_name, **body})
        created = to_plain(project.agents.create_version(agent_name=agent_name, body=body))
        ledger.retain(created_name, created)
    version = str(created.get("version") or "")
    if not version.isdigit():
        raise ReadbackError("version_unknown", "create accepted but version unknown; read back before any retry")
    actual = wait_active(project, agent_name=agent_name, version=version, seconds=seconds, interval=interval,
                         sleep=sleep, clock=clock)
    readback = check_active_version(actual, version=version, image=image, metadata=metadata, definition=definition)
    result = {"agent": agent_name, "version": version, "definition": dict(definition),
              "metadata": dict(metadata), "readback": readback}
    ledger.retain(active, result)
    return result


def invoke(openai_client: Any, ledger: EvidenceLedger, *, key: str, agent_name: str, version: str,
           input: Any, store: bool = True, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """One non-streaming Responses call pinned to an agent version, at most once per `key`."""
    request = {"input": input, "store": store, "stream": False,
               "extra_body": {"agent_reference": agent_reference(agent_name, version)}}

    def call() -> dict[str, Any]:
        started = clock()
        response = openai_client.responses.create(**request)
        return {"response": to_plain(response), "output_text": getattr(response, "output_text", None),
                "seconds": clock() - started}

    return ledger.once(f"invoke-{key}", request, call)


def cancel_response(openai_client: Any, ledger: EvidenceLedger, *, key: str, agent_name: str, version: str,
                    input: Any, cancel_on: str = "response.created", attempts: int = 10, interval: float = 2.0,
                    sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Stream a background response, cancel at `cancel_on`, prove `cancelled` without output by read-back.

    Resumes from `cancel-<key>-accepted.json`; a cancel already requested is never re-sent.
    """
    if cancel_on not in CANCEL_EVENTS:
        raise RefusedError("cancel_event", "unsupported cancellation point")
    prefix = f"cancel-{key}"
    accepted = prefix + "-accepted.json"

    def request_cancel(response_id: str) -> None:
        ledger.intent(prefix + "-request", {"response_id": response_id})
        ledger.retain(prefix + "-result.json", to_plain(openai_client.responses.cancel(response_id)))

    if ledger.exists(accepted):
        response_id = ledger.read(accepted)["response_id"]
    else:
        request = {"input": input, "store": True, "stream": True, "background": True,
                   "extra_body": {"agent_reference": agent_reference(agent_name, version)}}
        ledger.intent(prefix, request)
        response_id = None
        with openai_client.responses.create(**request) as stream:
            for event in stream:
                if event.type == "response.created" and response_id is None:
                    response = to_plain(event.response)
                    response_id = response["id"]
                    ledger.retain(accepted, {"response_id": response_id, "response": response})
                if response_id is not None and event.type == cancel_on:
                    request_cancel(response_id)
                    break
        if response_id is None:
            raise ReadbackError("stream_without_identity", "stream ended without response identity; reconcile intent")
    observed = to_plain(openai_client.responses.retrieve(response_id))
    if observed.get("status") in NONTERMINAL_RESPONSE_STATUSES and not ledger.exists(prefix + "-request-intent.json"):
        request_cancel(response_id)
    result = poll_until(lambda: to_plain(openai_client.responses.retrieve(response_id)),
                        lambda state: state.get("status") not in NONTERMINAL_RESPONSE_STATUSES,
                        attempts=attempts, interval=interval, sleep=sleep)
    if result.value.get("status") != "cancelled" or result.value.get("output"):
        raise VerificationError("cancellation_not_proved", "cancellation not proved; reconcile without replay")
    return {"response_id": response_id, "cancelled": True, "output_absent": True,
            "readback": result.value, "readback_attempts": result.attempts}


def list_sessions(project: Any, agent_name: str, *, max_items: int = 1000, seconds: float = 60.0,
                  clock: Callable[[], float] = time.monotonic) -> list[dict[str, Any]]:
    return collect_bounded(project.agents.list_sessions(agent_name=agent_name, limit=100),
                           max_items=max_items, seconds=seconds, clock=clock)


def list_versions(project: Any, agent_name: str, *, include_drafts: bool | None = None, max_items: int = 1000,
                  seconds: float = 60.0, clock: Callable[[], float] = time.monotonic) -> list[dict[str, Any]]:
    return collect_bounded(project.agents.list_versions(agent_name=agent_name, limit=100, include_drafts=include_drafts),
                           max_items=max_items, seconds=seconds, clock=clock)


def session_log_excerpt(project: Any, *, agent_name: str, agent_version: str, session_id: str,
                        keywords: tuple[str, ...] = DEFAULT_KEYWORDS, max_lines: int = 100, seconds: float = 20.0,
                        max_bytes: int = 1048576, max_events: int = 1000, connection_timeout: float = 10,
                        read_timeout: float = 5, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Verify the session belongs to `agent_version`, then return a bounded redacted exception excerpt."""
    safe_identifier(session_id, "session id")
    session = to_plain(project.agents.get_session(agent_name=agent_name, session_id=session_id))
    if str((session.get("version_indicator") or {}).get("agent_version")) != str(agent_version):
        raise VerificationError("session_version", "session version mismatch")

    def chunks() -> Iterable[bytes]:
        yield from project.agents.get_session_log_stream(
            agent_name=agent_name, agent_version=str(agent_version), session_id=session_id,
            connection_timeout=connection_timeout, read_timeout=read_timeout)

    excerpt = exception_lines(chunks(), keywords=keywords, max_lines=max_lines, seconds=seconds,
                              max_bytes=max_bytes, max_events=max_events, clock=clock)
    return {"session_id": session_id, "version": str(agent_version), **excerpt}


class HostedTeardown:
    """Owned hosted-agent teardown in the only safe order: responses -> sessions -> versions.

    Any Responses call through an agent-scoped client re-creates deleted sessions, which then block
    version deletion with 409. Calling an earlier phase after a later one is refused. Each step reads,
    records intent, deletes, then polls read-back; `execute=False` records only the plan.
    """

    def __init__(self, project: Any, ledger: EvidenceLedger, *, agent_name: str, execute: bool = False,
                 polls: int = 4, interval: float = 5.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self.project, self.ledger, self.execute = project, ledger, execute
        self.agent_name = safe_identifier(agent_name, "agent name")
        self.polls, self.interval, self.sleep = polls, interval, sleep
        self.outcomes: list[dict[str, Any]] = []
        self._reached = -1

    def _enter(self, phase: str) -> None:
        index = TEARDOWN_PHASES.index(phase)
        if index < self._reached:
            raise RefusedError("teardown_order", f"{phase} after {TEARDOWN_PHASES[self._reached]} refused; "
                               "order is responses -> sessions -> versions")
        self._reached = index

    def _step(self, kind: str, ident: str, read: Callable[[], Any], delete: Callable[[Any], Any]) -> dict[str, Any]:
        name = f"teardown-{kind}-{self.agent_name}-{safe_identifier(ident, kind + ' id')}"
        base = {"kind": kind, "agent": self.agent_name, "id": ident}
        if self.ledger.exists(name + "-result.json"):
            record = self.ledger.read(name + "-result.json")
            self.outcomes.append(record)
            return record
        state = read()
        dangling = self.ledger.exists(name + "-intent.json")
        if state is None:
            record = {**base, "outcome": "deleted" if dangling else "already-absent", "reconciled": dangling}
        elif dangling:
            raise UnresolvedIntentError("unresolved_intent", f"{name} intent exists and target still present")
        elif not self.execute:
            record = {**base, "outcome": "planned", "pre_state": state}
        else:
            self.ledger.intent(name, {**base, "pre_state": state})
            error = returned = None
            try:
                returned = to_plain(delete(state))
            except Exception as failure:
                error = error_summary(failure)
            polled = poll_until(read, lambda value: value is None, attempts=self.polls, interval=self.interval,
                                sleep=self.sleep)
            outcome = "deleted" if polled.settled else "delete-failed" if error else "still-present"
            record = {**base, "outcome": outcome, "delete_error": error, "delete_returned": returned,
                      "readback_attempts": polled.attempts, "readback": polled.value}
        if self.execute:
            self.ledger.retain(name + "-result.json", record)
        self.outcomes.append(record)
        return record

    def responses(self, openai_client: Any, response_ids: Iterable[str], *, bearer_token: str,
                  http_client: Any = None) -> list[dict[str, Any]]:
        """`openai_client` must be scoped to this agent; read-back uses raw GET so 404 is visible."""
        self._enter("responses")

        def delete(state: Mapping[str, Any], rid: str) -> Any:
            if state.get("status") in NONTERMINAL_RESPONSE_STATUSES:
                openai_client.responses.cancel(rid)
            return openai_client.responses.delete(rid)

        return [self._step("response", rid,
                           lambda rid=rid: read_stored_response(openai_client, rid, bearer_token=bearer_token,
                                                                http_client=http_client),
                           lambda state, rid=rid: delete(state, rid))
                for rid in dict.fromkeys(response_ids)]

    def sessions(self, session_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Default: every listed session id, deduplicated (listings repeat deleted/re-created ids)."""
        self._enter("sessions")
        agents = self.project.agents
        if session_ids is None:
            listed = _read_or_none(lambda: list_sessions(self.project, self.agent_name)) or []
            session_ids = [session["agent_session_id"] for session in listed]

        def delete(sid: str) -> None:
            try:
                agents.delete_session(agent_name=self.agent_name, session_id=sid)
            except Exception as error:
                if getattr(error, "status_code", None) not in (400, 409):
                    raise
                agents.stop_session(agent_name=self.agent_name, session_id=sid)
                agents.delete_session(agent_name=self.agent_name, session_id=sid)

        return [self._step("session", sid,
                           lambda sid=sid: _read_or_none(lambda: agents.get_session(agent_name=self.agent_name,
                                                                                     session_id=sid)),
                           lambda state, sid=sid: delete(sid))
                for sid in dict.fromkeys(session_ids)]

    def versions(self, versions: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Deleting the last version removes the agent; confirm with `agent_readback()`."""
        self._enter("versions")
        agents = self.project.agents
        if versions is None:
            listed = _read_or_none(lambda: list_versions(self.project, self.agent_name, include_drafts=True)) or []
            versions = [str(item["version"]) for item in listed]
        return [self._step("version", str(number),
                           lambda number=number: _read_or_none(lambda: agents.get_version(
                               agent_name=self.agent_name, agent_version=str(number))),
                           lambda state, number=number: agents.delete_version(agent_name=self.agent_name,
                                                                             agent_version=str(number)))
                for number in dict.fromkeys(str(value) for value in versions)]

    def agent_readback(self) -> dict[str, Any]:
        if self._reached < TEARDOWN_PHASES.index("versions"):
            raise RefusedError("teardown_order", "agent read-back requires the versions phase first")
        state = _read_or_none(lambda: self.project.agents.get(agent_name=self.agent_name))
        return {"kind": "agent", "id": self.agent_name, "outcome": "absent" if state is None else "present",
                "state": state}
