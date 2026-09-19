"""Small, stdlib-only synthetic optimization reference service."""

from .contracts import LOCAL_OPERATOR, Refusal
from .service import OptimizationService

__all__ = ["LOCAL_OPERATOR", "OptimizationService", "Refusal"]
__version__ = "0.1.0"