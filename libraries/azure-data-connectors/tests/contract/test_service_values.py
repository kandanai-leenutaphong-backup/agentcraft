import unittest
from datetime import datetime, timezone
from decimal import Decimal

from azdata import ConfigurationError, ConnectorConfig, ContentValue, CreateRequest, Limits, RecordInput, RecordKey, ResourceAddress
from azdata.contracts import serialized
from azdata.execution import content_bytes, validate_request
from azdata.transport import OperationFault
from azdata import Policy, QueryRequest, ReadRequest, connect


class ServiceValueTests(unittest.TestCase):
    def test_native_parameters_are_opt_in_and_nonfinite_values_refuse(self):
        request = QueryRequest(dialect="postgresql", expression="SELECT id FROM Records WHERE price=:price", parameters={"price": Decimal("1.20")})
        validate_request("query", request, Limits(), "id", None, native_parameters=True)
        with self.assertRaises(OperationFault):
            validate_request("query", request, Limits(), "id", None)
        with self.assertRaises(OperationFault):
            content_bytes(ContentValue({"price": Decimal("NaN")}, kind="row"))

    def test_scalar_keys_do_not_conflate_boolean_and_integer(self):
        request = CreateRequest(records=(RecordInput(RecordKey({"id": 1}), ContentValue({"id": True})),))
        with self.assertRaises(OperationFault):
            validate_request("create", request, Limits(), "id", None, scalar_keys=True)

    def test_content_type_cannot_inject_headers_or_change_json_semantics(self):
        for content in (ContentValue(b"one", kind="bytes", media_type="text/plain\r\nx-extra: value"),
                        ContentValue({"id": "one"}, media_type="application/octet-stream")):
            with self.assertRaises(OperationFault):
                content_bytes(content)

    def test_composite_keys_and_entity_types_are_opt_in(self):
        request = CreateRequest(records=(RecordInput(RecordKey({"PartitionKey": "run", "RowKey": "one"}),
            ContentValue({"quantity": 2, "created": datetime(2026, 9, 15, tzinfo=timezone.utc)}, kind="entity")),))
        validate_request("create", request, Limits(), "id", None,
                         key_fields=("PartitionKey", "RowKey"), content_kinds=("entity",))
        with self.assertRaises(OperationFault):
            validate_request("create", request, Limits(), "id", None)

    def test_binary_input_is_bounded_and_not_stringified(self):
        content = ContentValue(b"\x00\xff", kind="bytes", media_type="application/octet-stream")
        self.assertEqual(content_bytes(content), b"\x00\xff")
        request = CreateRequest(records=(RecordInput(RecordKey({"id": "blob"}), content),))
        validate_request("create", request, Limits(), "id", None, content_kinds=("bytes",))
        with self.assertRaises(OperationFault):
            validate_request("create", request, Limits(), "id", None)

    def test_native_values_have_explicit_serialization_tags(self):
        self.assertEqual(serialized(Decimal("1.20")), {"type": "decimal", "value": "1.20"})

    def test_database_origins_never_contain_credentials(self):
        config = ConnectorConfig("postgresql://unit.postgres.database.azure.com:5432", ResourceAddress({"database": "fixture"}),
                                 ("unit.postgres.database.azure.com",), database_user="fixture-user")
        self.assertEqual(config.database_user, "fixture-user")
        with self.assertRaises(ConfigurationError):
            ConnectorConfig("postgresql://user:password@unit.postgres.database.azure.com", config.target, config.allowed_hosts)


if __name__ == "__main__":
    unittest.main()