"""Translate the hosted operator target and policy into one native model binding."""

from llm_interface import connect

from .policy import RuntimePolicy, RuntimeTarget


def connect_model(target: RuntimeTarget, policy: RuntimePolicy, *, model: str, credential):
    return connect(
        target.model_endpoint, model, credential=credential,
        provider="azure_completions", policy=policy.execution_policy(),
    )