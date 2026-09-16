"""Compatibility adapter: the component terminal, bound to the GUIDE task text."""

from __future__ import annotations

from pathlib import Path

from agent_optimization import HELPER, cli as _cli

from .profile import (
    FULL_TASK,
    GUIDE_TASKS,
    STRESS_TASK,
    TASK,
    TERMINAL_API_PATH,
    WORKFLOW_TASK,
)


class OptimizationTerminal(_cli.OptimizationTerminal):
    def __init__(self, service, *, cli: str, endpoint: str, model: str, workspace_root: Path,
                 token_provider, path: str, api_origin: str, tasks=GUIDE_TASKS,
                 api_path: str = TERMINAL_API_PATH) -> None:
        super().__init__(service, cli=cli, endpoint=endpoint, model=model, workspace_root=workspace_root,
                         token_provider=token_provider, path=path, api_origin=api_origin,
                         tasks=tasks, api_path=api_path)


__all__ = ["FULL_TASK", "HELPER", "OptimizationTerminal", "STRESS_TASK", "TASK", "WORKFLOW_TASK"]
