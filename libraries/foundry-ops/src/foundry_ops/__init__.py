"""Foundry lifecycle glue over caller-owned official SDK clients.

Stage -> subpackage (each depends only on `core`):
  foundation (errors, evidence ledger, manifests, bounds, logs, identifiers) -> `core`
  build (ACR image, digest pin)                                             -> `build`
  deploy / invoke / cancel / verify / traces / teardown                     -> `hosting`
  data (JSONL datasets: register, read back, eval/optimization references)  -> `data`
  evaluate (eval runs, rows, criteria, code evaluators, canaries)           -> `evaluation`
  optimize (jobs, candidates, configs)                                      -> `optimization`
Importing any of them loads no Azure, OpenAI or httpx package and performs no I/O.
"""

__version__ = "0.1.0"
__all__ = ["build", "core", "data", "evaluation", "hosting", "optimization"]
