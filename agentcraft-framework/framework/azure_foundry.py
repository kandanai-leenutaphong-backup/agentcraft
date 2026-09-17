"""Minimal Azure account Responses call, distilled from llm_interface.providers."""

import asyncio
from urllib.parse import urlsplit

import httpx
from azure.identity.aio import get_bearer_token_provider
from openai import AsyncOpenAI


async def respond(prompt: str, *, endpoint: str, deployment: str, credential) -> str:
    """Borrow an async Azure credential; return completed text or raise."""
    target = urlsplit(endpoint)
    if (
        target.scheme != "https"
        or not target.hostname
        or not target.hostname.endswith((".openai.azure.com", ".services.ai.azure.com"))
        or target.username is not None
        or target.password is not None
        or target.port not in (None, 443)
        or target.query
        or target.fragment
        or target.path.rstrip("/") not in ("", "/openai/v1")
    ):
        raise ValueError("Use an Azure account HTTPS origin or /openai/v1 endpoint.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("A nonempty prompt is required.")
    if not isinstance(deployment, str) or not deployment.strip():
        raise ValueError("A deployment name is required.")

    token = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    async with asyncio.timeout(120), httpx.AsyncClient(
        trust_env=False, follow_redirects=False, timeout=120
    ) as http:
        async with AsyncOpenAI(
            base_url=f"https://{target.netloc}/openai/v1/",
            api_key=token,
            http_client=http,
            organization="",
            project="",
            max_retries=0,
            timeout=120,
        ) as client:
            response = await client.responses.create(
                model=deployment, input=prompt, max_output_tokens=128, store=False
            )
            if response.status != "completed":
                raise RuntimeError("Model response did not complete.")
            if any(
                content.type == "refusal"
                for item in response.output if item.type == "message"
                for content in item.content
            ):
                raise RuntimeError("Model refused the request.")
            if not response.output_text:
                raise RuntimeError("Model returned no text.")
            return response.output_text