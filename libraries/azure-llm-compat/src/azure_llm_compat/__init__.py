"""Azure model endpoint access: chat/responses and embeddings over one Entra ID identity.

Generalised from the CyberEye agent so any pipeline can call an Azure OpenAI
deployment without restating the credential chain. No API key is read, stored,
or accepted from configuration.
"""

from __future__ import annotations

from .client import AzureLlmClient
from .agent import stream_tool_turn
from .config import COGNITIVE_SCOPE, DEFAULT_ENV_PREFIX, LlmConfig, LlmConfigError
from .credentials import azure_credential, bearer_token_provider, set_credential_factory
from .streaming import ENVELOPE_EVENTS, response_events

__all__ = [
    "AzureLlmClient",
    "COGNITIVE_SCOPE",
    "DEFAULT_ENV_PREFIX",
    "ENVELOPE_EVENTS",
    "LlmConfig",
    "LlmConfigError",
    "azure_credential",
    "bearer_token_provider",
    "response_events",
    "set_credential_factory",
    "stream_tool_turn",
]
