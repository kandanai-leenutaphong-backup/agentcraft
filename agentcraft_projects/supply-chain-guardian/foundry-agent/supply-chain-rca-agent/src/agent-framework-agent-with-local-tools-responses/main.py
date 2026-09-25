# Copyright (c) Microsoft. All rights reserved.
"""Supply Chain Guardian RCA agent.

Hosted on Microsoft Foundry via the Microsoft Agent Framework. Every tool below calls a
live /tools/* endpoint on the already-deployed supply-chain-guardian Container App, which in
turn calls real Fabric, Azure AI Search, and Microsoft Graph APIs (managed-identity
authenticated). There is no mocked/canned data anywhere in this agent: if a tool call fails
or a live source has nothing to say, the tool returns that fact plainly and the agent must
say so rather than inventing evidence.
"""

import os

import requests
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field
from typing_extensions import Annotated

load_dotenv()

# Base URL of the existing supply-chain-guardian app that hosts the live evidence tools.
# Override via SCG_APP_BASE_URL for local/dev testing against a different deployment.
SCG_APP_BASE_URL = os.environ.get(
    "SCG_APP_BASE_URL",
    "https://supply-chain-guardian.delightfulplant-c387f72d.malaysiawest.azurecontainerapps.io",
)
_TIMEOUT_SECONDS = 20


def _get(path: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(f"{SCG_APP_BASE_URL}{path}", params=params, timeout=_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": True, "detail": f"live call to {path} failed: {exc}"}


@tool(approval_mode="never_require")
def fabric_evidence() -> dict:
    """Get live Fabric IQ evidence: real workspace items (ontology SQL endpoint, Lakehouse,
    notebook) and the real Delta table names currently in the Lakehouse. No mocked data;
    if the Lakehouse has zero tables, this reflects that the ontology notebook has not been
    (re)run, not a placeholder."""
    return _get("/tools/fabric-evidence")


@tool(approval_mode="never_require")
def policy_search(
    query: Annotated[str, Field(description="Search text describing the disruption or mitigation "
                                             "policy being investigated, e.g. 'supplier shipment "
                                             "delay contract remedy'.")],
) -> dict:
    """Search the live, governed policy/contract index (Azure AI Search) for mitigation
    guidance and contract-clause citations relevant to a disruption. Returns real matched
    documents; never fabricated citations."""
    return _get("/tools/policy-search", {"query": query})


@tool(approval_mode="never_require")
def org_context() -> dict:
    """Get the live organizational context (manager / direct reports) for the demo account
    via Microsoft Graph, to identify who should be looped in or who approval should route to."""
    return _get("/tools/org-context")


@tool(approval_mode="never_require")
def recent_mail(
    top: Annotated[int, Field(description="How many recent inbox messages to fetch (default 5).")] = 5,
) -> dict:
    """Get real recent inbox messages via Microsoft Graph that may reference this
    disruption (e.g. a supplier notice or an internal escalation thread)."""
    return _get("/tools/recent-mail", {"top": top})


@tool(approval_mode="never_require")
def web_search(
    query: Annotated[str, Field(description="Web search query about the disruption, e.g. "
                                             "'RM-14 supplier shipment delay S102'.")],
) -> dict:
    """Run a live web search for outside context on a disruption (news, supplier statements,
    logistics context). Returns real search results, never invented headlines."""
    return _get("/tools/web-search", {"query": query})


AGENT_INSTRUCTIONS = """You are the Supply Chain Guardian root-cause-analysis (RCA) agent.

You investigate supply-chain disruptions (late shipments, insufficient raw materials,
cascading production risk) for a manufacturing operation. You have four live evidence
tools: fabric_evidence (Fabric ontology/lakehouse), policy_search (governed mitigation
policy/contract index), org_context and recent_mail (Work IQ / Microsoft Graph), and
web_search (outside context). Always call the tools relevant to the question before
answering; never state a root cause, blast radius, or mitigation citation you did not
obtain from a tool result. If a tool returns an error or empty/mocked result, say so
explicitly instead of filling in a plausible-sounding answer.

When asked to explain or investigate a disruption, structure your answer as:
1. Root cause hypothesis (what happened, and why you believe it, citing which tool
   result supports each claim)
2. Business impact / blast radius (which orders, customers, or SKUs are affected, per
   the live evidence, not assumptions)
3. Recommended mitigation, citing the specific policy/contract clause from policy_search
   if one was found, or stating none was found
4. Confidence and what additional live evidence (if any) would raise it

Be concise, evidence-first, and honest about the limits of what you found."""


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=AGENT_INSTRUCTIONS,
        tools=[fabric_evidence, policy_search, org_context, recent_mail, web_search],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
