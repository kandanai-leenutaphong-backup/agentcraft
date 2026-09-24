"""Foundry lifecycle glue over caller-owned official SDK clients.

Modules: `records`, `manifest`, `bounds`, `logs`, `verify`, `hosted`, `evals`, `build`, `errors`.
Importing any of them loads no Azure, OpenAI or httpx package and performs no I/O.
"""

__version__ = "0.1.0"
__all__ = ["bounds", "build", "errors", "evals", "hosted", "logs", "manifest", "records", "verify"]
