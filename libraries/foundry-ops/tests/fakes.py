"""Offline fakes shaped like azure-ai-projects 2.6.1 / openai 3.13 / httpx surfaces used by foundry_ops."""

from types import SimpleNamespace


class HTTPError(Exception):
    def __init__(self, status_code, message="http error"):
        super().__init__(message)
        self.status_code = status_code


class ResourceNotFoundError(Exception):
    """Name-matched like azure.core.exceptions.ResourceNotFoundError."""


class APIConnectionError(Exception):
    """Like openai.APIConnectionError: no status_code."""


class Model(dict):
    def as_dict(self):
        return dict(self)


class Reply:
    def __init__(self, status_code, body=None, text=None):
        self.status_code, self._body, self.text = status_code, body, text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeHTTP:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def _next(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.replies.pop(0)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)


class FakeAgents:
    def __init__(self):
        self.agents, self.versions, self.sessions, self.calls = {}, {}, {}, []
        self.session_delete_errors = []
        self.version_status_sequence = ["creating", "active"]

    def _log(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def get(self, agent_name):
        self._log("get", agent_name=agent_name)
        if agent_name not in self.agents:
            raise ResourceNotFoundError(agent_name)
        return Model(self.agents[agent_name])

    def create_version(self, agent_name, body):
        self._log("create_version", agent_name=agent_name, body=body)
        number = str(len([key for key in self.versions if key[0] == agent_name]) + 1)
        self.versions[(agent_name, number)] = {"name": agent_name, "version": number, "status": "creating",
                                               "definition": body["definition"], "metadata": body["metadata"]}
        self.agents[agent_name] = {"name": agent_name, "versions": {"latest": {"version": number}}}
        return Model(self.versions[(agent_name, number)])

    def get_version(self, agent_name, agent_version):
        self._log("get_version", agent_name=agent_name, agent_version=agent_version)
        key = (agent_name, str(agent_version))
        if key not in self.versions:
            raise HTTPError(404)
        state = self.versions[key]
        if state["status"] != "active":
            state["status"] = self.version_status_sequence.pop(0) if self.version_status_sequence else "active"
        return Model(state)

    def list_versions(self, agent_name, limit=None, include_drafts=None):
        self._log("list_versions", agent_name=agent_name)
        return iter([Model(value) for key, value in self.versions.items() if key[0] == agent_name])

    def delete_version(self, agent_name, agent_version):
        self._log("delete_version", agent_name=agent_name, agent_version=agent_version)
        self.versions.pop((agent_name, str(agent_version)))
        if not any(key[0] == agent_name for key in self.versions):
            self.agents.pop(agent_name, None)

    def list_sessions(self, agent_name, limit=None):
        self._log("list_sessions", agent_name=agent_name)
        return iter([Model(value) for key, value in self.sessions.items() if key[0] == agent_name])

    def get_session(self, agent_name, session_id):
        self._log("get_session", agent_name=agent_name, session_id=session_id)
        if (agent_name, session_id) not in self.sessions:
            raise HTTPError(404)
        return Model(self.sessions[(agent_name, session_id)])

    def delete_session(self, agent_name, session_id):
        self._log("delete_session", agent_name=agent_name, session_id=session_id)
        if self.session_delete_errors:
            raise self.session_delete_errors.pop(0)
        self.sessions.pop((agent_name, session_id))

    def stop_session(self, agent_name, session_id):
        self._log("stop_session", agent_name=agent_name, session_id=session_id)

    def get_session_log_stream(self, agent_name, agent_version, session_id, **kwargs):
        self._log("get_session_log_stream", agent_name=agent_name, agent_version=agent_version, **kwargs)
        return iter(self.log_chunks)


class FakeProject:
    def __init__(self):
        self.agents = FakeAgents()


class Event(SimpleNamespace):
    pass


class Stream:
    def __init__(self, events):
        self.events, self.closed = events, False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def __iter__(self):
        return iter(self.events)


class ResponseModel(dict):
    def model_dump(self, mode="json"):
        return dict(self)

    @property
    def output_text(self):
        return self.get("_text")


class FakeResponses:
    def __init__(self):
        self.calls, self.store, self.stream_events = [], {}, []

    def create(self, **request):
        self.calls.append(("create", request))
        if request.get("stream"):
            return Stream(self.stream_events)
        response = ResponseModel(id="resp_1", status="completed", output=[], _text="Iris-setosa")
        self.store["resp_1"] = response
        return response

    def cancel(self, response_id):
        self.calls.append(("cancel", response_id))
        self.store[response_id] = ResponseModel(id=response_id, status="cancelled", output=[])
        return self.store[response_id]

    def retrieve(self, response_id):
        self.calls.append(("retrieve", response_id))
        if response_id not in self.store:
            raise APIConnectionError("mapped 404")
        return self.store[response_id]

    def delete(self, response_id):
        self.calls.append(("delete", response_id))
        self.store.pop(response_id, None)


class FakeOpenAI:
    base_url = "https://example.invalid/api/projects/p/agents/a/endpoint/protocols/openai/"
    default_query = {"api-version": "v1"}

    def __init__(self):
        self.responses = FakeResponses()


class Page:
    def __init__(self, data, last_id=None):
        self.data, self.last_id = data, last_id


class Pager:
    def __init__(self, pages):
        self.pages = pages

    def iter_pages(self):
        return iter(self.pages)


def eval_client(pages=None, runs=None):
    output_items = SimpleNamespace(list=lambda **kwargs: Pager(pages or []))
    run_states = list(runs or [])
    runs_api = SimpleNamespace(output_items=output_items, retrieve=lambda **kwargs: run_states.pop(0))
    return SimpleNamespace(evals=SimpleNamespace(runs=runs_api))


class Clock:
    def __init__(self, step=0.0):
        self.now, self.step, self.slept = 0.0, step, []

    def __call__(self):
        self.now += self.step
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds
