"""Host-composed agent optimization: immutable generations, sandboxed tools, measured runs.

The host injects authorization, the dataset, the model and every domain fact through
`OptimizationProfile` and `TerminalTasks`. Nothing here names a use case, label or prompt.
"""

from .cli import HELPER, OptimizationTerminal
from .evaluation import GradeEvaluator, audit_results, model_predictor, score
from .profile import OptimizationProfile, TerminalTasks
from .python_tools import PythonToolRunner
from .runs import measure_run
from .service import PROTOCOLS, OptimizationService, compare_evaluation, digest, now, write_json
from .workflow import detect, detector_version, knowledge_arguments, verify_detector
from .joint import PROCESS_CONTRACT, PROCESS_VERSION, normalize_rulesets

__all__ = [
    "GradeEvaluator",
    "HELPER",
    "OptimizationProfile",
    "OptimizationService",
    "OptimizationTerminal",
    "PROTOCOLS",
    "PROCESS_CONTRACT",
    "PROCESS_VERSION",
    "normalize_rulesets",
    "PythonToolRunner",
    "TerminalTasks",
    "audit_results",
    "compare_evaluation",
    "detect",
    "detector_version",
    "digest",
    "knowledge_arguments",
    "measure_run",
    "model_predictor",
    "now",
    "score",
    "verify_detector",
    "write_json",
]
