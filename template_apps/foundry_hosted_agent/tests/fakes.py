"""Offline fakes shaped like the azure-ai-projects 2.6.1 / openai 3.13 surfaces lifecycle.py calls."""

from types import SimpleNamespace

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
TENANT = "66666666-7777-8888-9999-000000000000"
PRINCIPAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ENDPOINT = "https://fake-account.services.ai.azure.com/api/projects/fake-project"
LOGIN = "fakeregistry.azurecr.io"
REPOSITORY = "fake-agent"
MODEL = "example-model-deployment"
DIGEST = "sha256:" + "ab" * 32
VALID_ENV = {
    "AZURE_TENANT_ID": TENANT,
    "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "FOUNDRY_PROJECT_RESOURCE_ID": (f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-fake/providers/"
                                    "Microsoft.CognitiveServices/accounts/fake-account/projects/fake-project"),
    "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
    "ACR_NAME": "fakeregistry",
    "ACR_LOGIN_SERVER": LOGIN,
    "IMAGE_REPOSITORY": REPOSITORY,
    "MODEL_ACCOUNT": "fake-account",
    "MODEL_RESOURCE_GROUP": "rg-fake",
    "MODEL_DEPLOYMENT": MODEL,
}


class NotFound(Exception):
    status_code = 404


class FakeAz:
    """Answers the exact read and build commands; records every call and the staged context at submit."""

    def __init__(self, account=None):
        self.calls, self.staged = [], None
        self.account = account or {"subscriptionId": SUBSCRIPTION, "tenantId": TENANT}

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        head = tuple(arguments[:3])
        if head[:2] == ("account", "show"):
            return self.account
        if head[:2] == ("resource", "show"):
            return {"state": "Succeeded", "endpoints": {"AI Foundry API": ENDPOINT}, "principal": PRINCIPAL}
        if head[:2] == ("acr", "show"):
            return {"id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-fake/providers/"
                          "Microsoft.ContainerRegistry/registries/fakeregistry", "loginServer": LOGIN}
        if head[:3] == ("role", "assignment", "list"):
            return [{"role": "AcrPull", "condition": None}]
        if head[0] == "cognitiveservices":
            return [{"name": MODEL, "state": "Succeeded"}]
        if head[:2] == ("acr", "build"):
            from pathlib import Path
            context = Path(arguments[-1])
            self.staged = sorted(path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file())
            self.tag = arguments[arguments.index("--image") + 1].split(":", 1)[1]
            return {"runId": "run1"}
        if head[:3] == ("acr", "task", "show-run"):
            return {"runId": "run1", "status": "Succeeded",
                    "outputImages": [{"registry": LOGIN, "repository": REPOSITORY, "tag": self.tag, "digest": DIGEST}]}
        if head[:3] == ("acr", "repository", "show"):
            return {"digest": DIGEST}
        raise AssertionError(f"unexpected az command {arguments[:3]}")

    def count(self, *prefix):
        return sum(1 for call in self.calls if tuple(call[:len(prefix)]) == prefix)


class FakeAgents:
    def __init__(self, log):
        self.log, self.versions, self.sessions = log, {}, {"session1"}

    def get(self, agent_name):
        if not self.versions:
            raise NotFound()
        return {"name": agent_name, "versions": {"latest": self.versions[max(self.versions, key=int)]}}

    def create_version(self, agent_name, body):
        self.log.append("create_version")
        version = str(len(self.versions) + 1)
        self.versions[version] = {"version": version, "status": "active", **body}
        return {"version": version, "status": "creating"}

    def get_version(self, agent_name, agent_version):
        if agent_version not in self.versions:
            raise NotFound()
        return dict(self.versions[agent_version])

    def list_versions(self, agent_name, limit, include_drafts=None):
        return list(self.versions.values())

    def delete_version(self, agent_name, agent_version):
        self.log.append("delete_version")
        self.versions.pop(agent_version)

    def list_sessions(self, agent_name, limit):
        return [{"agent_session_id": session} for session in sorted(self.sessions)]

    def get_session(self, agent_name, session_id):
        if session_id not in self.sessions:
            raise NotFound()
        return {"agent_session_id": session_id, "status": "idle"}

    def stop_session(self, agent_name, session_id):
        self.log.append("stop_session")

    def delete_session(self, agent_name, session_id):
        self.log.append("delete_session")
        self.sessions.discard(session_id)


class FakeProject:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.agents = FakeAgents(self.log)


class FakeResponses:
    def __init__(self, store, log):
        self.store, self.log, self.metadata, self.requests = store, log, {}, []

    def create(self, **request):
        self.log.append("responses.create")
        self.requests.append(request)
        response_id = f"resp_{len(self.requests)}"
        response = {"id": response_id, "status": "completed", "metadata": dict(self.metadata),
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "8 words"}]}]}
        self.store[response_id] = response
        return SimpleNamespace(model_dump=lambda mode="json": dict(response), output_text="8 words")

    def cancel(self, response_id):
        self.log.append("responses.cancel")

    def delete(self, response_id):
        self.log.append("responses.delete")
        self.store.pop(response_id, None)
        return {"id": response_id, "deleted": True}


class FakeOpenAI:
    base_url = ENDPOINT + "/agents/example/endpoint/protocols/openai/"
    default_query = {"api-version": "v1"}

    def __init__(self, store, log):
        self.responses = FakeResponses(store, log)


class Reply:
    def __init__(self, status_code, body):
        self.status_code, self.body = status_code, body

    def json(self):
        return self.body


class FakeHttp:
    """Anonymous POST status is configurable; GET reads the shared response store (JSON 404 when absent)."""

    def __init__(self, store, anonymous_status=401):
        self.store, self.anonymous_status, self.posts, self.headers = store, anonymous_status, [], []

    def post(self, url, json):
        self.posts.append(url)
        return Reply(self.anonymous_status, {})

    def get(self, url, params, headers):
        self.headers.append(headers)
        response_id = url.rsplit("/", 1)[1]
        if response_id in self.store:
            return Reply(200, dict(self.store[response_id]))
        return Reply(404, {"error": {"code": "not_found", "message": "missing"}})
