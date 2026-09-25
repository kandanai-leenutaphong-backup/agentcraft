"""Edge dependencies for pipeline stages. `cloud_clients` is the only place that builds SDK clients; tests pass
fakes in `Clients` directly."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import time
from typing import Any

from ..build import az_json
from ..hosting import AI_SCOPE
from .source import ImageLayout
from .spec import RunSpec


@dataclass
class Clients:
    """Caller-constructed dependencies: Azure CLI runner, project client, agent-scoped OpenAI client (invoke,
    stored read-back, teardown), project OpenAI client (evals), HTTP client, bearer-token callable, image layout."""

    az: Callable[[list[str]], Any] | None = None
    project: Any = None
    openai: Any = None
    evals: Any = None
    http: Any = None
    token: Callable[[], str] | None = None
    layout: ImageLayout | None = None
    request_factory: Any = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


@contextmanager
def cloud_clients(spec: RunSpec, *, layout: ImageLayout, events: list[dict[str, Any]] | None = None) -> Iterator[Clients]:
    """Operator Entra identity through Azure CLI; no key, no secret, no SDK retries that could replay a write."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with ExitStack() as stack:
        credential = stack.enter_context(AzureCliCredential(tenant_id=spec.targets["tenant_id"], process_timeout=30))
        project = stack.enter_context(AIProjectClient(endpoint=spec.targets["project_endpoint"], credential=credential,
                                                      retry_total=0, connection_timeout=15, read_timeout=150))
        openai_client = stack.enter_context(project.get_openai_client(agent_name=spec.agent, max_retries=0, timeout=150))
        eval_client = stack.enter_context(project.get_openai_client(max_retries=0, timeout=150))
        yield Clients(az=lambda arguments: az_json(arguments, events=events), project=project, openai=openai_client,
                      evals=eval_client, token=lambda: credential.get_token(AI_SCOPE).token, layout=layout)
