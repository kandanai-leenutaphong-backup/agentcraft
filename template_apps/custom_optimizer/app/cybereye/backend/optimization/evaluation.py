"""Compatibility adapter: the component's evaluator, bound to the GUIDE profile."""

from __future__ import annotations

from app.components.agent_optimization import evaluation as _evaluation

from .dataset import GRADES
from .profile import GUIDE_PROFILE, SCORER_VERSION, model_request


def score(cases, elapsed_ms, grades=GRADES):
    return _evaluation.score(cases, elapsed_ms, grades)


def audit_results(cases, grades=GRADES):
    return _evaluation.audit_results(cases, grades)


def model_predictor(client, request_builder=model_request):
    return _evaluation.model_predictor(client, request_builder)


class GradeEvaluator(_evaluation.GradeEvaluator):
    def __init__(self, dataset, predict, profile=GUIDE_PROFILE, *, knowledge_search=None) -> None:
        super().__init__(dataset, predict, profile, knowledge_search=knowledge_search)


__all__ = ["GRADES", "GradeEvaluator", "SCORER_VERSION", "audit_results", "model_predictor",
           "model_request", "score"]
