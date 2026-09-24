"""Read-only installed-contract probes for conditional migration decisions."""

import ast
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
from pathlib import Path

from azure.ai.agentserver.optimization import load_config
from azure.ai.projects import models
from azure.ai.projects.operations import DatasetsOperations
from llm_interface import AgentBinding
import evidence


def source(function):
    text = inspect.getsource(function)
    return {"path": inspect.getsourcefile(function), "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}


def main():
    loader = source(load_config)
    upload = source(DatasetsOperations.upload_file)
    cli_path = Path("/opt/az/lib/python3.13/site-packages/azure/cli/command_modules/acr/build.py")
    cli = cli_path.read_text()
    tree = ast.parse(cli)
    direct = any(isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "no_wait"
                 and any(isinstance(child, ast.Return) and isinstance(child.value, ast.Name) and child.value.id == "queued"
                         for child in node.body) for node in ast.walk(tree))
    assert direct
    methods = sorted(name for name in dir(AgentBinding) if not name.startswith("_"))
    result = {"packages": {name: importlib.metadata.version(name) for name in
        ("azure-ai-projects", "azure-ai-agentserver-optimization", "azure-ai-agentserver-responses", "agent-framework-core", "openai")},
        "C01": {"load_config_signature": str(inspect.signature(load_config)), "source": loader,
                "gate": "retained: no public timeout/retry controls; local whitespace stripping reproduced by owner test"},
        "C02": {"source": upload, "gate": "retained explicit SDK stages: provenance, prefix, per-stage intent and readback"},
        "C03": {"AgentBinding_public": methods, "modern_host_installed": importlib.util.find_spec("agent_framework_foundry_hosting") is not None,
                "gate": "retain current official ResponsesAgentServerHost; no public native-agent accessor in AgentBinding"},
        "C04": {"cli_path": str(cli_path), "sha256": hashlib.sha256(cli.encode()).hexdigest(),
                "no_wait_returns_queued": direct, "gate": "implemented direct CLI runId; no new dependency"},
        "C05": {"CodeConfiguration_present": hasattr(models, "CodeConfiguration"), "gate": "retain containers; no selected deployment-mode or ZIP identity contract"},
        "C06": {"gate": "retain direct SDK independent validation; service target row/config/readback equivalence not established; no holdout upload"},
        "C07": {"gate": "retain versioned explicit Python exact-label grader and frozen macro-F1; mapping/error/whitespace parity not established for native string-check"},
        "C08": {"gate": "retain host-owned instrumentation and derived metric exports; no existing custom span implementation removed or new correlation requirement"},
        "C09": {"signal": "asyncio.Event", "gate": "implemented task cancellation/join in both handlers; model/tool and classifier owner tests"},
        "C10": {"gate": "retain direct SDK calls and canonical owners; no cross-testbed runtime imports or new library; short signal adapters remain host-local"}}
    print(json.dumps(evidence.save("conditional-contract-probes.json", result)))


if __name__ == "__main__":
    main()