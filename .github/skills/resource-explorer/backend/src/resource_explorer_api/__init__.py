"""Resource Explorer API — a bounded, lazy tree over the ``azdata`` discover plane.

The component owns the *hierarchy*: which branches exist, in what order, how
an ARM inventory is grouped, what a node id is, and what the wire payload
looks like. Every cloud enumeration below that is ``azdata``'s, reached only
through its public top-level surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
