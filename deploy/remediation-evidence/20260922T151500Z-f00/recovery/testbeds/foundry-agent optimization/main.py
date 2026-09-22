"""Native Foundry config at the edge; canonical MAF inference through llm_interface."""

import hashlib
import json
import os
import ssl

from composition import ROOT, apply_optimization, compose, load_spec


def loaded_spec(credential, config_dir=None):
    from azure.ai.agentserver.optimization import load_config
    candidate = os.environ.get("OPTIMIZATION_CANDIDATE_ID", "")
    inline = os.environ.get("OPTIMIZATION_CONFIG", "")
    config = load_config(config_dir=config_dir or ROOT / ".agent_configs", credential=credential)
    if candidate and not inline and (config is None or config.candidate_id != candidate):
        raise ValueError("requested native candidate failed to load")
    if inline and (config is None or config.source != "env:OPTIMIZATION_CONFIG"):
        raise ValueError("native inline override failed to load")
    return apply_optimization(load_spec(), config), config


async def classify(query, endpoint, credential, spec, tls_context):
    import httpx
    from llm_interface import Limits, connect
    async with httpx.AsyncHTTPTransport(verify=tls_context, trust_env=False, retries=0) as transport, connect(
        endpoint, spec.model, credential=credential, allow_model_calls=True, transport=transport,
        allowed_tools=(), limits=Limits(max_model_calls=1, max_tool_calls=1, max_output_tokens=1024,
                                       timeout_seconds=120, max_concurrency=1),
    ) as model:
        return await compose(model, spec).run(query)


def create_server(endpoint, manifest, spec, config, **options):
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse
    from azure.identity.aio import DefaultAzureCredential
    server = ResponsesAgentServerHost(**options)
    tls_context = ssl.create_default_context()
    identity = {"source_sha256": manifest["sha256"],
                "config_sha256": manifest["files"]["app/configuration.yaml"],
                "instructions_sha256": hashlib.sha256(spec.instructions.encode()).hexdigest(),
                "config_source": config.source, "candidate_id": config.candidate_id or "baseline",
                "model": spec.model, "agent_name": os.environ["FOUNDRY_AGENT_NAME"],
                "agent_version": os.environ["FOUNDRY_AGENT_VERSION"]}
    selection_path = ROOT / ".agent_configs/selection.json"
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        if selection["instructions_sha256"] != identity["instructions_sha256"]:
            raise ValueError("packaged candidate does not match loaded instructions")
        identity["applied_candidate_id"] = selection["candidate_id"]
        if "native_config_sha256" in selection:
            identity["native_config_sha256"] = selection["native_config_sha256"]

    @server.response_handler
    async def handler(request, context, _cancellation_signal):
        query = await context.get_input_text()
        if not isinstance(query, str) or not query.strip() or len(query) > 8192:
            raise ValueError("bounded nonempty classifier input required")
        async with DefaultAzureCredential(
            exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
            exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
            exclude_developer_cli_credential=True, exclude_powershell_credential=True,
        ) as credential:
            result = await classify(query, endpoint, credential, spec, tls_context)

        def configure(response):
            response.metadata = identity

        return TextResponse(context, request, text=result.text, configure=configure)

    return server


def main():
    from azure.identity import DefaultAzureCredential
    with DefaultAzureCredential(
        exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
        exclude_developer_cli_credential=True, exclude_powershell_credential=True,
    ) as credential:
        spec, config = loaded_spec(credential)
    create_server(os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                  json.loads((ROOT / "source-manifest.json").read_text()), spec, config).run()


if __name__ == "__main__":
    main()