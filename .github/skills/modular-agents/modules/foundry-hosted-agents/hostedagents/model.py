"""Official OpenAI SDK adapter; the credential is supplied by the runtime edge."""

from __future__ import annotations

import asyncio
from typing import Any

from .policy import RuntimeTarget

MODEL_SCOPE = "https://cognitiveservices.azure.com/.default"


class OpenAIModel:
    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_credential(cls, target: RuntimeTarget, credential: Any) -> OpenAIModel:
        from openai import AsyncOpenAI

        async def token() -> str:
            issued = await asyncio.to_thread(credential.get_token, MODEL_SCOPE)
            return issued.token

        return cls(AsyncOpenAI(
            base_url=target.model_endpoint, api_key=token, max_retries=0, timeout=120,
        ))

    async def complete(
        self, *, model: str, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]], max_tokens: int,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "model": model, "messages": messages, "max_completion_tokens": max_tokens,
        }
        if tools:
            options.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
        response = await self.client.chat.completions.create(**options)
        if not response.choices:
            raise RuntimeError("model response contains no choices")
        message = response.choices[0].message
        return {
            "content": message.content,
            "tool_calls": [call.model_dump(exclude_none=True) for call in message.tool_calls or []],
        }

    async def close(self) -> None:
        await self.client.close()