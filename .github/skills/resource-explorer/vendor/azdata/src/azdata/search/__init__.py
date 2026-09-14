"""Azure AI Search — read, write, deploy, observe and verify planes.

``read.py`` queries an index, ``write.py`` mutates documents in one,
``deploy.py`` provisions the service and the index themselves,
``observe.py`` reports index and service counters, ``verify.py``
enumerates the document key space so a change can be diffed, and
``discover.py`` lists indexes and their field schema.
"""

from __future__ import annotations

from azdata.search.deploy import SearchIndexProvisioner, SearchServiceProvisioner
from azdata.search.discover import MAX_FIELD_DEPTH, SearchDiscoverer
from azdata.search.observe import SearchStats
from azdata.search.read import SearchConnector
from azdata.search.verify import SearchKeys
from azdata.search.write import SearchDocuments

__all__ = [
    "MAX_FIELD_DEPTH",
    "SearchConnector",
    "SearchDiscoverer",
    "SearchDocuments",
    "SearchIndexProvisioner",
    "SearchKeys",
    "SearchServiceProvisioner",
    "SearchStats",
]
