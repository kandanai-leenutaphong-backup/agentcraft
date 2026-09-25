"""Server-side ACR image build through a caller-supplied Azure CLI runner; digest-pinned output."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
import os
import re
import subprocess
import time
from typing import Any

from ..core.bounds import poll_until
from ..core.errors import OutcomeUnknownError, ReadbackError, VerificationError
from ..core.records import EvidenceLedger, redact_text

AzRunner = Callable[[list[str]], Any]
RUNNING_BUILD_STATUSES = frozenset({"Queued", "Started", "Running"})
_QUEUED = re.compile(r"^(?:WARNING: )?Queued a build with ID: ([A-Za-z0-9]+)\s*$", re.MULTILINE)
_RUN_QUERY = "{runId:runId,status:status,outputImages:outputImages,startTime:startTime,finishTime:finishTime}"


def parse_queued_build_id(stderr: str) -> str | None:
    """`az acr build --no-wait` may print the run id only on stderr; accept exactly one."""
    identifiers = _QUEUED.findall(stderr or "")
    return identifiers[0] if len(identifiers) == 1 else None


def az_json(arguments: Sequence[str], *, timeout: float = 180.0, events: list[dict[str, Any]] | None = None,
            runner: Callable[..., Any] = subprocess.run, clock: Callable[[], float] = time.monotonic) -> Any:
    """Run `az <arguments> -o json`; record command, exit code, seconds and redacted diagnostics in `events`."""
    command = ["az", *arguments, "-o", "json"]
    started = clock()
    result = runner(command, capture_output=True, text=True, timeout=timeout)
    event: dict[str, Any] = {"command": command, "exit_code": result.returncode, "seconds": clock() - started}
    if events is not None:
        events.append(event)
    if result.returncode:
        event["diagnostic"] = redact_text(result.stderr or "")[:4000]
        raise RuntimeError("Azure CLI refused command; inspect retained diagnostic")
    output = json.loads(result.stdout or "null")
    if list(arguments[:2]) == ["acr", "build"] and "--no-wait" in arguments and not isinstance(output, dict):
        run_id = parse_queued_build_id(result.stderr)
        if run_id:
            output = {"runId": run_id}
            event["identity_source"] = "direct CLI queued-build diagnostic"
    event["result"] = output
    return output


def submit_build(az: AzRunner, ledger: EvidenceLedger, *, key: str, subscription: str, registry: str,
                 image: str, context_dir: str | os.PathLike[str], dockerfile: str = "Dockerfile",
                 platform: str = "linux/amd64", timeout: int = 900,
                 context: Mapping[str, Any] | None = None) -> str:
    """Queue one `az acr build --no-wait` under intent; return its run id. Unknown outcome is never resubmitted.

    `context` adds caller fields (e.g. archive identity) to the intent record; unknown outcome raises
    `OutcomeUnknownError` (a `ReadbackError` and a `ValueError`).
    """
    run_record = f"build-{key}-run.json"
    if ledger.exists(run_record):
        return ledger.read(run_record)["run_id"]
    source = os.fspath(context_dir)
    command = ["acr", "build", "--subscription", subscription, "--registry", registry, "--platform", platform,
               "--image", image, "--file", os.path.join(source, dockerfile), "--no-logs", "--no-wait",
               "--timeout", str(timeout), "--query", "{runId:runId}", source]
    ledger.intent(f"build-{key}", {"command": command, "image": image}, context=dict(context or {}))
    queued = az(command)
    run_id = queued.get("runId") if isinstance(queued, dict) else None
    if not isinstance(run_id, str) or not run_id.isalnum():
        raise OutcomeUnknownError("build_outcome_unknown", "build outcome unknown; reconcile retained tag, never resubmit")
    ledger.retain(run_record, {"run_id": run_id, "image": image})
    return run_id


def wait_build(az: AzRunner, *, subscription: str, registry: str, run_id: str, seconds: float = 900.0,
               interval: float = 10.0, sleep: Callable[[float], None] = time.sleep,
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    def read() -> dict[str, Any]:
        run = az(["acr", "task", "show-run", "--subscription", subscription, "--registry", registry,
                  "--run-id", run_id, "--query", _RUN_QUERY])
        if run.get("runId") != run_id:
            raise VerificationError("foreign_build", "foreign ACR run identity")
        return run

    result = poll_until(read, lambda run: run.get("status") == "Succeeded", interval=interval, seconds=seconds,
                        abort=lambda run: None if run.get("status") in RUNNING_BUILD_STATUSES | {"Succeeded"}
                        else f"ACR run {run_id}: {run.get('status')}; inspect before retry",
                        sleep=sleep, clock=clock)
    if not result.settled:
        raise ReadbackError("build_deadline", f"ACR run {run_id} not finished before deadline; reconcile, never resubmit")
    return result.value


def resolve_image(az: AzRunner, run: dict[str, Any], *, subscription: str, registry: str, registry_host: str,
                  repository: str, tag: str) -> str:
    """Exactly one run output must match repo:tag and its registry digest; return `host/repo@digest`."""
    images = [image for image in run.get("outputImages") or []
              if image.get("registry", registry_host) == registry_host
              and image.get("repository") == repository and image.get("tag") == tag]
    if len(images) != 1:
        raise VerificationError("build_output", "ACR run output does not match the pinned tag")
    shown = az(["acr", "repository", "show", "--subscription", subscription, "--name", registry,
                "--image", f"{repository}:{tag}", "--query", "{digest:digest}"])
    if not isinstance(shown, dict) or shown.get("digest") != images[0].get("digest"):
        raise VerificationError("image_digest", "ACR output digest drift")
    return f"{registry_host}/{repository}@{shown['digest']}"
