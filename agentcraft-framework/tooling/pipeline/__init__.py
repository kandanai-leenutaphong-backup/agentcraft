from collections.abc import Callable, Iterable
from typing import Any


class Pipeline:
    """Apply functions in order, passing each output to the next function."""

    def __init__(self, functions: Iterable[Callable[[Any], Any]]):
        self.functions = tuple(functions)

    def __call__(self, data: Any) -> Any:
        for function in self.functions:
            data = function(data)
        return data