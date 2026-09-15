from unittest import TestCase

from app.components.data_connector_library import cosmos_ensure_graph, cosmos_primary_key
from app.data.data_pipelines.ait import arm as ait
from app.data.data_pipelines.perth import arm as perth


class PipelineShimTests(TestCase):
    def test_both_pipelines_import_one_implementation(self) -> None:
        for module in (ait, perth):
            self.assertIs(module.cosmos_ensure_graph, cosmos_ensure_graph)
            self.assertIs(module.cosmos_primary_key, cosmos_primary_key)