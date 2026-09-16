"""Compatibility adapter: detector versioning and the GUIDE workflow contract."""

from __future__ import annotations

from agent_optimization import detect, verify_detector, workflow as _workflow

from .profile import BASELINE_DETECTOR, KNOWLEDGE_BEHAVIOUR_CLASSES, WORKFLOW_CONTRACT


def detector_version(definition, history, created_at, scope=WORKFLOW_CONTRACT["input"]):
    return _workflow.detector_version(definition, history, created_at, scope)


def knowledge_arguments(payload, behaviour_classes=KNOWLEDGE_BEHAVIOUR_CLASSES):
    return _workflow.knowledge_arguments(payload, behaviour_classes)


__all__ = ["BASELINE_DETECTOR", "WORKFLOW_CONTRACT", "detect", "detector_version",
           "knowledge_arguments", "verify_detector"]
