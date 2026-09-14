"""Operator-authorized deployment with resumable, read-back-verified receipts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from .client import FoundryClient, FoundryError, current_version, identifier, instance_principal_id, session_key
from .grants import Grant, GrantBroker
from .packaging import Bundle, load_bundle


class DeployRefused(ValueError):
    pass


class OperatorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    allowed_agents: tuple[str, ...] = ()
    allow_deploy: StrictBool = False
    allow_update: StrictBool = False
    allow_invoke: StrictBool = False
    allow_delete: StrictBool = False
    allow_role_changes: StrictBool = False
    grants: tuple[Grant, ...] = ()

    @field_validator("allowed_agents")
    @classmethod
    def validate_agents(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for name in value:
            identifier(name)
        return value

    def authorize(self, name: str, action: str, *, hosted_process: bool = False) -> None:
        if name not in self.allowed_agents:
            raise DeployRefused("agent is outside the operator's exact-name allowlist")
        if action != "verify" and not getattr(self, f"allow_{action}", False):
            raise DeployRefused(f"operator policy does not permit {action}")
        if hosted_process and action in ("deploy", "update", "delete"):
            raise DeployRefused("deployment mutation is restricted to the operator's local process")


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DeployRefused("receipt must not be a symlink")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_receipt(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise DeployRefused("receipt must not be a symlink")
    return json.loads(path.read_bytes()) if path.exists() else None


class Deployer:
    def __init__(
        self, client: FoundryClient, policy: OperatorPolicy, *, principal: str,
        broker: GrantBroker | None = None, hosted_process: bool = False,
        wait_budget: float = 1200, poll_interval: float = 10,
    ) -> None:
        if not principal:
            raise DeployRefused("operator principal is required")
        self.client = client
        self.policy = policy
        self.principal = principal
        self.broker = broker
        self.hosted_process = hosted_process
        self.wait_budget = wait_budget
        self.poll_interval = poll_interval

    def _check_receipt(self, receipt: dict[str, Any], name: str) -> None:
        if any(receipt.get(key) != expected for key, expected in {
            "endpoint": self.client.endpoint, "name": name, "operator": self.principal,
        }.items()):
            raise DeployRefused("receipt belongs to a different target, agent, or operator")

    async def _await_version(self, name: str, version: str) -> None:
        deadline = time.monotonic() + self.wait_budget
        while time.monotonic() < deadline:
            record = await self.client.version_status(name, version)
            status = record.get("status") or (record.get("definition") or {}).get("status")
            if status == "active":
                return
            if status == "failed":
                raise FoundryError("hosted version build")
            await asyncio.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        raise FoundryError("hosted version readiness deadline")

    async def verify(self, name: str, receipt: dict[str, Any], bundle: Bundle | None = None) -> dict[str, Any]:
        self.policy.authorize(name, "verify")
        self._check_receipt(receipt, name)
        live = await self.client.get_agent(name)
        if live is None or current_version(live) != receipt.get("version"):
            raise FoundryError("deployed version read-back")
        if instance_principal_id(live) != receipt.get("instance_principal_id"):
            raise FoundryError("deployed instance identity read-back")
        await self._await_version(name, receipt["version"])
        health = await self.client.warm(
            name, session_key(self.principal, name, purpose="verify"), budget=min(240, self.wait_budget),
            interval=self.poll_interval,
        )
        if health.get("artifact_id") != receipt.get("runtime_sha256") or health.get("agent") != receipt.get("agent_id"):
            raise FoundryError("runtime artifact identity read-back")
        if bundle is not None:
            if bundle.artifact_id != receipt.get("artifact_id"):
                raise FoundryError("receipt artifact digest")
            if health.get("policy") != bundle.config["policy"] or health.get("model") != bundle.config["model"]:
                raise FoundryError("runtime configuration read-back")
        if receipt.get("grants") and self.broker is None:
            raise DeployRefused("a grant broker is required to verify recorded grants")
        for record in receipt.get("grants", []):
            await self.broker.verify(Grant.model_validate(record["grant"]), receipt["instance_principal_id"])
        return health

    async def deploy(self, name: str, bundle: Bundle, receipt_path: Path) -> dict[str, Any]:
        self.policy.authorize(name, "deploy", hosted_process=self.hosted_process)
        if self.policy.grants and (not self.policy.allow_role_changes or self.broker is None):
            raise DeployRefused("grant application requires explicit role-change permission and a broker")
        bundle = load_bundle(bundle.directory)
        receipt = read_receipt(receipt_path)
        live = await self.client.get_agent(name)
        if receipt is not None:
            self._check_receipt(receipt, name)
            if not receipt.get("version") and receipt.get("state") == "uploading":
                raise DeployRefused("upload outcome is unknown; reconcile its live version before retrying")
            if live is None and receipt.get("state") != "deleted":
                raise DeployRefused("recorded agent is absent; reconcile its grants with teardown before recreating")
            if live is not None and receipt.get("instance_principal_id") and (
                instance_principal_id(live) != receipt["instance_principal_id"]
            ):
                raise DeployRefused("agent instance identity changed outside this receipt")
            planned = {json.dumps(grant.model_dump(), sort_keys=True) for grant in self.policy.grants}
            retained = {json.dumps(record["grant"], sort_keys=True) for record in receipt.get("grants", [])}
            if live is not None and retained - planned:
                raise DeployRefused("the new plan drops recorded grants; teardown or reconcile permissions first")
        if live is not None and receipt is None:
            raise DeployRefused("existing agent has no ownership receipt; refusing to overwrite")
        if live is not None and receipt.get("version") and current_version(live) != receipt["version"]:
            raise DeployRefused("agent version changed outside this receipt")
        if live is not None and receipt.get("artifact_id") != bundle.artifact_id:
            self.policy.authorize(name, "update", hosted_process=self.hosted_process)
        if live is None or receipt.get("artifact_id") != bundle.artifact_id or not receipt.get("version"):
            previous = receipt or {}
            receipt = {
                "endpoint": self.client.endpoint, "name": name, "operator": self.principal,
                "artifact_id": bundle.artifact_id, "zip_sha256": bundle.sha256,
                "runtime_sha256": bundle.runtime_sha256,
                "agent_id": bundle.config["agent_id"],
                "definition_sha256": hashlib.sha256(
                    (json.dumps(bundle.config, indent=2, sort_keys=True) + "\n").encode()
                ).hexdigest(),
                "version": "", "state": "uploading", "grants": previous.get("grants", []) if live else [],
            }
            write_receipt(receipt_path, receipt)
            uploaded = await self.client.upload(
                name=name, metadata=bundle.metadata, zip_path=bundle.zip_path, sha256=bundle.sha256,
                update=live is not None,
            )
            version = current_version(uploaded)
            if not version:
                raise FoundryError("upload did not return a version")
            receipt.update(version=version, state="waiting")
            write_receipt(receipt_path, receipt)
        try:
            await self._await_version(name, receipt["version"])
            live = await self.client.get_agent(name)
            if live is None:
                raise FoundryError("created agent read-back")
            if current_version(live) != receipt["version"]:
                raise DeployRefused("agent version changed while waiting; refusing grant application")
            principal_id = instance_principal_id(live)
            if receipt.get("instance_principal_id") and principal_id != receipt["instance_principal_id"]:
                raise DeployRefused("agent identity changed while waiting; refusing grant application")
            if self.policy.grants:
                uuid.UUID(principal_id)
            receipt.update(instance_principal_id=principal_id, state="granting")
            write_receipt(receipt_path, receipt)
            existing = {json.dumps(record["grant"], sort_keys=True): record for record in receipt["grants"]}
            for grant in self.policy.grants:
                key = json.dumps(grant.model_dump(), sort_keys=True)
                if key in existing and not existing[key].get("pending"):
                    await self.broker.verify(grant, principal_id)
                    continue

                def record_intent(record: dict[str, Any]) -> None:
                    if key not in existing:
                        existing[key] = {**record, "pending": True}
                        receipt["grants"].append(existing[key])
                    write_receipt(receipt_path, receipt)

                record = await self.broker.ensure(grant, principal_id, before_write=record_intent)
                if key in existing:
                    record["created"] = record["created"] or existing[key]["created"]
                    existing[key].clear()
                    existing[key].update(record)
                else:
                    receipt["grants"].append(record)
                write_receipt(receipt_path, receipt)
            receipt["state"] = "warming"
            write_receipt(receipt_path, receipt)
            await self.verify(name, receipt, bundle)
            receipt["state"] = "active"
            write_receipt(receipt_path, receipt)
            return read_receipt(receipt_path)
        except Exception as failure:
            receipt.update(state="failed", failure=type(failure).__name__)
            write_receipt(receipt_path, receipt)
            raise

    async def teardown(self, name: str, receipt_path: Path) -> dict[str, Any]:
        self.policy.authorize(name, "delete", hosted_process=self.hosted_process)
        receipt = read_receipt(receipt_path)
        if receipt is None:
            raise DeployRefused("teardown requires the deployment receipt")
        self._check_receipt(receipt, name)
        live = await self.client.get_agent(name)
        if live is not None and current_version(live) != receipt.get("version"):
            raise DeployRefused("refusing to delete an agent version outside this receipt")
        if live is not None and instance_principal_id(live) != receipt.get("instance_principal_id"):
            raise DeployRefused("refusing to delete an agent identity outside this receipt")
        records = receipt.get("grants", [])
        if records and (not self.policy.allow_role_changes or self.broker is None):
            raise DeployRefused("recorded grant revocation needs explicit role-change permission")
        for record in reversed(records):
            await self.broker.revoke(record, receipt["instance_principal_id"])
        await self.client.delete_agent(name)
        deadline = time.monotonic() + self.wait_budget
        while await self.client.get_agent(name) is not None:
            if time.monotonic() >= deadline:
                raise FoundryError("agent deletion read-back")
            await asyncio.sleep(self.poll_interval)
        receipt["state"] = "deleted"
        write_receipt(receipt_path, receipt)
        return read_receipt(receipt_path)