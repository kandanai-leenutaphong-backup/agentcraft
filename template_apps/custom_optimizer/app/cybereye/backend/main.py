from __future__ import annotations

import asyncio
import hashlib
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from azure.identity import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from template_foundations.azure_llm import AzureLlmClient, LlmConfig

from .api.optimization import router
from .config import Settings, settings
from .knowledge import Knowledge, describe_capabilities
from .optimization.cli import OptimizationTerminal
from .optimization.dataset import GuideDataset
from .optimization.evaluation import model_predictor
from .optimization.python_tools import PythonToolRunner
from .optimization.service import OptimizationService
from .security import LocalGate


def create_app(configuration: Settings = settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        async with AsyncExitStack() as cleanup:
            credential = cleanup.enter_context(DefaultAzureCredential(exclude_interactive_browser_credential=True))
            try:
                dataset = GuideDataset(Path(configuration.guide_data_dir),
                                       Path(configuration.optimization_dir) / "contexts",
                                       PythonToolRunner(configuration.python_sandbox))
                model = AzureLlmClient(LlmConfig(endpoint=configuration.openai_endpoint,
                                               model=configuration.model, timeout_seconds=45, max_retries=1),
                                       credential=credential)
                cleanup.callback(model.client.close)
                knowledge = Knowledge(configuration.search_endpoint, configuration.knowledge_index, credential)
                cleanup.push_async_callback(asyncio.to_thread, knowledge.close)
                reference = {"name": "search_mitre_attack",
                             "source_digest": hashlib.sha256(Path(__file__).with_name("knowledge.py").read_bytes()).hexdigest(),
                             "endpoint": configuration.search_endpoint, "index": configuration.knowledge_index,
                             "access": "read-only advisory retrieval"}
                service = OptimizationService(dataset, Path(configuration.optimization_dir) / "experiments",
                                              configuration.model, model_predictor(model.client),
                                              knowledge_search=knowledge.search, knowledge_reference=reference,
                                              capability_catalogue=lambda caller, experiment: describe_capabilities(
                                                  dataset.describe(), experiment, knowledge))
                cleanup.callback(service.close)
                def token():
                    value = credential.get_token("https://cognitiveservices.azure.com/.default")
                    return value.token, float(value.expires_on)
                terminal = OptimizationTerminal(service, cli=configuration.copilot_cli,
                                                endpoint=configuration.openai_endpoint, model=configuration.model,
                                                workspace_root=Path(configuration.copilot_workspace_dir),
                                                token_provider=token, path=configuration.command_path,
                                                api_origin=configuration.local_api_origin)
                cleanup.callback(terminal.close)
                application.state.optimization = service
                application.state.optimization_terminal = terminal
                application.state.knowledge = knowledge
            except (OSError, ValueError) as error:
                application.state.optimization = None
                application.state.optimization_error = f"Optimizer configuration unavailable: {type(error).__name__}"
            yield

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