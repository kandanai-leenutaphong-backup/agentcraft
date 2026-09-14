"""One operator CLI: local build/plan; authorized Foundry lifecycle and read-back."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _bootstrap import SKILL_ROOT
from pydantic import BaseModel, ConfigDict, Field

from hostedagents import load_definition
from hostedagents.client import FoundryClient, project_endpoint, session_key
from hostedagents.deployment import Deployer, DeployRefused, OperatorPolicy, read_receipt
from hostedagents.grants import GrantBroker
from hostedagents.packaging import build_bundle, load_bundle
from hostedagents.policy import RuntimePolicy, RuntimeTarget


class BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_dir: str
    agent_id: str | None = None
    package_sources: dict[str, str] = Field(default_factory=dict)
    allowed_prefixes: tuple[str, ...] = ()
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    runtime_target: RuntimeTarget = Field(default_factory=RuntimeTarget)
    requirements: str | None = None
    cpu: str = "1"
    memory: str = "2Gi"


def read_build(path: Path) -> tuple[BuildConfig, dict[str, Path]]:
    config = BuildConfig.model_validate_json(path.read_bytes())
    sources = {name: (path.parent / value).resolve() for name, value in config.package_sources.items()}
    for source in sources.values():
        sys.path.insert(0, str(source.parent))
    return config, sources


def build(path: Path, output: Path):
    config, sources = read_build(path)
    definition = load_definition(
        (path.parent / config.control_dir).resolve(), agent_id=config.agent_id,
        allowed_prefixes=config.allowed_prefixes,
    )
    return build_bundle(
        definition, package_sources=sources, output_dir=output,
        policy=config.runtime_policy, target=config.runtime_target,
        requirements=(path.parent / config.requirements).resolve() if config.requirements else None,
        cpu=config.cpu, memory=config.memory,
    )


_ENV_KEYS = frozenset({
    "SUBSCRIPTION_ID", "TENANT_ID", "FOUNDRY_ACCOUNT", "FOUNDRY_PROJECT", "FOUNDRY_RESOURCE_GROUP",
    "AGENT_NAME", "BUILD_CONFIG", "OPERATOR_POLICY", "STATE_DIR",
})


def environment(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(path, interpolate=False)
    if set(values) != _ENV_KEYS or any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise DeployRefused("environment file must contain exactly the documented non-empty target keys")
    import uuid

    for key in ("SUBSCRIPTION_ID", "TENANT_ID"):
        uuid.UUID(values[key])
    endpoint = project_endpoint(
        f"https://{values['FOUNDRY_ACCOUNT']}.services.ai.azure.com/api/projects/{values['FOUNDRY_PROJECT']}"
    )
    values["ENDPOINT"] = endpoint
    for key in ("BUILD_CONFIG", "OPERATOR_POLICY", "STATE_DIR"):
        values[key] = str((path.parent / values[key]).resolve())
    return dict(values)


def preflight(values: dict[str, str]) -> str:
    result = subprocess.run(["az", "account", "show", "--output", "json"], capture_output=True, text=True, check=False)
    if result.returncode:
        raise DeployRefused("run az login and az account set --subscription using the environment target")
    account = json.loads(result.stdout)
    if account.get("id", "").lower() != values["SUBSCRIPTION_ID"].lower() or account.get("tenantId", "").lower() != values["TENANT_ID"].lower():
        raise DeployRefused("active Azure subscription/tenant differs from the environment file")
    user = account.get("user") or {}
    if user.get("type") != "user" or not user.get("name"):
        raise DeployRefused("deployment entry point requires an operator Azure CLI user login")
    return hashlib.sha256(json.dumps([account["tenantId"], user["name"]]).encode()).hexdigest()


@contextlib.contextmanager
def receipt_lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as failure:
            raise DeployRefused("another deployment operation owns this receipt") from failure
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--env", type=Path, required=True)
    result.add_argument("command", choices=("build", "plan", "deploy", "verify", "invoke", "teardown"))
    result.add_argument("--artifact", type=Path)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--request", type=Path)
    result.add_argument("--confirm", action="store_true")
    return result


async def execute(arguments: argparse.Namespace) -> dict[str, Any]:
    values = environment(arguments.env.resolve())
    policy = OperatorPolicy.model_validate_json(Path(values["OPERATOR_POLICY"]).read_bytes())
    name = values["AGENT_NAME"]
    state = Path(values["STATE_DIR"])
    receipt_path = state / f"{name}.json"
    if arguments.command == "build":
        bundle = build(Path(values["BUILD_CONFIG"]), arguments.output_dir or state / "artifacts")
        return {"artifact": str(bundle.directory), "artifact_id": bundle.artifact_id, "zip_sha256": bundle.sha256,
                "tools": bundle.config["tools"], "cloud_calls": False}
    if arguments.command == "plan":
        config, _sources = read_build(Path(values["BUILD_CONFIG"]))
        return {"endpoint": values["ENDPOINT"], "agent": name, "operator_policy": policy.model_dump(mode="json"),
                "runtime_policy": config.runtime_policy.model_dump(mode="json"), "receipt": str(receipt_path), "cloud_calls": False}
    hosted_process = any(os.environ.get(key) for key in ("CONTAINER_APP_NAME", "FOUNDRY_AGENT_SESSION_ID"))
    action = {"teardown": "delete"}.get(arguments.command, arguments.command)
    policy.authorize(name, action, hosted_process=hosted_process)
    if arguments.command != "verify" and not arguments.confirm:
        raise DeployRefused("review plan, then pass --confirm for this explicitly authorized operation")
    bundle = load_bundle(arguments.artifact) if arguments.artifact else None
    if arguments.command == "deploy" and bundle is None:
        raise DeployRefused("deploy requires --artifact pointing to a verified build directory")
    principal = preflight(values)
    from azure.identity import AzureCliCredential

    credential = AzureCliCredential(tenant_id=values["TENANT_ID"], subscription=values["SUBSCRIPTION_ID"])
    client = FoundryClient(values["ENDPOINT"], credential)
    deployer = Deployer(
        client, policy, principal=principal, broker=GrantBroker(credential), hosted_process=hosted_process,
    )
    with receipt_lock(receipt_path.with_suffix(".lock")):
        if arguments.command == "deploy":
            return await deployer.deploy(name, bundle, receipt_path)
        if arguments.command == "teardown":
            return await deployer.teardown(name, receipt_path)
        receipt = read_receipt(receipt_path)
        if receipt is None:
            raise DeployRefused("operation requires the deployment receipt")
        health = await deployer.verify(name, receipt, bundle)
        if arguments.command == "verify":
            return {"verified": True, "name": name, "version": receipt["version"], "health": health}
        if arguments.request is None:
            raise DeployRefused("invoke requires --request pointing to a JSON invocation")
        payload = arguments.request.read_bytes()
        if len(payload) > 128_000:
            raise DeployRefused("invocation exceeds 128000 bytes")
        body = json.loads(payload)
        if not isinstance(body, dict):
            raise DeployRefused("invocation must be a JSON object")
        body["stream"] = False
        status, result = await client.invoke(name, session_key(principal, name), body)
        if status != 200:
            raise DeployRefused(f"invocation refused (HTTP {status})")
        return {"status": status, "result": result}


def main() -> int:
    try:
        result = asyncio.run(execute(parser().parse_args()))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as failure:
        safe = str(failure) if isinstance(failure, DeployRefused) else type(failure).__name__
        print(f"refused: {safe}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())