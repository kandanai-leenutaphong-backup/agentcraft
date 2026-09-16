from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.parser import Parser
from pathlib import Path
from typing import Callable

from resource_group import DeploymentError, ResourceGroupDeployment, Target, azure_cli, permits


DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parent
APP_SOURCE = ROOT / "doc_app"
TAGS = {"managed-by": "agentcraft-deploy", "capability": "writeup", "purpose": "project-testing"}


def load_config(path: Path) -> dict:
    def unique_object(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise DeploymentError("Duplicate writeup target field.")
            values[key] = value
        return values

    values = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    uuid = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
    patterns = {
        "subscription_id": uuid, "tenant_id": uuid, "resource_group": r"rg-agentcraft-testing",
        "location": r"eastus2", "cloud": r"AzureCloud", "name": r"[a-z][a-z0-9-]{2,23}",
        "registry_name": r"[a-z0-9]{5,50}", "auth_client_id": uuid,
        "auth_registration_object_id": uuid, "auth_tenant_id": uuid,
    }
    if (not isinstance(values, dict) or set(values) != set(patterns)
            or any(not isinstance(values[key], str) or not re.fullmatch(pattern, values[key])
                   for key, pattern in patterns.items())):
        raise DeploymentError("Writeup configuration requires only validated non-secret target fields.")
    project = Target.load(DIRECTORY / "env" / "agentcraft-testing.env")
    for key in ("subscription_id", "tenant_id", "resource_group", "location", "cloud"):
        if values[key] != getattr(project, key):
            raise DeploymentError("Writeup target must match the project testing environment.")
    return values


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class WriteupDeployment:
    def __init__(self, config: dict, cli: Callable = azure_cli) -> None:
        self.config = config
        self.cli = cli
        self.project = Target.load(DIRECTORY / "env" / "agentcraft-testing.env")
        self.commands: list[dict] = []
        self.observations: dict = {}

    @property
    def app_name(self) -> str:
        return "ca-" + self.config["name"]

    @property
    def group_arguments(self) -> tuple[str, ...]:
        return ("--resource-group", self.project.resource_group, "--subscription", self.project.subscription_id)

    def call(self, *arguments: str, timeout_seconds: float = 180):
        self.commands.append({"argv": ["az", *arguments, "--only-show-errors", "--output", "json"],
                              "timeout_seconds": timeout_seconds})
        print("writeup: az " + " ".join(arguments[:3]), file=sys.stderr, flush=True)
        return self.cli(*arguments, timeout_seconds=timeout_seconds)

    def expected_resources(self) -> dict[str, str]:
        prefix = self.project.resource_id + "/providers/"
        return {
            "app": prefix + "Microsoft.App/containerApps/" + self.app_name,
            "environment": prefix + "Microsoft.App/managedEnvironments/cae-" + self.config["name"],
            "registry": prefix + "Microsoft.ContainerRegistry/registries/" + self.config["registry_name"],
            "identity": prefix + "Microsoft.ManagedIdentity/userAssignedIdentities/id-" + self.config["name"],
        }

    def preflight(self, mutation: bool) -> None:
        self.observations["project_group"] = ResourceGroupDeployment(self.project, self.call).run("verify")
        permissions = self.call(
            "rest", "--method", "get", "--url",
            f"https://management.azure.com{self.project.resource_id}/providers/Microsoft.Authorization/permissions?api-version=2022-04-01",
            "--query", "value[].{actions:actions,notActions:notActions}")
        if mutation and (not isinstance(permissions, list) or any(not permits(permissions, action) for action in (
                "Microsoft.Resources/deployments/write", "Microsoft.ContainerRegistry/registries/write",
                "Microsoft.App/managedEnvironments/write", "Microsoft.App/containerApps/write",
                "Microsoft.ManagedIdentity/userAssignedIdentities/write", "Microsoft.Authorization/roleAssignments/write"))):
            raise DeploymentError("Required deployment and resource-scoped AcrPull-assignment permissions are not reported. No operator grant is attempted.")
        resources = self.call("resource", "list", *self.group_arguments, "--query", "[].{id:id,tags:tags}")
        expected = {value.lower() for value in self.expected_resources().values()}
        if not isinstance(resources, list):
            raise DeploymentError("Resource inventory is unavailable.")
        for resource in resources:
            if resource.get("id", "").lower() in expected and any((resource.get("tags") or {}).get(key) != value for key, value in TAGS.items()):
                raise DeploymentError("A writeup resource name is already owned elsewhere; refusing adoption or retagging.")

    def template_parameters(self, application: bool, image: str = "", public_key: str = "") -> list[str]:
        return [
            f"name={self.config['name']}", f"registryName={self.config['registry_name']}",
            f"location={self.project.location}", f"deployApplication={str(application).lower()}",
            f"containerImage={image}", "ingressExternal=false", f"authClientId={self.config['auth_client_id']}",
            f"authTenantId={self.config['auth_tenant_id']}", f"signingPublicKey={public_key}",
        ]

    def apply(self, application: bool, image: str = "", public_key: str = "") -> dict:
        result = self.call(
            "deployment", "group", "create", *self.group_arguments, "--name", "agentcraft-writeup",
            "--mode", "Incremental", "--template-file", str(DIRECTORY / "infra" / "writeup.bicep"),
            "--parameters", *self.template_parameters(application, image, public_key),
            "--query", "properties.outputs", timeout_seconds=2400)
        if not isinstance(result, dict) or "url" not in result:
            raise DeploymentError("Writeup deployment did not return its expected outputs.")
        outputs = {key: value["value"] for key, value in result.items()}
        self.observations["infrastructure"] = outputs
        return outputs

    def local(self, arguments: list[str], *, capture: bool = False) -> str:
        environment = dict(os.environ)
        environment["PATH"] = str(Path.home() / ".local/node22/bin") + os.pathsep + environment.get("PATH", "")
        result = subprocess.run(arguments, cwd=APP_SOURCE, env=environment, input="" if capture else None,
                                text=True, capture_output=capture, timeout=900, check=False)
        if result.returncode:
            raise DeploymentError("Local writeup build or signing command failed; no credential output is included.")
        return result.stdout if capture else ""

    def public_key(self) -> str:
        if not (Path.home() / ".writeup/dev_signing_key").is_file():
            raise DeploymentError("Existing writeup operator key is required; no new key or agent identity is created automatically.")
        value = self.local([sys.executable, "deploy/dev_sign.py", "init"], capture=True).strip()
        match = re.fullmatch(r"DEV_PUBLIC_KEY_ED25519=([A-Za-z0-9+/]{43}=)", value)
        if match is None:
            raise DeploymentError("Could not derive the existing public verifier.")
        return match.group(1)

    def configure_callback(self, url: str) -> None:
        self.validate_url(url)
        query = "{id:id,appId:appId,signInAudience:signInAudience,web:web,requiredResourceAccess:requiredResourceAccess}"
        registration = self.call("ad", "app", "show", "--id", self.config["auth_client_id"], "--query", query)
        if (registration.get("id") != self.config["auth_registration_object_id"]
                or registration.get("appId") != self.config["auth_client_id"]
                or registration.get("signInAudience") != "AzureADMultipleOrgs"
                or registration.get("web", {}).get("implicitGrantSettings", {}).get("enableIdTokenIssuance") is not True):
            raise DeploymentError("The retained writeup registration no longer matches the inspected sign-in contract.")
        callback = url + "/.auth/login/aad/callback"
        web = registration["web"]
        previous = list(web.get("redirectUris") or [])
        if callback not in previous:
            updated_web = {**web, "redirectUris": [*previous, callback]}
            self.call("rest", "--method", "patch", "--url",
                      f"https://graph.microsoft.com/v1.0/applications/{self.config['auth_registration_object_id']}",
                      "--body", json.dumps({"web": updated_web}, separators=(",", ":")))
        current = self.call("ad", "app", "show", "--id", self.config["auth_client_id"], "--query", query)
        if (set(current.get("web", {}).get("redirectUris", [])) != set(previous + [callback])
                or current.get("requiredResourceAccess") != registration.get("requiredResourceAccess")
                or current.get("signInAudience") != registration["signInAudience"]
                or current.get("web", {}).get("implicitGrantSettings") != web.get("implicitGrantSettings")):
            raise DeploymentError("Callback read-back failed or registration permissions/sign-in settings changed.")
        self.observations["registration"] = {"client_id": self.config["auth_client_id"], "callback": callback,
                                             "callback_added": callback not in previous, "api_permissions_changed": False,
                                             "client_secret_created": False, "mode": "native-id-token-only-implicit"}

    def validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or not re.fullmatch(re.escape(self.app_name) + r"\.[a-z0-9-]+\." + re.escape(self.project.location)
                                    + r"\.azurecontainerapps\.io", parsed.netloc)):
            raise DeploymentError("Refusing a URL outside the exact writeup app and Azure region.")

    def snapshot(self) -> dict:
        app = self.call("containerapp", "show", *self.group_arguments, "--name", self.app_name, "--query",
                        "{id:id,tags:tags,state:properties.provisioningState,runningStatus:properties.runningStatus,revision:properties.latestReadyRevisionName,ingress:properties.configuration.ingress,registries:properties.configuration.registries,scale:properties.template.scale,containers:properties.template.containers[].{name:name,image:image,resources:resources,environmentVariableNames:env[].name}}")
        auth = self.call("rest", "--method", "get", "--url",
                         f"https://management.azure.com{self.expected_resources()['app']}/authConfigs/current?api-version=2024-03-01",
                         "--query", "properties")
        registry = self.call("acr", "show", *self.group_arguments, "--name", self.config["registry_name"], "--query",
                             "{id:id,sku:sku.name,adminUserEnabled:adminUserEnabled,anonymousPullEnabled:anonymousPullEnabled,loginServer:loginServer}")
        expected_issuer = f"https://login.microsoftonline.com/{self.config['auth_tenant_id']}/v2.0"
        registration = auth.get("identityProviders", {}).get("azureActiveDirectory", {}).get("registration", {})
        if (app.get("id", "").lower() != self.expected_resources()["app"].lower() or app.get("state") != "Succeeded"
                or app.get("scale", {}).get("maxReplicas") != 1 or app.get("ingress", {}).get("allowInsecure") is not False
                or auth.get("platform", {}).get("enabled") is not True
                or auth.get("globalValidation", {}).get("unauthenticatedClientAction") != "AllowAnonymous"
                or registration.get("clientId") != self.config["auth_client_id"]
                or registration.get("openIdIssuer") != expected_issuer
                or registry.get("adminUserEnabled") is not False or registry.get("anonymousPullEnabled") is not False):
            raise DeploymentError("Writeup resource, auth or registry security read-back failed; do not expose ingress.")
        snapshot = {"app": app, "auth": auth, "registry": registry}
        self.observations["deployed"] = snapshot
        return snapshot

    def signed_headers(self, path: str) -> dict[str, str]:
        raw = self.local([sys.executable, "deploy/dev_sign.py", "sign", "GET", path], capture=True)
        return dict(Parser().parsestr(raw).items())

    def verify_http(self, url: str) -> dict:
        self.validate_url(url)
        opener = urllib.request.build_opener(NoRedirect())

        def request(path: str, headers: dict | None = None):
            try:
                response = opener.open(urllib.request.Request(url + path, headers=headers or {}), timeout=90)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, dict(response.headers.items()), response.read()

        checks = {}
        for name, path, headers, expected in (
                ("health", "/healthz", {}, 200), ("anonymous_document", "/index.html", {}, 401),
                ("anonymous_browser", "/", {"Accept": "text/html"}, 302),
                ("anonymous_asset", "/identity.js", {}, 401), ("unknown_path", "/does-not-exist", {}, 401),
                ("forged_principal", "/index.html", {"X-MS-CLIENT-PRINCIPAL-ID": "not-a-user"}, 401),
                ("forged_session", "/index.html", {"Cookie": "dev_session=forged.invalid"}, 401)):
            status, _, _ = request(path, headers)
            checks[name] = status
            if status != expected:
                raise DeploymentError(f"Live writeup check {name} expected {expected}, received {status}.")
        headers = self.signed_headers("/index.html")
        status, _, body = request("/index.html", headers)
        digest = hashlib.sha256(body).hexdigest()
        expected_digest = hashlib.sha256((APP_SOURCE / "docs/dist/index.html").read_bytes()).hexdigest()
        if status != 200 or digest != expected_digest:
            raise DeploymentError("Signed live content does not match the local production build.")
        checks["signed_document"] = status
        checks["document_sha256"] = digest
        for name, path in (("signature_replay", "/index.html"), ("signature_wrong_path", "/identity.js")):
            status, _, _ = request(path, headers)
            checks[name] = status
            if status != 401:
                raise DeploymentError(f"Live writeup check {name} was not refused.")
        status, response_headers, _ = request("/.auth/login/aad")
        location = response_headers.get("Location", response_headers.get("location", ""))
        authorize = urllib.parse.urlsplit(location)
        parameters = urllib.parse.parse_qs(authorize.query)
        if (status != 302 or authorize.hostname != "login.microsoftonline.com"
                or not authorize.path.startswith("/" + self.config["auth_tenant_id"] + "/")
                or parameters.get("client_id") != [self.config["auth_client_id"]]
                or parameters.get("redirect_uri") != [url + "/.auth/login/aad/callback"]
                or not parameters.get("state") or not parameters.get("nonce")):
            raise DeploymentError("Native sign-in redirect does not match tenant, audience, callback, state and nonce.")
        checks["entra_login_redirect"] = status
        checks["entra_response_type"] = parameters.get("response_type")
        checks["interactive_user_signin_verified"] = False
        self.observations["http_verification"] = checks
        return checks

    def deploy(self) -> dict:
        public_key = self.public_key()
        self.local(["bash", "deploy/stage_demo.sh"])
        self.local(["npm", "run", "build"])
        self.local(["node", "dataset_prep/scripts/sync.mjs", "--check"])
        outputs = self.apply(False)
        self.configure_callback(outputs["url"])
        tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        registry = self.config["registry_name"]
        self.call("acr", "build", "--subscription", self.project.subscription_id, "--registry", registry,
                  "--image", "writeup-base:1", "--file", str(APP_SOURCE / "deploy/Dockerfile.base"),
                  "--no-logs", str(APP_SOURCE), timeout_seconds=1800)
        self.call("acr", "build", "--subscription", self.project.subscription_id, "--registry", registry,
                  "--image", "writeup:" + tag, "--file", str(APP_SOURCE / "deploy/Dockerfile"),
                  "--build-arg", "BASE=" + outputs["registryLoginServer"] + "/writeup-base:1",
                  "--no-logs", str(APP_SOURCE), timeout_seconds=1800)
        image = outputs["registryLoginServer"] + "/writeup:" + tag
        self.apply(True, image, public_key)
        self.snapshot()
        self.call("containerapp", "ingress", "enable", *self.group_arguments, "--name", self.app_name,
                  "--type", "external", "--target-port", "8080", "--transport", "auto", timeout_seconds=600)
        try:
            snapshot = self.snapshot()
            url = "https://" + snapshot["app"]["ingress"]["fqdn"]
            self.verify_http(url)
        except (DeploymentError, OSError, ValueError, KeyError):
            self.call("containerapp", "ingress", "disable", *self.group_arguments, "--name", self.app_name, timeout_seconds=600)
            raise
        return {"action": "deployed", "url": url, "image": image, "read_back_verified": True}

    def run(self, action: str, confirmation: str | None = None) -> dict:
        if action not in {"plan", "deploy", "verify"}:
            raise DeploymentError("Unsupported writeup action.")
        if action == "deploy" and confirmation != self.project.resource_id:
            raise DeploymentError(f"Explicit target confirmation required: --confirm {self.project.resource_id}")
        self.preflight(action == "deploy")
        if action == "plan":
            return {"action": "plan", "resources": self.expected_resources(), "registry_sku": "Basic",
                    "application_count": 1, "max_replicas": 1, "logs_destination": "none",
                    "auth_mode": "native-id-token-only-implicit", "auth_tenant_id": self.config["auth_tenant_id"],
                    "registration_change": "append-only-new-callback-no-new-api-permissions",
                    "scope": "writeup-and-required-hosting-only", "confirmation_required": self.project.resource_id}
        if action == "deploy":
            return self.deploy()
        snapshot = self.snapshot()
        url = "https://" + snapshot["app"]["ingress"]["fqdn"]
        self.verify_http(url)
        return {"action": "verified", "url": url, "read_back_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy only the protected writeup to the Agentcraft testing group.")
    parser.add_argument("action", choices=("plan", "deploy", "verify"))
    parser.add_argument("--confirm")
    parser.add_argument("--record", type=Path, required=True)
    options = parser.parse_args()
    receipt = None
    runner = None
    try:
        record = options.record.resolve()
        if record.parent != DIRECTORY / "records" or record.suffix != ".json":
            raise DeploymentError("Receipt must be a new JSON file directly under deploy/records.")
        receipt = record.open("x", encoding="utf-8")
        runner = WriteupDeployment(load_config(DIRECTORY / "env/writeup.json"))
        result = runner.run(options.action, options.confirm)
        status = 0
    except (DeploymentError, OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        result = {"action": options.action, "read_back_verified": False,
                  "error": str(error) if isinstance(error, DeploymentError) else "Writeup command failed; inspect recorded phase before retrying."}
        status = 1
    result.update({"schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                   "commands": runner.commands if runner else [], "observations": runner.observations if runner else {}})
    if receipt is not None:
        with receipt:
            json.dump(result, receipt, indent=2)
            receipt.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"commands", "observations"}}, indent=2),
          file=sys.stdout if status == 0 else sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())