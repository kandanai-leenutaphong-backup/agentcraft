"""Hosted-agent lifecycle behind deploy.sh: test, preflight, build, deploy, invoke, verify, teardown.

Lifecycle mechanics are `foundry_ops`; this module owns only targets, the source allowlist and the order.
Cloud clients are constructed in `main()` and passed down; every action function accepts fakes.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Callable
import unittest

from foundry_ops.build import az_json, resolve_image, submit_build, wait_build
from foundry_ops.errors import FoundryOpsError, RefusedError, VerificationError
from foundry_ops.evals import validate_dataset_version
from foundry_ops.hosted import HostedTeardown, deploy_version, hosted_definition, invoke as hosted_invoke
from foundry_ops.manifest import RunManifest, load_run_manifest, series_directory
from foundry_ops.records import EvidenceLedger, error_summary, sanitize, sha256_hex, to_plain, utc_stamp
from foundry_ops.verify import (AI_SCOPE, agent_responses_url, anonymous_probe, check_active_version,
                                check_identity, is_not_found, read_stored_response, require_refusal)

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
APP = ROOT / "app"
ENV_DIR = DEPLOY / "env"
RECORDS = DEPLOY / "records"
PURPOSE = "foundry-hosted-agent"
NAME = r"[a-z0-9][a-z0-9-]{0,62}"
ENVIRONMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
CLOUD_ACTIONS = ("preflight", "build", "deploy", "invoke", "verify", "teardown")
WRITE_ACTIONS = frozenset({"build", "deploy", "invoke", "teardown"})
MANIFEST_KEYS = frozenset({"schema_version", "purpose", "series", "agent", "actions", "env_sha256",
                           "previous_version", "previous_image"})
APP_SUFFIXES = frozenset({".py", ".yaml", ".md"})
LIBRARY_PACKAGES = {"agentcraft_core": "framework-core/src/agentcraft_core",
                    "llm_interface": "llm-interface/src/llm_interface",
                    "agentconfig": "modular-agents/modules/agent-config-build/agentconfig"}
DEPLOY_FILES = ("Dockerfile", "runtime-requirements.lock")
PROJECT_API_VERSION = "2025-06-01"

GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
ENV_FORMATS = {
    "AZURE_TENANT_ID": GUID,
    "AZURE_SUBSCRIPTION_ID": GUID,
    "FOUNDRY_PROJECT_RESOURCE_ID": (r"/subscriptions/" + GUID + r"/resourceGroups/[A-Za-z0-9._()-]{1,90}"
                                    r"/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]{2,64}"
                                    r"/projects/[A-Za-z0-9_-]{1,64}"),
    "FOUNDRY_PROJECT_ENDPOINT": r"https://[a-z0-9-]{2,64}\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_-]{1,64}",
    "ACR_NAME": r"[A-Za-z0-9]{5,50}",
    "ACR_LOGIN_SERVER": r"[a-z0-9]{5,50}\.azurecr\.io",
    "IMAGE_REPOSITORY": r"[a-z0-9]+(?:[._/-][a-z0-9]+){0,20}",
    "MODEL_ACCOUNT": r"[A-Za-z0-9-]{2,64}",
    "MODEL_RESOURCE_GROUP": r"[A-Za-z0-9._()-]{1,90}",
    "MODEL_DEPLOYMENT": r"[A-Za-z0-9._-]{1,64}",
}
SECRET_NAME = re.compile(r"(?i)(secret|password|passwd|token|api_?key|account_?key|connection_?string|"
                         r"(^|_)sas($|_)|_key$|credential)")
SECRET_VALUE = re.compile(r"(?i)(eyJ[A-Za-z0-9_-]{10,}|-----BEGIN|accountkey=|sharedaccesskey=|sharedaccesssignature|"
                          r"(^|[?&;])sig=|password=|secret=|token=|client_secret|ghp_|github_pat_|\bsk-[A-Za-z0-9]{8,}|"
                          r"[A-Za-z0-9+/]{30,}={1,2}$)")
AUTH_NAME = re.compile(r"(?i)auth")
AUTH_OFF = frozenset({"false", "0", "off", "no", "disabled", "none", "anonymous"})
AGENT_ACCESS_NAME = re.compile(r"(?i)(agent_access|signed_dev|dev_access)")


# --- targets ---------------------------------------------------------------------------------

def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise RefusedError("env_syntax", f"line {number}: expected KEY=VALUE")
        if key in values:
            raise RefusedError("env_duplicate", f"duplicate variable {key}")
        values[key] = value
    return values


def validate_env(values: dict[str, str]) -> dict[str, str]:
    """Refuse before any side effect. Messages name the variable, never its value."""
    for key, value in values.items():
        if SECRET_NAME.search(key) or SECRET_VALUE.search(value):
            raise RefusedError("env_secret", f"secret-shaped variable refused: {key}; use managed identity or Key Vault")
        if AUTH_NAME.search(key) and value.strip().lower() in AUTH_OFF:
            raise RefusedError("env_auth_disabled", f"variable would disable authentication: {key}")
        if AGENT_ACCESS_NAME.search(key):
            raise RefusedError("env_agent_access", f"variable would enable unrequested agent access: {key}")
    unknown = sorted(set(values) - set(ENV_FORMATS))
    if unknown:
        raise RefusedError("env_unknown", "unknown variables: " + ", ".join(unknown))
    missing = sorted(key for key in ENV_FORMATS if not values.get(key))
    if missing:
        raise RefusedError("env_missing", "missing variables: " + ", ".join(missing))
    placeholders = sorted(key for key, value in values.items() if "<" in value or ">" in value)
    if placeholders:
        raise RefusedError("env_placeholder", "placeholder values: " + ", ".join(placeholders))
    malformed = sorted(key for key, pattern in ENV_FORMATS.items() if not re.fullmatch(pattern, values[key]))
    if malformed:
        raise RefusedError("env_format", "malformed variables: " + ", ".join(malformed))
    if values["FOUNDRY_PROJECT_RESOURCE_ID"].split("/")[2].lower() != values["AZURE_SUBSCRIPTION_ID"].lower():
        raise RefusedError("env_subscription", "project resource id is outside AZURE_SUBSCRIPTION_ID")
    if values["ACR_LOGIN_SERVER"] != values["ACR_NAME"].lower() + ".azurecr.io":
        raise RefusedError("env_registry", "ACR_LOGIN_SERVER does not match ACR_NAME")
    return values


@dataclass
class Context:
    environment: str
    env: dict[str, str]
    run: RunManifest
    ledger: EvidenceLedger
    libraries: Path

    @property
    def agent(self) -> str:
        return self.run.agent or ""


def load_context(environment: str, manifest_sha256: str, action: str, *, libraries: Path,
                 env_dir: Path = ENV_DIR, records: Path = RECORDS) -> Context:
    """Env targets, then the digest-pinned run manifest binding them; only then create evidence state."""
    if not ENVIRONMENT.fullmatch(environment or ""):
        raise RefusedError("environment", "environment name must match " + ENVIRONMENT.pattern)
    env_path = env_dir / f"{environment}.env"
    if env_path.is_symlink() or not env_path.is_file():
        raise RefusedError("env_path", "environment file missing or symlinked")
    env = validate_env(parse_env(env_path.read_text()))
    run = load_run_manifest(env_dir / f"{environment}.run.json", expected_sha256=manifest_sha256, action=action,
                            allowed_root=env_dir, pins={"env_sha256": env_path}, purpose=PURPOSE,
                            series_pattern=NAME, agent_pattern=NAME)
    extra = sorted(set(run.value) - MANIFEST_KEYS)
    if extra:
        raise RefusedError("manifest_fields", "unknown manifest fields: " + ", ".join(extra))
    previous = run.value.get("previous_version")
    if previous is not None and not (isinstance(previous, str) and previous.isdigit()):
        raise RefusedError("manifest_previous", "previous_version must be a version number string or null")
    records.mkdir(exist_ok=True)
    ledger = EvidenceLedger(series_directory(records, run.series))
    run.bind(ledger)
    return Context(environment, env, run, ledger, libraries)


# --- source identity -------------------------------------------------------------------------

def _contained(path: Path, root: Path) -> Path:
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise RefusedError("source_path", "build source must be a non-symlink inside its owner")
    return path


def source_inputs(libraries: Path) -> dict[str, Path]:
    """Exact build context: app sources by suffix, vendored library packages, Dockerfile and lock."""
    files: dict[str, Path] = {}
    for path in sorted(APP.rglob("*")):
        if path.is_file() and path.suffix in APP_SUFFIXES and "__pycache__" not in path.parts \
                and path.name != "source-manifest.json":
            files["app/" + path.relative_to(APP).as_posix()] = _contained(path, APP)
    for package, relative in LIBRARY_PACKAGES.items():
        base = libraries / relative
        if not (base / "__init__.py").is_file():
            raise RefusedError("library_missing", f"library package not found: {package}")
        for path in sorted(base.rglob("*")):
            if path.is_file() and (path.suffix == ".py" or path.name == "py.typed") and "__pycache__" not in path.parts:
                files[f"lib/{package}/{path.relative_to(base).as_posix()}"] = _contained(path, libraries)
    for name in DEPLOY_FILES:
        files[name] = _contained(DEPLOY / name, DEPLOY)
    return files


def source_manifest(inputs: dict[str, Path]) -> dict[str, Any]:
    files = {name: sha256_hex(path.read_bytes()) for name, path in sorted(inputs.items())}
    return {"files": files, "sha256": sha256_hex(json.dumps(files, sort_keys=True).encode())}


def release_label(manifest: dict[str, Any]) -> str:
    """Short caller-chosen label (image tag, ledger key, eval dataset version); full digest stays the pin."""
    return validate_dataset_version("sha256-" + manifest["sha256"][:32])


def stage(inputs: dict[str, Path], manifest: dict[str, Any], directory: Path) -> Path:
    for name, path in inputs.items():
        content = path.read_bytes()
        if sha256_hex(content) != manifest["files"][name]:
            raise RefusedError("source_changed", "source changed during staging")
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (directory / "app/source-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return directory


def expected_identity(ctx: Context, deployed: dict[str, Any]) -> dict[str, str]:
    return {"source_sha256": deployed["metadata"]["source_sha256"],
            "config_sha256": deployed["metadata"]["config_sha256"],
            "agent_name": ctx.agent, "agent_version": deployed["version"]}


# --- actions ---------------------------------------------------------------------------------

def run_offline_tests() -> dict[str, Any]:
    output = io.StringIO()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    summary = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "seconds": round(time.monotonic() - started, 3)}
    if not result.wasSuccessful():
        sys.stderr.write(output.getvalue())
        raise RuntimeError("offline tests failed")
    return summary


def preflight(ctx: Context, az: Callable[[list[str]], Any], project: Any) -> dict[str, Any]:
    """Read-only: account, project, registry, pull role, model, agent ownership. Gaps refuse."""
    from composition import load_spec

    env, subscription = ctx.env, ctx.env["AZURE_SUBSCRIPTION_ID"]
    gaps: list[str] = []
    account = az(["account", "show", "--query", "{subscriptionId:id,tenantId:tenantId}"])
    if (account or {}).get("subscriptionId", "").lower() != subscription.lower() \
            or (account or {}).get("tenantId", "").lower() != env["AZURE_TENANT_ID"].lower():
        raise RefusedError("account_mismatch", "active az account differs from env; run az account set explicitly")
    found = az(["resource", "show", "--ids", env["FOUNDRY_PROJECT_RESOURCE_ID"], "--api-version", PROJECT_API_VERSION,
                "--query", "{state:properties.provisioningState,endpoints:properties.endpoints,"
                           "principal:identity.principalId}"]) or {}
    if found.get("state") != "Succeeded" or env["FOUNDRY_PROJECT_ENDPOINT"] not in (found.get("endpoints") or {}).values():
        gaps.append("project state or endpoint mismatch")
    registry = az(["acr", "show", "--subscription", subscription, "--name", env["ACR_NAME"],
                   "--query", "{id:id,loginServer:loginServer}"]) or {}
    if registry.get("loginServer") != env["ACR_LOGIN_SERVER"]:
        gaps.append("registry login server mismatch")
    principal = found.get("principal")
    if not isinstance(principal, str) or not re.fullmatch(GUID, principal):
        gaps.append("project managed identity missing")
    elif registry.get("id"):
        roles = az(["role", "assignment", "list", "--subscription", subscription, "--scope", registry["id"],
                    "--include-inherited", "--query",
                    f"[?principalId=='{principal}'].{{role:roleDefinitionName,condition:condition}}"]) or []
        if not any(role.get("role") == "AcrPull" and not role.get("condition") for role in roles):
            gaps.append("project identity lacks unconditional AcrPull on the registry (grant is out of scope here)")
    model = az(["cognitiveservices", "account", "deployment", "list", "--subscription", subscription,
                "--resource-group", env["MODEL_RESOURCE_GROUP"], "--name", env["MODEL_ACCOUNT"], "--query",
                f"[?name=='{env['MODEL_DEPLOYMENT']}'].{{name:name,state:properties.provisioningState}}"]) or []
    if len(model) != 1 or model[0].get("state") != "Succeeded":
        gaps.append("model deployment not found or not ready")
    if load_spec().model != env["MODEL_DEPLOYMENT"]:
        gaps.append("app/configuration.yaml model differs from MODEL_DEPLOYMENT")
    try:
        existing = to_plain(project.agents.get(agent_name=ctx.agent))
    except Exception as error:
        if not is_not_found(error):
            raise
        existing = None
    latest = str((((existing or {}).get("versions") or {}).get("latest") or {}).get("version")) if existing else None
    previous = ctx.run.value.get("previous_version")
    if existing is not None and previous is None and not any(ctx.ledger.directory.glob("deploy-*-active.json")):
        gaps.append("agent exists but is not owned by this series; set previous_version in the run manifest")
    if existing is None and previous is not None:
        gaps.append("previous_version set but agent is absent")
    result = {"agent_exists": existing is not None, "latest_version": latest, "gaps": gaps}
    if gaps:
        raise RefusedError("preflight_gaps", "preflight blocked: " + "; ".join(gaps))
    return result


def build(ctx: Context, az: Callable[[list[str]], Any], project: Any) -> dict[str, Any]:
    """Offline tests and preflight, then one server-side ACR build of the exact source; digest-pinned image."""
    tests = run_offline_tests()
    preflight(ctx, az, project)
    inputs = source_inputs(ctx.libraries)
    manifest = source_manifest(inputs)
    label = release_label(manifest)
    record = f"build-{label}-image.json"
    if ctx.ledger.exists(record):
        return ctx.ledger.read(record)
    env, repository = ctx.env, ctx.env["IMAGE_REPOSITORY"]
    with tempfile.TemporaryDirectory(prefix="foundry-hosted-agent-") as directory:
        stage(inputs, manifest, Path(directory))
        run_id = submit_build(az, ctx.ledger, key=label, subscription=env["AZURE_SUBSCRIPTION_ID"],
                              registry=env["ACR_NAME"], image=f"{repository}:{label}", context_dir=directory)
    run = wait_build(az, subscription=env["AZURE_SUBSCRIPTION_ID"], registry=env["ACR_NAME"], run_id=run_id)
    image = resolve_image(az, run, subscription=env["AZURE_SUBSCRIPTION_ID"], registry=env["ACR_NAME"],
                          registry_host=env["ACR_LOGIN_SERVER"], repository=repository, tag=label)
    result = {"image": image, "release": label, "run_id": run_id, "source": manifest, "tests": tests}
    ctx.ledger.retain(record, result)
    return result


def current_label(ctx: Context) -> tuple[str, dict[str, Any]]:
    manifest = source_manifest(source_inputs(ctx.libraries))
    return release_label(manifest), manifest


def _read_stage(ctx: Context, name: str, missing: str) -> dict[str, Any]:
    if not ctx.ledger.exists(name):
        raise RefusedError("stage_missing", missing)
    return ctx.ledger.read(name)


def deploy(ctx: Context, project: Any, **timing: Any) -> dict[str, Any]:
    """New immutable hosted version of the built image; waits active and reads back exact identity."""
    label, manifest = current_label(ctx)
    built = _read_stage(ctx, f"build-{label}-image.json", "no build record for the current source; run build")
    metadata = {"source_sha256": manifest["sha256"], "config_sha256": manifest["files"]["app/configuration.yaml"],
                "release": label}
    return deploy_version(project, ctx.ledger, key=label, agent_name=ctx.agent,
                          definition=hosted_definition(built["image"]), metadata=metadata,
                          previous_version=ctx.run.value.get("previous_version"),
                          previous_image=ctx.run.value.get("previous_image"), **timing)


def invoke(ctx: Context, openai_client: Any, text: str) -> dict[str, Any]:
    """One stored, version-pinned Responses call per (release, version, input); a rerun never re-infers."""
    label, _ = current_label(ctx)
    deployed = _read_stage(ctx, f"deploy-{label}-active.json", "no active deployment for the current source")
    if not isinstance(text, str) or not text.strip() or len(text) > 8192:
        raise RefusedError("invoke_input", "bounded non-empty input required")
    key = f"{label}-v{deployed['version']}-{sha256_hex(text.encode())[:16]}"
    reply = hosted_invoke(openai_client, ctx.ledger, key=key, agent_name=ctx.agent,
                          version=deployed["version"], input=text)
    if reply["response"].get("status") != "completed":
        raise VerificationError("invoke_incomplete", "response not completed; reconcile by response id, never replay")
    return {"response_id": reply["response"]["id"], "version": deployed["version"],
            "output_text": reply["output_text"], "seconds": reply["seconds"]}


def verify(ctx: Context, project: Any, openai_client: Any, bearer_token: str, http_client: Any = None) -> dict[str, Any]:
    """Active exact version, anonymous refusal, and every stored response read back with its identity."""
    label, _ = current_label(ctx)
    deployed = _read_stage(ctx, f"deploy-{label}-active.json", "no active deployment for the current source")
    actual = to_plain(project.agents.get_version(agent_name=ctx.agent, agent_version=deployed["version"]))
    readback = check_active_version(actual, version=deployed["version"],
                                    image=deployed["definition"]["container_configuration"]["image"],
                                    metadata=deployed["metadata"], definition=deployed["definition"])
    status = require_refusal(anonymous_probe(agent_responses_url(ctx.env["FOUNDRY_PROJECT_ENDPOINT"], ctx.agent),
                                             http_client=http_client))
    invocations = sorted(ctx.ledger.directory.glob(f"invoke-{label}-v{deployed['version']}-*-result.json"))
    if not invocations:
        raise RefusedError("stage_missing", "no invocation to verify; run invoke first")
    identity = expected_identity(ctx, deployed)
    stored_ids = []
    for path in invocations:
        invoked = ctx.ledger.read(path.name)["response"]
        stored = read_stored_response(openai_client, invoked["id"], bearer_token=bearer_token, http_client=http_client)
        if stored is None:
            raise VerificationError("stored_response_missing", "stored response absent")
        if stored.get("status") != "completed" or stored.get("output") != invoked.get("output"):
            raise VerificationError("stored_response_drift", "stored response status or output differs")
        check_identity(stored.get("metadata"), identity, what="stored response metadata")
        stored_ids.append(invoked["id"])
    return {"version": readback, "anonymous_status": status, "stored_responses": stored_ids, "identity": identity}


def teardown(ctx: Context, project: Any, openai_client: Any, bearer_token: str, *, execute: bool,
             http_client: Any = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Owned responses -> sessions -> versions, then agent read-back. `execute=False` plans only."""
    ledger = ctx.ledger
    response_ids = [ledger.read(path.name)["response"]["id"]
                    for path in sorted(ledger.directory.glob("invoke-*-result.json"))]
    versions = sorted({str(ledger.read(path.name)["version"])
                       for pattern in ("deploy-*-created.json", "deploy-*-active.json")
                       for path in ledger.directory.glob(pattern)}, key=int)
    steps = HostedTeardown(project, ledger, agent_name=ctx.agent, execute=execute, sleep=sleep)
    result = {"execute": execute,
              "responses": steps.responses(openai_client, response_ids, bearer_token=bearer_token,
                                           http_client=http_client),
              "sessions": steps.sessions(),
              "versions": steps.versions(versions)}
    if execute:
        result["agent"] = steps.agent_readback()
    return result


# --- edge ------------------------------------------------------------------------------------

@contextmanager
def cloud_clients(env: dict[str, str], agent: str):
    """Operator Entra identity through Azure CLI; no key, no secret, no retries that could replay a write."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with ExitStack() as stack:
        credential = stack.enter_context(AzureCliCredential(tenant_id=env["AZURE_TENANT_ID"], process_timeout=30))
        project = stack.enter_context(AIProjectClient(endpoint=env["FOUNDRY_PROJECT_ENDPOINT"], credential=credential,
                                                      retry_total=0, connection_timeout=15, read_timeout=150))
        openai_client = stack.enter_context(project.get_openai_client(agent_name=agent, max_retries=0, timeout=150))
        yield credential, project, openai_client


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="deploy.sh", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("test", *CLOUD_ACTIONS))
    parser.add_argument("-e", "--environment", help="env/<environment>.env and env/<environment>.run.json")
    parser.add_argument("--manifest-sha256", help="reviewed SHA-256 of env/<environment>.run.json")
    parser.add_argument("--authorize-cloud-write", action="store_true",
                        help="explicit authorization for build, deploy, invoke and executed teardown")
    parser.add_argument("--plan", action="store_true", help="teardown: read and record the plan only")
    parser.add_argument("--input", default="How many words are in: hello from a Foundry hosted agent",
                        help="invoke: text sent to the agent")
    return parser.parse_args(argv)


def refuse(message: str) -> int:
    print(json.dumps({"status": "refused", "error": message}), file=sys.stderr)
    return 2


def main(argv: list[str] | None = None, environ: dict[str, str] | os._Environ = os.environ) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.action == "test":
        print(json.dumps({"status": "complete", "action": "test", "result": run_offline_tests()}))
        return 0
    execute = args.action in WRITE_ACTIONS and not (args.action == "teardown" and args.plan)
    if execute and not args.authorize_cloud_write:
        return refuse(f"{args.action} writes to the cloud; pass --authorize-cloud-write "
                      "(or teardown --plan for a read-only plan)")
    if args.plan and (args.action != "teardown" or args.authorize_cloud_write):
        return refuse("--plan applies only to teardown and excludes --authorize-cloud-write")
    if not args.environment or not args.manifest_sha256:
        return refuse("cloud actions require -e <environment> and --manifest-sha256 <reviewed digest>")
    libraries = Path(environ.get("AGENTCRAFT_LIBRARIES") or ROOT.parents[1] / "libraries")
    try:
        ctx = load_context(args.environment, args.manifest_sha256, args.action, libraries=libraries)
    except (FoundryOpsError, ValueError, OSError) as error:
        return refuse(getattr(error, "code", type(error).__name__) + ": " + str(error))
    started, events = time.monotonic(), []
    receipt: dict[str, Any] = {"action": args.action, "environment": args.environment, "status": "blocked",
                               "manifest_sha256": ctx.run.sha256, "started_at": utc_stamp()}
    try:
        def az(arguments: list[str]) -> Any:
            return az_json(arguments, events=events)

        with cloud_clients(ctx.env, ctx.agent) as (credential, project, openai_client):
            def token() -> str:
                return credential.get_token(AI_SCOPE).token

            actions = {
                "preflight": lambda: preflight(ctx, az, project),
                "build": lambda: build(ctx, az, project),
                "deploy": lambda: deploy(ctx, project),
                "invoke": lambda: invoke(ctx, openai_client, args.input),
                "verify": lambda: verify(ctx, project, openai_client, token()),
                "teardown": lambda: teardown(ctx, project, openai_client, token(), execute=execute),
            }
            receipt["result"] = actions[args.action]()
        receipt["status"] = "complete"
    except Exception as error:
        receipt["error"] = error_summary(error)
        receipt["code"] = getattr(error, "code", None)
    receipt.update(seconds=round(time.monotonic() - started, 3), az=sanitize(events))
    retained = ctx.ledger.retain(f"{utc_stamp()}-{args.action}.json", receipt)
    print(json.dumps({"status": receipt["status"], "action": args.action, "receipt": retained["path"],
                      "code": receipt.get("code"), "seconds": receipt["seconds"]}))
    return 0 if receipt["status"] == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())
