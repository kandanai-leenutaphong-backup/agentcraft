import hashlib
import asyncio
import json
import site
import ssl
import subprocess
from pathlib import Path
import tempfile
import tarfile
import io
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import nullcontext
from types import SimpleNamespace

from deploy import experiment
from foundry_ops.errors import UnresolvedIntentError, VerificationError
from foundry_ops.logs import log_messages

from composition import ROOT, load_spec
from proof_tools import nonce_digest, nonce_statistics, nonce_reverse
from main import parse_input, validate_events


class ConfigurationTests(unittest.TestCase):
    def test_finish_build_refuses_foreign_run_tag_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            source = {"sha256": "source", "files": {}}
            with tarfile.open(archive, "w:gz") as bundle:
                payload = json.dumps(source).encode()
                member = tarfile.TarInfo("app/source-manifest.json")
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))
            image = {"registry": experiment.TARGET["registry_host"],
                     "repository": experiment.TARGET["image_repository"], "tag": "gap-own", "digest": "sha256:own"}
            run = {"runId": "owned", "status": "Succeeded", "outputImages": [image]}
            cases = ((dict(run, runId="foreign"), {"digest": "sha256:own"}, "run identity"),
                     (dict(run, outputImages=[dict(image, tag="gap-other")]), {"digest": "sha256:own"}, "pinned tag"),
                     (run, {"digest": "sha256:other"}, "digest drift"))
            with patch.object(experiment, "ROOT", root), patch.object(experiment, "RECORDS", root):
                for observed, stored, message in cases:
                    with self.subTest(message=message), patch.object(experiment, "cli", side_effect=[observed, stored]):
                        with self.assertRaisesRegex(ValueError, message):
                            experiment.finish_build(source, archive, "owned", "gap-own")
                with patch.object(experiment, "cli", side_effect=[run, {"digest": "sha256:own"}]):
                    self.assertEqual(experiment.finish_build(source, archive, "owned", "gap-own")["acr_run"]["runId"], "owned")

    def test_overlap_two_direct_ids_and_unknown_stops_writes(self):
        for dropped in (False, True):
            with self.subTest(dropped=dropped), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                records = root / "records"
                records.mkdir()
                archive = records / "frozen.tar.gz"
                content = b"FROM scratch\n"
                source = {"sha256": "frozen", "files": {"Dockerfile": experiment.digest(content)}}
                with tarfile.open(archive, "w:gz") as bundle:
                    for name, payload in (("Dockerfile", content), ("app/source-manifest.json", json.dumps(source).encode())):
                        member = tarfile.TarInfo(name)
                        member.size = len(payload)
                        bundle.addfile(member, io.BytesIO(payload))
                request = {"tags": ["gap-first", "gap-second"], "source_sha256": "frozen",
                           "archive": "records/frozen.tar.gz", "archive_sha256": experiment.digest(archive.read_bytes())}
                calls = []
                def queue(arguments):
                    calls.append(arguments)
                    self.assertTrue((records / "build-overlap-intent.json").exists())
                    return None if dropped else {"runId": "direct" + str(len(calls))}
                def finish(source, retained, run_id, tag):
                    self.assertEqual(len(calls), 2)
                    return {"acr_run": {"runId": run_id, "startTime": "2026-09-22T19:00:00Z",
                                       "finishTime": "2026-09-22T19:01:00Z"}, "tag": tag}
                with patch.object(experiment, "ROOT", root), patch.object(experiment, "DEPLOY", root), \
                     patch.object(experiment, "RECORDS", records), patch.object(experiment, "preflight"), \
                     patch.object(experiment, "local_checks"), patch.object(experiment, "manifest", return_value=source), \
                     patch.object(experiment, "RUN_MANIFEST", {"build_overlap": request}), \
                     patch.object(experiment, "cli", side_effect=queue), patch.object(experiment, "finish_build", side_effect=finish):
                    if dropped:
                        with self.assertRaisesRegex(RuntimeError, "not proved"):
                            experiment.build_overlap()
                        self.assertEqual(len(calls), 1)
                    else:
                        result = experiment.build_overlap()
                        self.assertEqual(result["overlap_seconds"], 60)
                        self.assertEqual([item["tag"] for item in result["builds"]], request["tags"])
                    with self.assertRaises(UnresolvedIntentError):
                        experiment.build_overlap()
                    self.assertEqual(len(calls), 1 if dropped else 2)

    def test_foreign_owner_refuses_before_provider_access(self):
        with patch.object(experiment, "project_client") as provider:
            with self.assertRaisesRegex(ValueError, "foreign agent"):
                experiment.check_version({"agent": "foreign"})
            provider.assert_not_called()

    def test_cancel_existing_response_without_inference_replay(self):
        project = self.sdk({})
        client = project.get_openai_client.return_value.__enter__.return_value
        canceled = {"id": "resp_owned", "status": "cancelled", "output": []}
        client.responses.retrieve.return_value.model_dump.return_value = canceled
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)), \
             patch.object(experiment, "read_receipt", return_value={"agent": "canary", "version": "2"}), \
             patch.object(experiment, "check_version"), patch.object(experiment, "project_client", return_value=nullcontext(project)):
            (Path(directory) / "cancel-v2-accepted-intent.json").write_text(json.dumps({"response_id": "resp_owned"}))
            self.assertTrue(experiment.cancellation_probe("receipt")["cancelled"])
            client.responses.create.assert_not_called()
            client.responses.cancel.assert_not_called()
            client.responses.retrieve.return_value.model_dump.return_value = dict(canceled, status="completed")
            with self.assertRaisesRegex(ValueError, "not proved"):
                experiment.cancellation_probe("receipt")

    def test_intent_reads_retained_and_ledger_shapes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)):
            legacy = Path(directory) / "legacy-intent.json"
            legacy.write_text(json.dumps({"response_id": "resp_old"}))
            experiment.ledger().intent("current", {"response_id": "resp_new"})
            self.assertEqual(experiment.read_intent(legacy), {"response_id": "resp_old"})
            self.assertEqual(experiment.read_intent(Path(directory) / "current-intent.json"), {"response_id": "resp_new"})

    def test_streaming_cancel_retains_identity_before_cancel(self):
        project = self.sdk({})
        client = project.get_openai_client.return_value.__enter__.return_value
        created = {"id": "resp_stream", "status": "in_progress", "output": []}
        canceled = dict(created, status="cancelled")
        event = SimpleNamespace(type="response.created", response=SimpleNamespace(model_dump=lambda **kwargs: created))
        client.responses.create.return_value.__enter__.return_value = iter([event])
        client.responses.retrieve.return_value = SimpleNamespace(model_dump=lambda **kwargs: canceled)
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)), \
             patch.object(experiment, "RUN_MANIFEST", {"series": "synthetic"}), \
             patch.object(experiment, "read_receipt", return_value={"agent": "canary", "version": "2"}), \
             patch.object(experiment, "check_version"), patch.object(experiment, "project_client", return_value=nullcontext(project)):
            def cancel(response_id):
                self.assertTrue((Path(directory) / "cancel-stream-v2-accepted.json").exists())
                return SimpleNamespace(model_dump=lambda **kwargs: canceled)
            client.responses.cancel.side_effect = cancel
            self.assertTrue(experiment.cancellation_probe("receipt", True)["cancelled"])
            client.responses.cancel.assert_called_once_with("resp_stream")
            client.responses.create.return_value.__enter__.return_value = iter([event, SimpleNamespace(type="response.content_part.added")])
            self.assertTrue(experiment.cancellation_probe("receipt", True, True)["cancelled"])
            self.assertTrue((Path(directory) / "cancel-work-v2-request-intent.json").exists())

    def test_build_cli_null_output_direct_identity_and_dropped_response(self):
        command = ["acr", "build", "--no-wait"]
        for stderr, expected in (("WARNING: Queued a build with ID: crf\n", {"runId": "crf"}),
                                 ("", None),
                                 ("WARNING: Queued a build with ID: crf\nWARNING: Queued a build with ID: foreign\n", None)):
            with patch.object(experiment.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "null", stderr)) as execute:
                self.assertEqual(experiment.cli(command), expected)
                execute.assert_called_once()

    def test_official_clients_injected_transport_and_404(self):
        import httpx
        from azure.ai.projects import AIProjectClient
        from azure.core.credentials import AccessToken
        from azure.core.exceptions import ResourceNotFoundError
        from azure.core.pipeline.transport import HttpResponse, HttpTransport
        from openai import OpenAI
        class Response(HttpResponse):
            def __init__(self, request, status, value):
                super().__init__(request, None)
                self.status_code = status
                self.headers = {"content-type": "application/json"}
                self.content_type = "application/json"
                self.payload = json.dumps(value).encode()
            def body(self):
                return self.payload
            def text(self, encoding=None):
                return self.payload.decode(encoding or "utf-8")
            def json(self):
                return json.loads(self.payload)
        transport = MagicMock(spec=HttpTransport)
        requests = []
        def send(request, **kwargs):
            requests.append(request)
            if "/versions/2" in request.url:
                return Response(request, 200, {"id": "agent", "name": "canary", "version": "2", "definition": {"kind": "hosted"}})
            return Response(request, 404, {"error": {"code": "NotFound", "message": "missing"}})
        transport.send.side_effect = send
        credential = SimpleNamespace(get_token=lambda *args, **kwargs: AccessToken("offline", 4102444800))
        with AIProjectClient("https://offline.services.ai.azure.com/api/projects/test", credential, transport=transport, retry_total=0) as project:
            self.assertEqual(project.agents.get_version("canary", "2").version, "2")
            with self.assertRaises(ResourceNotFoundError):
                project.agents.get("missing")
        self.assertEqual(len(requests), 2)
        submitted = []
        def response(request):
            submitted.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "resp_offline", "object": "response", "created_at": 1,
                "model": "canary", "status": "completed", "output": [], "parallel_tool_calls": False,
                "tool_choice": "auto", "tools": []})
        with OpenAI(api_key="offline-not-a-secret", base_url="https://offline.invalid", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(response))) as client:
            client.responses.create(input="canary", extra_body={"agent_reference": {"type": "agent_reference", "name": "canary", "version": "2"}})
        self.assertEqual(submitted[0]["agent_reference"]["version"], "2")

    def test_log_stream_utf8_multiline_malformed_and_bounds(self):
        payload = b'data: {"message":\r\ndata: "Error \xc3\xa9"}\r\n\r\ndata: not-json\n\n'
        self.assertEqual(list(log_messages([payload[index:index + 1] for index in range(len(payload))])), ["Error \u00e9"])
        with self.assertRaises(ValueError):
            list(log_messages([payload], max_bytes=2))
        with self.assertRaises(ValueError):
            list(log_messages([payload], max_events=0))
        with self.assertRaises(UnicodeDecodeError):
            list(log_messages([b"\xc3"]))

    def test_stored_metadata_and_anonymous_success_refuse(self):
        project = self.sdk({})
        client = project.get_openai_client.return_value.__enter__.return_value
        client.responses.retrieve.return_value.model_dump.return_value = {"status": "completed", "output": [], "metadata": {"foreign": "value"}}
        invocation = {"deployed": {}, "response_id": "resp_1", "response_output": [], "response_metadata": {}}
        with patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value=invocation), \
             patch.object(experiment, "check_version"), patch.object(experiment, "project_client", return_value=nullcontext(project)):
            with self.assertRaisesRegex(ValueError, "text/metadata"):
                experiment.verify("receipt")
            invocation.update(response_metadata=None, nonce="a1" * 16, envelope={}, anonymous_status=401)
            client.responses.retrieve.return_value.model_dump.return_value = {"status": "completed", "output": [], "metadata": {}}
            with patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value=invocation), \
                 patch.object(experiment, "check_version"), patch.object(experiment, "verify_response", return_value={}), \
                 patch.object(experiment, "project_client", return_value=nullcontext(project)):
                self.assertTrue(experiment.verify("receipt")["readback"])
        with patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value={}), \
             patch.object(experiment, "check_version"), patch.object(experiment, "anonymous_probe", return_value=200), \
               patch.object(experiment, "RUN_MANIFEST", None), \
             patch.object(experiment, "project_client") as connect:
            with self.assertRaisesRegex(VerificationError, "anonymous refusal"):
                experiment.invoke("receipt")
            connect.assert_not_called()

    def test_native_handler_cancellation_model_and_tool(self):
        import main
        from contextlib import ExitStack
        from azure.ai.agentserver.responses import ResponsesAgentServerHost
        captured = []
        credential = AsyncMock()
        original = ResponsesAgentServerHost.response_handler

        def register(server, function):
            captured.append(function)
            return original(server, function)

        with ExitStack() as stack:
            stack.enter_context(patch.object(ResponsesAgentServerHost, "response_handler", register))
            stack.enter_context(patch("azure.identity.aio.DefaultAzureCredential", return_value=credential))
            stack.enter_context(patch("azure.ai.agentserver.responses.TextResponse", side_effect=lambda context, request, text: text))
            main.create_server("https://smoke.invalid/api/projects/smoke", {}, configure_observability=None)

        async def exercise(phase):
            signal, entered = asyncio.Event(), asyncio.Event()
            actions = []

            async def work(*args):
                try:
                    actions.append(phase)
                    entered.set()
                    await asyncio.Event().wait()
                    actions.append("subsequent-dispatch")
                finally:
                    actions.append("closed")

            credential.reset_mock()
            with patch("azure.identity.aio.DefaultAzureCredential", return_value=credential), patch.object(main, "execute_proof", work):
                produce = await captured[0](None, SimpleNamespace(response_id="synthetic-cancellation", get_input_text=AsyncMock(return_value="a1" * 16)), signal)
                self.assertEqual(actions, [])
                task = asyncio.create_task(produce())
                await asyncio.wait_for(entered.wait(), 2)
                signal.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
            self.assertEqual(actions, [phase, "closed"])
            credential.__aexit__.assert_awaited_once()
            self.assertEqual(len([task for task in asyncio.all_tasks() if task is not asyncio.current_task()]), 0)

        for phase in ("model", "tool"):
            asyncio.run(exercise(phase))

    def test_build_direct_identity_without_inventory_race(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "Dockerfile"
            source_file.write_text("FROM scratch\n")
            source = {"sha256": "source", "files": {name: experiment.digest(source_file.read_bytes()) for name in ("Dockerfile", "app/main.py")}}
            with patch.object(experiment, "RECORDS", root), patch.object(experiment, "ROOT", root), \
                 patch.object(experiment, "preflight"), patch.object(experiment, "local_checks"), \
                 patch.object(experiment, "manifest", return_value=source), \
                 patch.object(experiment, "source_inputs", return_value={"Dockerfile": source_file, "app/main.py": source_file}), \
                 patch.object(experiment, "cli", return_value={"runId": "direct123"}) as command, \
                 patch.object(experiment, "finish_build", return_value={"ok": True}) as finish:
                experiment.build()
                self.assertEqual(finish.call_args.args[2], "direct123")
                self.assertEqual(command.call_count, 1)
                self.assertEqual(command.call_args.args[0][:2], ["acr", "build"])
                with self.assertRaises(UnresolvedIntentError):
                    experiment.build()
                self.assertEqual(command.call_count, 1)

    def test_build_dropped_response_refuses_second_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "Dockerfile"
            source_file.write_text("FROM scratch\n")
            source = {"sha256": "source", "files": {name: experiment.digest(source_file.read_bytes()) for name in ("Dockerfile", "app/main.py")}}
            with patch.object(experiment, "RECORDS", root), patch.object(experiment, "ROOT", root), \
                 patch.object(experiment, "preflight"), patch.object(experiment, "local_checks"), \
                 patch.object(experiment, "manifest", return_value=source), \
                 patch.object(experiment, "source_inputs", return_value={"Dockerfile": source_file, "app/main.py": source_file}), \
                 patch.object(experiment, "cli", return_value=None) as command, patch.object(experiment, "finish_build") as finish:
                with self.assertRaisesRegex(RuntimeError, "unknown"):
                    experiment.build()
                with self.assertRaises(UnresolvedIntentError):
                    experiment.build()
                command.assert_called_once()
                finish.assert_not_called()

    def test_manifest_digest_and_historical_refusal(self):
        path = experiment.DEPLOY / "env/migration-h-v1.json"
        with self.assertRaises(ValueError):
            experiment.configure_run(path, "0" * 64, "build")
        with self.assertRaises(ValueError):
            experiment.configure_run(path, experiment.digest(path.read_bytes()), "grant-pull")

    def sdk(self, value):
        project = MagicMock()
        project.agents.get.return_value.as_dict.return_value = value
        project.agents.get_version.return_value.as_dict.return_value = value
        return project

    def test_explicit_older_version_invocation(self):
        project = self.sdk({})
        client = project.get_openai_client.return_value.__enter__.return_value
        client.responses.create.return_value = SimpleNamespace(
            model_dump=lambda **kwargs: {"id": "resp_1", "status": "completed"}, output_text="")
        deployed = {"agent": experiment.TARGET["agent_name"], "version": "2"}
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)), \
             patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value=deployed), \
             patch.object(experiment, "check_version"), patch.object(experiment, "anonymous_probe", return_value=401), \
             patch.object(experiment, "verify_response", return_value={}), \
             patch.object(experiment, "project_client", return_value=nullcontext(project)):
            experiment.invoke("receipt")
        self.assertEqual(client.responses.create.call_args.kwargs["extra_body"]["agent_reference"]["version"], "2")
        self.assertEqual(project.get_openai_client.call_args.kwargs["max_retries"], 0)

    def test_unknown_create_never_repeated(self):
        from azure.core.exceptions import ResourceNotFoundError
        project = self.sdk({})
        project.agents.get.side_effect = ResourceNotFoundError()
        project.agents.create_version.side_effect = TimeoutError("unknown")
        built = {"image": "registry/image@sha256:immutable", "source": {"sha256": "source", "files": {"app/configuration.yaml": "config"}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)), \
             patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value=built), \
             patch.object(experiment, "project_client", side_effect=lambda: nullcontext(project)):
            with self.assertRaises(TimeoutError):
                experiment.deploy("build")
            with self.assertRaises(UnresolvedIntentError):
                experiment.deploy("build")
        self.assertEqual(project.agents.create_version.call_count, 1)

    def test_sdk_session_enumeration(self):
        project = self.sdk({"name": experiment.TARGET["agent_name"]})
        project.agents.list_versions.return_value = []
        project.agents.list_sessions.return_value = [SimpleNamespace(as_dict=lambda: {"agent_session_id": "first"}),
                                                    SimpleNamespace(as_dict=lambda: {"agent_session_id": "second"})]
        with patch.object(experiment, "preflight"), patch.object(experiment, "project_client", return_value=nullcontext(project)):
            self.assertEqual(len(experiment.inspect_agent()["sessions"]["result"]["data"]), 2)

    def test_install_refuses_unreviewed_profile(self):
        with patch.object(experiment.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "reviewed uv profile"):
                experiment.install()
            command.assert_not_called()

    def test_locked_install_dry_run_vector(self):
        lock = experiment.DEPLOY / "host-requirements.lock"
        with patch.object(experiment.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command:
            result = experiment.install(site.getusersitepackages(), experiment.digest(lock.read_bytes()), True)
        vector = command.call_args.args[0]
        self.assertEqual(vector[:4], ["uv", "--no-config", "pip", "install"])
        for flag in ("--no-python-downloads", "--no-build-isolation", "--require-hashes", "--no-index", "--target", "--dry-run"):
            self.assertIn(flag, vector)
        for flag in ("--no-deps", "--break-system-packages", "--upgrade", "--user", "--exact"):
            self.assertNotIn(flag, vector)
        self.assertTrue(result["dry_run"])

    def test_locked_install_foreign_target_refused(self):
        lock = experiment.DEPLOY / "host-requirements.lock"
        with patch.object(experiment.subprocess, "run") as command:
            with self.assertRaisesRegex(ValueError, "containment"):
                experiment.install("/usr/lib/python3/dist-packages", experiment.digest(lock.read_bytes()), True)
            command.assert_not_called()

    def test_image_dependency_contract(self):
        docker = (experiment.DEPLOY / "Dockerfile").read_text()
        self.assertEqual(docker.count("@sha256:"), 2)
        self.assertNotIn("RUN pip", docker)
        self.assertIn("--require-hashes", docker)
        self.assertIn("--no-index", docker)
        self.assertIn("uv pip freeze --python /usr/local/bin/python", docker)
        manifest = json.loads((experiment.DEPLOY / "dependency-manifest.json").read_text())
        self.assertEqual(manifest["runtime_lock_sha256"], experiment.digest((experiment.DEPLOY / "runtime-requirements.lock").read_bytes()))
        self.assertTrue(any(name.startswith("llm_interface-") for name in manifest["wheels"]))

    def test_new_tool_configuration_and_result(self):
        spec = load_spec()
        self.assertEqual([function.__name__ for function in spec.tools], ["nonce_digest", "nonce_statistics", "nonce_reverse"])
        self.assertEqual(spec.tools[1]("ff" * 16), {
            "marker": "foundry-custom-script-v2-statistics", "nonce": "ff" * 16,
            "byte_sum": 4080, "set_bits": 128})
        with self.assertRaises(ValueError):
            nonce_statistics("invalid")
        self.assertEqual(nonce_reverse("00112233445566778899aabbccddeeff")["reversed_hex"], "ffeeddccbbaa99887766554433221100")
        with self.assertRaises(ValueError):
            nonce_reverse("invalid")

    def test_explicit_tool_input_refusals(self):
        nonce = "00" * 16
        self.assertEqual(parse_input('{"tool":"nonce_statistics","nonce":"' + nonce + '"}'), ("nonce_statistics", nonce))
        self.assertEqual(parse_input(nonce), ("nonce_digest", nonce))
        for text in ('{"tool":"os.system","nonce":"' + nonce + '"}', '{"tool":"nonce_statistics"}',
                     '{"tool":"nonce_statistics","nonce":"' + nonce + '","extra":1}'):
            with self.assertRaises(ValueError):
                parse_input(text)

    def test_new_tool_evidence_rejects_old_tool(self):
        expected = nonce_statistics("ff" * 16)
        events = [
            {"kind": "tool.call.ready", "data": {"name": "nonce_statistics", "call_id": "call_new", "arguments": {"nonce": expected["nonce"]}}},
            {"kind": "tool.started", "data": {"name": "nonce_statistics", "call_id": "call_new"}},
            {"kind": "tool.result", "data": {"call_id": "call_new", "result": expected}},
        ]
        validate_events(events, expected, "nonce_statistics")
        with self.assertRaises(ValueError):
            validate_events(events, expected, "nonce_digest")

    def test_real_hosting_sdk_compatibility(self):
        from deploy.compatibility import check

        self.assertEqual(check()["readiness"], 200)

    def test_platform_tls_remains_verified(self):
        from main import create_server

        with patch("main.ssl.create_default_context", wraps=ssl.create_default_context) as context:
            create_server("https://smoke.invalid/api/projects/smoke", {}, configure_observability=None)
            context.assert_called_once_with()
        verified = ssl.create_default_context()
        self.assertEqual(verified.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(verified.check_hostname)

    def test_positive_custom_script(self):
        spec = load_spec()
        nonce = "a1" * 16
        result = spec.tools[0](nonce)
        self.assertEqual(result, {
            "marker": "foundry-custom-script-v1", "nonce": nonce,
            "sha256": hashlib.sha256(("foundry-custom-script-v1:" + nonce).encode()).hexdigest(),
        })

    def test_invalid_nonce(self):
        for nonce in ("", "../secret", "f" * 33, None):
            with self.subTest(nonce=nonce), self.assertRaises(ValueError):
                nonce_digest(nonce)

    def test_native_maf_schema(self):
        from agent_framework import tool

        schema = tool(nonce_digest).to_json_schema_spec()
        self.assertEqual(schema["function"]["name"], "nonce_digest")
        self.assertEqual(schema["function"]["parameters"]["required"], ["nonce"])

    def test_build_source_allowlist(self):
        sources = experiment.source_inputs()
        self.assertIn("app/configuration.yaml", sources)
        self.assertTrue(all("records/" not in name and "__pycache__" not in name for name in sources))
        self.assertEqual(experiment.manifest(), experiment.manifest())

    def test_foreign_receipt_refused(self):
        with self.assertRaises(ValueError):
            experiment.read_receipt("/tmp/foreign-receipt.json", "build")

    def test_target_mismatch_refused(self):
        with patch.object(experiment, "prerequisites", return_value={"gaps": []}), patch.object(
            experiment, "cli", return_value={"subscriptionId": "foreign"}
        ) as command:
            with self.assertRaisesRegex(ValueError, "account mismatch"):
                experiment.preflight()
            self.assertEqual(command.call_count, 1)

    def test_build_stops_before_mutation(self):
        with patch.object(experiment, "preflight", side_effect=RuntimeError("blocked")), patch.object(experiment, "cli") as command:
            with self.assertRaises(RuntimeError):
                experiment.build()
            command.assert_not_called()

    def test_pull_role_semantics_refuse_broad_role(self):
        with patch.object(experiment, "preflight", return_value={"project_registry_roles": []}), patch.object(
            experiment, "cli", return_value=[{"id": experiment.PULL_ROLE, "name": "AcrPull", "permissions": []}]
        ) as command:
            with self.assertRaisesRegex(ValueError, "semantics"):
                experiment.grant_pull()
            self.assertEqual(command.call_count, 1)

    def test_existing_exact_pull_grant_is_read_only(self):
        scope = experiment.TARGET["registry_id"]
        definition = [{"id": experiment.PULL_ROLE, "name": "AcrPull", "permissions": [{
            "actions": ["Microsoft.ContainerRegistry/registries/pull/read"],
            "notActions": [], "dataActions": [], "notDataActions": [],
            "condition": None, "conditionVersion": None}]}]
        assignment = {"scope": scope, "principalId": experiment.PROJECT_PRINCIPAL,
                      "roleDefinitionId": "/roles/" + experiment.PULL_ROLE, "condition": None}
        with patch.object(experiment, "preflight", return_value={"project_registry_roles": [
            {"scope": scope, "role": "AcrPull", "condition": None}]}), patch.object(
            experiment, "cli", side_effect=[definition, [assignment]]
        ) as command:
            self.assertFalse(experiment.grant_pull()["created"])
            self.assertEqual(command.call_count, 2)

    def test_inactive_version_refused(self):
        deployed = {"version": "1", "definition": {"kind": "hosted", "cpu": "1", "memory": "2Gi",
                    "protocol_versions": [], "container_configuration": {"image": "registry/image@sha256:test"}}}
        with patch.object(experiment, "project_client", return_value=nullcontext(self.sdk({"version": "1", "status": "creating", "definition": deployed["definition"]}))):
            with self.assertRaises(VerificationError):
                experiment.check_version(deployed)

    def test_existing_name_without_owned_receipt_refused(self):
        built = {"image": "registry/image@sha256:immutable", "source": {"sha256": "source", "files": {"app/configuration.yaml": "config"}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(experiment, "RECORDS", Path(directory)), \
             patch.object(experiment, "preflight"), patch.object(experiment, "read_receipt", return_value=built), patch.object(
            experiment, "project_client", return_value=nullcontext(self.sdk({"name": experiment.TARGET["agent_name"]}))
        ) as request:
            with self.assertRaisesRegex(ValueError, "explicit owned"):
                experiment.deploy("build")
            self.assertEqual(request.call_count, 1)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_active_image_drift_refused(self):
        definition = {"kind": "hosted", "cpu": "1", "memory": "2Gi", "protocol_versions": [],
                      "container_configuration": {"image": "registry/image@sha256:expected"}}
        actual = {**definition, "container_configuration": {"image": "registry/image@sha256:foreign"}}
        with patch.object(experiment, "project_client", return_value=nullcontext(self.sdk({"version": "1", "status": "active", "definition": actual}))):
            with self.assertRaises(VerificationError):
                experiment.check_version({"version": "1", "definition": definition})

    def test_unknown_tool(self):
        self.assert_bad_config((ROOT / "configuration.yaml").read_text().replace(
            "proof_tools:nonce_digest", "os:system"))

    def test_duplicate_yaml_key(self):
        self.assert_bad_config("agents: {}\nagents: {}\n")

    def test_unknown_field(self):
        self.assert_bad_config((ROOT / "configuration.yaml").read_text() + "credential: forbidden\n")

    def test_tool_evidence(self):
        expected = nonce_digest("a1" * 16)
        events = [
            {"kind": "tool.call.ready", "data": {"name": "nonce_digest", "call_id": "call_1", "arguments": {"nonce": expected["nonce"]}}},
            {"kind": "tool.started", "data": {"name": "nonce_digest", "call_id": "call_1"}},
            {"kind": "tool.result", "data": {"call_id": "call_1", "result": expected}},
        ]
        validate_events(events, expected)
        with self.assertRaises(ValueError):
            validate_events([], expected)
        events[2]["data"]["call_id"] = "different"
        with self.assertRaises(ValueError):
            validate_events(events, expected)

    def assert_bad_config(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configuration.yaml"
            path.write_text(content)
            with self.assertRaises(ValueError):
                load_spec(path)


if __name__ == "__main__":
    unittest.main()