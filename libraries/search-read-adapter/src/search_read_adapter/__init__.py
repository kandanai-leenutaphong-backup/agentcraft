"""Synchronous fixed-target reads; azdata owns the service transport."""

from .errors import SearchError
from .keys import safe_key
from .read import SearchReadClient

__all__ = ["SearchError", "SearchReadClient", "safe_key"]
