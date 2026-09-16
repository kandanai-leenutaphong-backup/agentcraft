from __future__ import annotations

import asyncio
import hashlib
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from azure.identity import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from llm_interface import Capabilities, Limits, connect

from .api.optimization import router
from .config import Settings, settings
from .knowledge import Knowledge, describe_capabilities
from .optimization.cli import OptimizationTerminal
from .optimization.dataset import GuideDataset
from .optimization.evaluation import model_predictor
from .optimization.python_tools import PythonToolRunner
from .optimization.service import OptimizationService
from .security import LOCAL_PRINCIPAL, LocalGate


def create_app(configuration: Settings = settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        cleanup = AsyncExitStack()
        terminal_cleanup = AsyncExitStack()
        cleanup_lock = asyncio.Lock()
        service = None
        closed = False
        application.state.optimization_cleanup_complete = False

        async def close_resources():
            nonlocal closed
            async with cleanup_lock:
                if closed:
                    return
                try:
                    await terminal_cleanup.aclose()
                finally:
                    if service is not None:
                        await asyncio.to_thread(service.close)
                    await cleanup.aclose()
                closed = True
                application.state.optimization_cleanup_complete = True

        application.state.optimization_resources = cleanup
        application.state.optimization_cleanup = close_resources
        try:
            loop = asyncio.get_running_loop()

            def from_worker(operation, timeout):
                def invoke(*args):
                    try:
                        if asyncio.get_running_loop() is loop:
                            raise RuntimeError("worker_callback_called_on_host_loop")
                    except RuntimeError as error:
                        if str(error) != "no running event loop":
                            raise
                    pending = asyncio.run_coroutine_threadsafe(operation(*args), loop)
                    try:
                        return pending.result(timeout=timeout)
                    except BaseException:
                        pending.cancel()
                        raise
                return invoke

            credential = cleanup.enter_context(DefaultAzureCredential(exclude_interactive_browser_credential=True))
            try:
                dataset = GuideDataset(Path(configuration.guide_data_dir),
                                       Path(configuration.optimization_dir) / "contexts",
                                       PythonToolRunner(configuration.python_sandbox))
                model = connect(configuration.openai_endpoint, configuration.model, credential=credential,
                    allow_model_calls=configuration.allow_model_calls, allowed_tools=(),
                    capabilities=Capabilities(reasoning=True),
                    limits=Limits(timeout_seconds=45, max_model_calls=1, max_output_tokens=1200,
                                  max_concurrency=32, max_input_bytes=1_048_576))
                cleanup.push_async_callback(model.aclose)
                knowledge = Knowledge(configuration.search_endpoint, configuration.knowledge_index, credential)
                cleanup.push_async_callback(knowledge.aclose)
                reference = {"name": "search_mitre_attack",
                             "source_digest": hashlib.sha256(Path(__file__).with_name("knowledge.py").read_bytes()).hexdigest(),
                             "endpoint": configuration.search_endpoint, "index": configuration.knowledge_index,
                             "access": "read-only advisory retrieval"}
                service = OptimizationService(dataset, Path(configuration.optimization_dir) / "experiments",
                                              configuration.model, from_worker(model_predictor(model, principal=LOCAL_PRINCIPAL.id), 47),
                                              knowledge_search=from_worker(knowledge.search, 32), knowledge_reference=reference,
                                              capability_catalogue=lambda caller, experiment: describe_capabilities(
                                                  dataset.describe(), experiment, knowledge))
                def token():
                    if not configuration.allow_model_calls:
                        raise PermissionError("model_calls_not_granted")
                    value = credential.get_token("https://cognitiveservices.azure.com/.default")
                    return value.token, float(value.expires_on)
                terminal = OptimizationTerminal(service, cli=configuration.copilot_cli,
                                                endpoint=configuration.openai_endpoint, model=configuration.model,
                                                workspace_root=Path(configuration.copilot_workspace_dir),
                                                token_provider=token, path=configuration.command_path,
                                                api_origin=configuration.local_api_origin)
                terminal_cleanup.callback(terminal.close)
                application.state.optimization = service
                application.state.optimization_terminal = terminal
                application.state.knowledge = knowledge
            except (OSError, ValueError) as error:
                application.state.optimization = None
                application.state.optimization_error = f"Optimizer configuration unavailable: {type(error).__name__}"
            yield
        finally:
            await close_resources()

    application = FastAPI(title="Custom Optimizer", lifespan=lifespan)
    application.add_middleware(LocalGate)
    application.include_router(router)

    @application.get("/healthz")
    async def health():
        return {"status": "ok"}

    frontend = Path(__file__).resolve().parents[3] / "frontend/dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()