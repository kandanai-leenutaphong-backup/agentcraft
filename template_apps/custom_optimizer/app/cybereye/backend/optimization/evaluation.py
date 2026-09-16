"""Compatibility adapter: the component's evaluator, bound to the GUIDE profile."""

from __future__ import annotations

from agent_optimization import evaluation as _evaluation

from .dataset import GRADES
from .profile import GUIDE_PROFILE, SCORER_VERSION, model_request
from .model import model_predictor as _model_predictor


def score(cases, elapsed_ms, grades=GRADES):
    return _evaluation.score(cases, elapsed_ms, grades)


def audit_results(cases, grades=GRADES):
    return _evaluation.audit_results(cases, grades)


def model_predictor(connection, request_builder=model_request, *, principal):
    return _model_predictor(connection, request_builder, principal=principal)


class GradeEvaluator(_evaluation.GradeEvaluator):
    def __init__(self, dataset, predict, profile=GUIDE_PROFILE, *, knowledge_search=None) -> None:
        super().__init__(dataset, predict, profile, knowledge_search=knowledge_search)


__all__ = ["GRADES", "GradeEvaluator", "SCORER_VERSION", "audit_results", "model_predictor",
           "model_request", "score"]
