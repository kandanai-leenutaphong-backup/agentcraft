import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lifecycle
from fakes import DIGEST, LOGIN, REPOSITORY, VALID_ENV, FakeAz, FakeHttp, FakeOpenAI, FakeProject
from foundry_ops.core import RefusedError, UnresolvedIntentError, VerificationError, sha256_hex
from foundry_ops.evaluation import validate_dataset_version
from foundry_ops.hosting import hosted_definition

DEPLOY_SH = lifecycle.DEPLOY / "deploy.sh"
LIBRARIES = Path(os.environ.get("AGENTCRAFT_LIBRARIES") or lifecycle.ROOT.parents[1] / "libraries")
ACTIONS = list(lifecycle.CLOUD_ACTIONS)


def env_text(values):
    return "".join(f"{key}={value}\n" for key, value in values.items())


class Workspace:
    """Temporary env dir + records root with a valid env and a run manifest pinning it."""

    def __init__(self, directory, values=None, actions=ACTIONS, **extra):
        self.root = Path(directory)
        self.env_dir, self.records = self.root / "env", self.root / "records"
        self.env_dir.mkdir()
        self.env = self.env_dir / "dev.env"
        self.env.write_text(env_text(values or VALID_ENV))
        manifest = {"schema_version": 1, "purpose": "foundry-hosted-agent", "series": "dev-v1",
                    "agent": "example-hosted-agent", "actions": list(actions),
                    "env_sha256": sha256_hex(self.env.read_bytes()), "previous_version": None,
                    "previous_image": None, **extra}
        self.manifest = self.env_dir / "dev.run.json"
        self.manifest.write_text(json.dumps(manifest, sort_keys=True))
        self.sha = sha256_hex(self.manifest.read_bytes())

    def context(self, action, sha=None):
        return lifecycle.load_context("dev", sha or self.sha, action, libraries=LIBRARIES,
                                      env_dir=self.env_dir, records=self.records)


class EnvTests(unittest.TestCase):
    def test_example_env_documents_every_target_and_is_not_runnable(self):
        values = lifecycle.parse_env((lifecycle.ENV_DIR / "example.env").read_text())
        self.assertEqual(set(values), set(lifecycle.ENV_FORMATS))
        with self.assertRaises(RefusedError) as refused:
            lifecycle.validate_env(values)
        self.assertEqual(refused.exception.code, "env_placeholder")

    def test_example_manifest_pins_example_env(self):
        manifest = json.loads((lifecycle.ENV_DIR / "example.run.json").read_text())
        self.assertEqual(manifest["env_sha256"], sha256_hex((lifecycle.ENV_DIR / "example.env").read_bytes()))
        self.assertEqual(set(manifest), lifecycle.MANIFEST_KEYS)

    def test_valid_env_accepted(self):
        self.assertEqual(lifecycle.validate_env(dict(VALID_ENV)), VALID_ENV)

    def test_secret_shaped_values_refused_without_echo(self):
        cases = {
            "MODEL_DEPLOYMENT": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
            "FOUNDRY_PROJECT_ENDPOINT": VALID_ENV["FOUNDRY_PROJECT_ENDPOINT"] + "?sig=abcdef",
            "IMAGE_REPOSITORY": "DefaultEndpointsProtocol=https;AccountName=x;AccountKey=abc",
            "MODEL_ACCOUNT": "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4==",
            "ACR_NAME": "-----BEGIN PRIVATE KEY-----",
        }
        for key, value in cases.items():
            with self.subTest(key=key), self.assertRaises(RefusedError) as refused:
                lifecycle.validate_env({**VALID_ENV, key: value})
            self.assertEqual(refused.exception.code, "env_secret")
            self.assertNotIn(value, str(refused.exception))
        for name in ("CLIENT_SECRET", "STORAGE_ACCOUNT_KEY", "OPENAI_API_KEY", "SEARCH_TOKEN"):
            with self.subTest(name=name), self.assertRaises(RefusedError) as refused:
                lifecycle.validate_env({**VALID_ENV, name: "anything"})
            self.assertEqual(refused.exception.code, "env_secret")

    def test_auth_disable_agent_access_unknown_and_malformed_refused(self):
        for extra, code in (({"AUTH_ENABLED": "false"}, "env_auth_disabled"),
                            ({"SIGNED_DEV_ACCESS": "true"}, "env_agent_access"),
                            ({"EXTRA_TARGET": "x"}, "env_unknown"),
                            ({"FOUNDRY_PROJECT_ENDPOINT": "http://fake.services.ai.azure.com/api/projects/p"}, "env_format"),
                            ({"ACR_LOGIN_SERVER": "other.azurecr.io"}, "env_registry")):
            with self.subTest(code=code), self.assertRaises(RefusedError) as refused:
                lifecycle.validate_env({**VALID_ENV, **extra})
            self.assertEqual(refused.exception.code, code)
        missing = dict(VALID_ENV)
        missing.pop("MODEL_DEPLOYMENT")
        with self.assertRaises(RefusedError):
            lifecycle.validate_env(missing)

    def test_env_syntax_refused(self):
        for text in ("export A=1\n", "A=1\nA=2\n", "lower=1\n", "NOVALUE\n"):
            with self.subTest(text=text), self.assertRaises(RefusedError):
                lifecycle.parse_env(text)


class ManifestTests(unittest.TestCase):
    def test_valid_context_binds_manifest_once(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(directory)
            ctx = workspace.context("preflight")
            self.assertEqual((ctx.agent, ctx.run.series), ("example-hosted-agent", "dev-v1"))
            self.assertTrue((workspace.records / "dev-v1" / "run-manifest.json").exists())
            workspace.context("build")

    def test_refusals_before_any_evidence_state(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(directory, actions=["preflight"])
            for action, sha, code in (("preflight", "0" * 64, "manifest_digest"),
                                      ("build", None, "manifest_action")):
                with self.subTest(code=code), self.assertRaises(RefusedError) as refused:
                    workspace.context(action, sha)
                self.assertEqual(refused.exception.code, code)
            workspace.env.write_text(env_text({**VALID_ENV, "MODEL_DEPLOYMENT": "drifted"}))
            with self.assertRaises(RefusedError) as refused:
                workspace.context("preflight")
            self.assertEqual(refused.exception.code, "manifest_pin")
            self.assertFalse(workspace.records.exists())

    def test_unknown_manifest_field_and_foreign_agent_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RefusedError) as refused:
                Workspace(directory, grant_roles=True).context("preflight")
            self.assertEqual(refused.exception.code, "manifest_fields")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RefusedError) as refused:
                Workspace(directory, agent="Foreign_Agent").context("preflight")
            self.assertEqual(refused.exception.code, "manifest_agent")

    def test_version_label_over_fifty_characters_refused_by_library(self):
        label = lifecycle.release_label({"sha256": "f" * 64, "package_sha256": "e" * 64})
        self.assertEqual((label, len(label)), ("src-" + "f" * 24 + "-pkg-" + "e" * 16, 49))
        self.assertEqual(validate_dataset_version("x" * 50), "x" * 50)
        with self.assertRaises(RefusedError) as refused:
            validate_dataset_version("x" * 51)
        self.assertEqual(refused.exception.code, "dataset_version")

    def test_mutable_image_refused_by_library(self):
        with self.assertRaises(RefusedError):
            hosted_definition(f"{LOGIN}/{REPOSITORY}:latest")


class SourceTests(unittest.TestCase):
    def test_allowlisted_deterministic_source(self):
        inputs = lifecycle.source_inputs(LIBRARIES)
        for name in ("app/main.py", "app/composition.py", "app/tool_calls.py", "package/configuration.yaml",
                     "package/agent_tools.py", "package/prompts/agent.md",
                     "lib/llm_interface/__init__.py", "lib/agentconfig/__init__.py",
                     "lib/agentcraft_core/__init__.py", "Dockerfile", "runtime-requirements.lock"):
            self.assertIn(name, inputs)
        self.assertFalse([name for name in inputs if "tests/" in name or "__pycache__" in name
                          or name.startswith(("deploy/", "records", "app/prompts/"))
                          or name in ("app/configuration.yaml", "app/agent_tools.py")])
        self.assertEqual(lifecycle.source_manifest(inputs), lifecycle.source_manifest(lifecycle.source_inputs(LIBRARIES)))

    def test_staged_context_carries_package_identity(self):
        inputs = lifecycle.source_inputs(LIBRARIES)
        manifest = lifecycle.source_manifest(inputs)
        with tempfile.TemporaryDirectory() as directory:
            lifecycle.stage(inputs, manifest, Path(directory))
            staged = Path(directory)
            recorded = json.loads((staged / "app/source-manifest.json").read_text())
            package = {path.relative_to(staged / "package").as_posix(): sha256_hex(path.read_bytes())
                       for path in (staged / "package").rglob("*") if path.is_file()}
        self.assertEqual(recorded, manifest)
        self.assertEqual(recorded["package_files"], package)
        self.assertEqual(recorded["package_sha256"], sha256_hex(json.dumps(package, sort_keys=True).encode()))
        self.assertEqual(recorded["config_sha256"], package["configuration.yaml"])

    def test_dockerfile_uses_uv_on_system_interpreter_with_hashes(self):
        docker = (lifecycle.DEPLOY / "Dockerfile").read_text()
        self.assertEqual(docker.count("@sha256:"), 2)
        self.assertIn("uv --no-config pip install --python /usr/local/bin/python", docker)
        for flag in ("--require-hashes", "--only-binary :all:", "--no-python-downloads"):
            self.assertIn(flag, docker)
        for forbidden in ("RUN pip", "python -m pip", "venv", "--break-system-packages", "--system"):
            self.assertNotIn(forbidden, docker)
        self.assertIn("RUN python main.py --self-check", docker)
        for line in ("WORKDIR /app", "COPY app /app", "COPY package /app/package", "AGENT_PACKAGE_DIR=/app/package"):
            self.assertIn(line, docker)

    def test_lock_consistent_with_pins(self):
        lock = (lifecycle.DEPLOY / "runtime-requirements.lock").read_text()
        entries = [line.split(" ", 1)[0] for line in lock.splitlines() if line[:1].isalnum()]
        pins = [line.strip() for line in (lifecycle.DEPLOY / "runtime-requirements.in").read_text().splitlines()
                if line.strip() and not line.startswith("#")]
        self.assertEqual(sorted(set(pins) - set(entries)), [])
        self.assertFalse([entry for entry in entries if entry.split("==")[0] in
                          {"agentcraft-core", "llm-interface", "modular-agents"}])
        blocks = lock.split("\n")
        for index, line in enumerate(blocks):
            if line[:1].isalnum():
                self.assertIn("--hash=sha256:", blocks[index + 1], line)


class LifecycleTests(unittest.TestCase):
    """Whole lifecycle over fakes: identity, refusal and teardown order."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.directory.name)
        self.log, self.store = [], {}
        self.az, self.project = FakeAz(), FakeProject(self.log)
        self.openai, self.http = FakeOpenAI(self.store, self.log), FakeHttp(self.store)
        self.tests = patch.object(lifecycle, "run_offline_tests", return_value={"tests": 0})
        self.tests.start()

    def tearDown(self):
        self.tests.stop()
        self.directory.cleanup()

    def built_and_deployed(self, ctx):
        built = lifecycle.build(ctx, self.az, self.project)
        deployed = lifecycle.deploy(ctx, self.project, sleep=lambda seconds: None)
        self.openai.responses.metadata = lifecycle.expected_identity(ctx, deployed)
        return built, deployed

    def test_full_lifecycle_and_teardown_order(self):
        ctx = self.workspace.context("build")
        self.assertFalse(lifecycle.preflight(ctx, self.az, self.project)["agent_exists"])
        with self.assertRaises(RefusedError):
            lifecycle.deploy(ctx, self.project)
        built, deployed = self.built_and_deployed(ctx)
        self.assertEqual(built["image"], f"{LOGIN}/{REPOSITORY}@{DIGEST}")
        self.assertIn("app/source-manifest.json", self.az.staged)
        self.assertIn("lib/llm_interface/__init__.py", self.az.staged)
        self.assertEqual(deployed["version"], "1")
        self.assertEqual(deployed["metadata"]["release"], built["release"])
        self.assertEqual(lifecycle.build(ctx, self.az, self.project), built)
        self.assertEqual(self.az.count("acr", "build"), 1)

        first = lifecycle.invoke(ctx, self.openai, "count these words please")
        again = lifecycle.invoke(ctx, self.openai, "count these words please")
        self.assertEqual(first, again)
        self.assertEqual(self.log.count("responses.create"), 1)
        request = self.openai.responses.requests[0]
        self.assertEqual(request["extra_body"]["agent_reference"],
                         {"type": "agent_reference", "name": "example-hosted-agent", "version": "1"})
        self.assertTrue(request["store"])

        verified = lifecycle.verify(ctx, self.project, self.openai, "offline-token", http_client=self.http)
        self.assertEqual(verified["anonymous_status"], 401)
        self.assertEqual(verified["stored_responses"], [first["response_id"]])
        self.assertEqual(self.http.headers[0]["Authorization"], "Bearer offline-token")
        self.assertNotIn("offline-token", "".join(path.read_text() for path in ctx.ledger.directory.iterdir()))

        plan = lifecycle.teardown(ctx, self.project, self.openai, "offline-token", execute=False, http_client=self.http)
        self.assertEqual({step["outcome"] for key in ("responses", "sessions", "versions") for step in plan[key]},
                         {"planned"})
        self.assertNotIn("responses.delete", self.log)
        done = lifecycle.teardown(ctx, self.project, self.openai, "offline-token", execute=True,
                                  http_client=self.http, sleep=lambda seconds: None)
        self.assertEqual([step["outcome"] for key in ("responses", "sessions", "versions") for step in done[key]],
                         ["deleted", "deleted", "deleted"])
        self.assertEqual(done["agent"]["outcome"], "absent")
        deletes = [entry for entry in self.log if "delete" in entry]
        self.assertEqual(deletes, ["responses.delete", "delete_session", "delete_version"])

    def test_verify_refuses_anonymous_success_and_identity_drift(self):
        ctx = self.workspace.context("build")
        self.built_and_deployed(ctx)
        lifecycle.invoke(ctx, self.openai, "hello")
        with self.assertRaises(VerificationError) as refused:
            lifecycle.verify(ctx, self.project, self.openai, "t", http_client=FakeHttp(self.store, 200))
        self.assertEqual(refused.exception.code, "anonymous_accepted")
        for response in self.store.values():
            response["metadata"] = {**response["metadata"], "agent_version": "999"}
        with self.assertRaises(VerificationError) as refused:
            lifecycle.verify(ctx, self.project, self.openai, "t", http_client=self.http)
        self.assertEqual(refused.exception.code, "identity_mismatch")
        self.store.clear()
        with self.assertRaises(VerificationError) as refused:
            lifecycle.verify(ctx, self.project, self.openai, "t", http_client=self.http)
        self.assertEqual(refused.exception.code, "stored_response_missing")

    def test_verify_ignores_null_only_fields_but_refuses_output_drift(self):
        ctx = self.workspace.context("build")
        self.built_and_deployed(ctx)
        lifecycle.invoke(ctx, self.openai, "hello")
        for response in self.store.values():
            response["output"] = [{**item, "phase": None, "namespace": None} for item in response["output"]]
        lifecycle.verify(ctx, self.project, self.openai, "t", http_client=self.http)
        for response in self.store.values():
            response["output"][0]["content"] = [{"type": "output_text", "text": "drifted"}]
        with self.assertRaises(VerificationError) as refused:
            lifecycle.verify(ctx, self.project, self.openai, "t", http_client=self.http)
        self.assertEqual(refused.exception.code, "stored_response_drift")

    def test_verify_refuses_image_drift(self):
        ctx = self.workspace.context("build")
        _, deployed = self.built_and_deployed(ctx)
        self.project.agents.versions[deployed["version"]]["definition"] = hosted_definition(
            f"{LOGIN}/{REPOSITORY}@sha256:" + "cd" * 32)
        with self.assertRaises(VerificationError):
            lifecycle.verify(ctx, self.project, self.openai, "t", http_client=self.http)

    def test_preflight_account_mismatch_stops_build_before_submission(self):
        ctx = self.workspace.context("build")
        az = FakeAz(account={"subscriptionId": "00000000-0000-0000-0000-000000000000", "tenantId": "x"})
        with self.assertRaises(RefusedError) as refused:
            lifecycle.build(ctx, az, self.project)
        self.assertEqual(refused.exception.code, "account_mismatch")
        self.assertEqual(az.count("acr", "build"), 0)

    def test_existing_unowned_agent_refused(self):
        self.project.agents.versions["7"] = {"version": "7", "status": "active"}
        ctx = self.workspace.context("build")
        with self.assertRaises(RefusedError) as refused:
            lifecycle.preflight(ctx, self.az, self.project)
        self.assertIn("not owned", str(refused.exception))

    def test_unknown_create_outcome_never_replayed(self):
        ctx = self.workspace.context("build")
        lifecycle.build(ctx, self.az, self.project)
        self.project.agents.create_version = lambda **kwargs: (_ for _ in ()).throw(TimeoutError("unknown"))
        with self.assertRaises(TimeoutError):
            lifecycle.deploy(ctx, self.project)
        with self.assertRaises(UnresolvedIntentError):
            lifecycle.deploy(ctx, self.project)


class CommandLineTests(unittest.TestCase):
    """deploy.sh refusals happen before any Azure CLI call or evidence write."""

    def run_cli(self, *arguments):
        with tempfile.TemporaryDirectory() as bin_dir:
            marker = Path(bin_dir) / "az-called"
            fake = Path(bin_dir) / "az"
            fake.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
            fake.chmod(0o755)
            environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(["bash", str(DEPLOY_SH), *arguments], capture_output=True, text=True,
                                    env=environment, timeout=120)
            self.assertFalse(marker.exists(), "az must not be called on refusal")
        return result

    def test_bash_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(DEPLOY_SH)]).returncode, 0)

    def test_cloud_actions_refuse_without_authorization_or_manifest(self):
        example_sha = sha256_hex((lifecycle.ENV_DIR / "example.run.json").read_bytes())
        before = lifecycle.RECORDS.exists() and sorted(lifecycle.RECORDS.rglob("*"))
        for arguments, message in (
                (("build", "-e", "example", "--manifest-sha256", example_sha), "--authorize-cloud-write"),
                (("deploy", "-e", "example"), "--authorize-cloud-write"),
                (("invoke", "-e", "example"), "--authorize-cloud-write"),
                (("teardown", "-e", "example"), "--authorize-cloud-write"),
                (("deploy", "-e", "example", "--authorize-cloud-write"), "--manifest-sha256"),
                (("preflight", "-e", "example"), "--manifest-sha256"),
                (("verify",), "--manifest-sha256"),
                (("teardown", "-e", "example", "--plan", "--authorize-cloud-write"), "--plan"),
                (("build", "-e", "example", "--authorize-cloud-write", "--manifest-sha256", example_sha),
                 "env_placeholder"),
                (("preflight", "-e", "missing", "--manifest-sha256", example_sha), "env_path"),
                (("preflight", "-e", "example", "--manifest-sha256", example_sha, "--env-dir", "/tmp"),
                 "env_dir_path"),
                (("preflight", "-e", "example", "--manifest-sha256", example_sha,
                  "--env-dir", str(lifecycle.ENV_DIR)), "env_placeholder")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)
        self.assertEqual(lifecycle.RECORDS.exists() and sorted(lifecycle.RECORDS.rglob("*")), before)

    def test_run_and_spec_refusals(self):
        example = lifecycle.REPO / "libraries/foundry-ops/examples/hosted_agent_e2e/run-spec.example.json"
        spec = ("--spec", str(example), "--spec-sha256", sha256_hex(example.read_bytes()))
        for arguments, message in (
                (("run",), "--authorize-cloud-write"),
                (("run", "--authorize-cloud-write"), "run requires --spec"),
                (("run", "--until", "preflight", "--authorize-cloud-write", *spec), "does not apply"),
                (("run", "--until", "nope", *spec), "stage_unknown"),
                (("run", "--until", "preflight", "--spec", str(example)), "--spec-sha256"),
                (("preflight", "-e", "example", *spec), "--spec excludes"),
                (("run", "--until", "preflight", *spec), "spec_placeholder"),
                (("promote", *spec), "--authorize-cloud-write"),
                (("verify", "--until", "verify", *spec), "--until does not apply")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
