from __future__ import annotations

import ast
import asyncio
import io
import json
import re
import time
import tokenize
from collections.abc import Mapping
from urllib.parse import parse_qs, unquote

from .base import AdapterResult, RecordAdapter
from ..contracts import Caveat, ConfigurationError, ContentValue, ItemResult, OperationCapability, plain
from ..execution import json_bytes
from ..transport import HttpResponse, OperationFault, check_response


READ_STEPS = frozenset({"V", "E", "has", "hasId", "hasLabel", "hasNot", "values", "valueMap", "elementMap", "properties",
    "id", "label", "key", "value", "out", "in", "both", "outE", "inE", "bothE", "outV", "inV", "bothV", "otherV",
    "limit", "range", "count", "dedup", "order", "by", "as", "select", "where", "not", "and", "or", "is", "filter",
    "fold", "unfold", "project", "path", "simplePath", "constant", "sum", "min", "max", "mean", "group", "groupCount"})
PREDICATES = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "within", "without", "between", "inside", "outside"})
ALIASES = {name: name + "_" for name in {"in", "as", "not", "and", "or", "is"}}


def literal(value):
    if isinstance(value, (tuple, list)):
        return "[" + ",".join(literal(item) for item in value) + "]"
    if value is None or type(value) not in (str, int, float, bool):
        raise OperationFault("unsupported", "gremlin_scalar_required")
    return json_bytes(value).decode().replace("$", "\\$")


def read_traversal(expression, parameters):
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(expression).readline))
        for index, token in enumerate(tokens):
            if token.type == tokenize.NAME and token.string in ALIASES and index and tokens[index - 1].string == ".":
                tokens[index] = token._replace(string=ALIASES[token.string])
        tree = ast.parse(tokenize.untokenize(tokens), mode="eval")
    except (SyntaxError, tokenize.TokenError, IndentationError):
        raise OperationFault("unsupported", "gremlin_traversal_subset_required") from None
    if sum(1 for node in ast.walk(tree)) > 256:
        raise OperationFault("invalid", "gremlin_traversal_complexity_limit")
    used = set()
    def render(node):
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Attribute):
                method = next((name for name, alias in ALIASES.items() if alias == node.func.attr), node.func.attr)
                if method not in READ_STEPS:
                    raise OperationFault("denied", "gremlin_mutation_or_script_refused")
                prefix = render(node.func.value) + "." + method
            elif isinstance(node.func, ast.Name) and node.func.id in PREDICATES:
                prefix = node.func.id
            else:
                raise OperationFault("denied", "gremlin_script_refused")
            return prefix + "(" + ",".join(render(argument) for argument in node.args) + ")"
        if isinstance(node, ast.Name):
            if node.id in {"g", "__"}:
                return node.id
            if node.id in parameters:
                used.add(node.id)
                return literal(parameters[node.id])
        if isinstance(node, ast.Constant):
            return literal(node.value)
        if isinstance(node, (ast.List, ast.Tuple)):
            return "[" + ",".join(render(item) for item in node.elts) + "]"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
            return literal(-node.operand.value)
        raise OperationFault("denied", "gremlin_script_refused")
    traversal = render(tree.body)
    if not traversal.startswith(("g.V(", "g.E(")) or used != set(parameters):
        raise OperationFault("invalid", "gremlin_parameter_or_root_mismatch")
    return traversal


class GremlinAdapter(RecordAdapter):
    service = "gremlin"
    scope = "https://cosmos.azure.com/.default"
    schemes = ("wss",)
    credential_kinds = ("entra", "resource_token")
    partition_required = True
    caveats = (Caveat("resource_token_required", "Caller supplies a scoped, expiring resource token. This library neither obtains account keys nor issues tokens; direct Entra traversal auth is not established."),
               Caveat("driver_support_gap", "Python 3.11 uses Gremlin Python 3.7.7 with GraphSON v2. Microsoft recommends 3.4.x, whose Tornado dependency is incompatible; live 3.7 compatibility is unverified."),
               Caveat("nontransactional_graph", "Gremlin traversals are not transactions; ambiguous writes are never replayed."),
               Caveat("read_traversal_subset", "Queries accept parsed g.V/g.E chains and declared read steps, not arbitrary Groovy, lambdas or bytecode."))

    def __init__(self, config):
        super().__init__(config)
        if (set(config.target.coordinates) != {"database", "container"} or config.partition_key_field in {None, "id", "label"}
                or config.key_field != "id" or self.key_fields != ("id",)
                or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,127}", value) for value in config.target.coordinates.values())):
            raise ConfigurationError("Gremlin requires database/container identifiers, id keys and an explicit vertex partition field")
        for operation in ("create", "read", "update", "delete"):
            evidence = ("none", "presence") if operation == "read" else ("none", "acknowledgment", "absence") if operation == "delete" else ("none", "acknowledgment", "presence", "content")
            self.capabilities[operation] = OperationCapability("supported", modes=("merge",) if operation == "update" else (),
                guarantees=("create_if_absent",) if operation == "create" else (), verification=evidence, reason="")
        self.capabilities["query"] = OperationCapability("supported", dialects=("gremlin",), reason="")
        self.capabilities["upsert"] = OperationCapability(reason="atomic_gremlin_upsert_unavailable")

    def create_client(self, session, kind):
        from gremlin_python.driver.client import Client
        from gremlin_python.driver.serializer import GraphSONSerializersV2d0
        from .gremlin_transport import GremlinTransport

        if session._transport._injected is not None:
            raise OperationFault("unsupported", "http_transport_not_native_driver")
        return self

    async def close(self):
        return None

    def validate(self, operation, request, evidence):
        if self.config.credential_kind != "resource_token":
            raise OperationFault("unsupported", "gremlin_resource_token_required")
        for entry in getattr(request, "records", ()) or getattr(request, "keys", ()):
            key = entry.key if hasattr(entry, "key") else entry
            if not isinstance(key.partition, str) or not key.partition:
                raise OperationFault("invalid", "gremlin_partition_string_required")
            if hasattr(entry, "content"):
                if entry.expected_version is not None:
                    raise OperationFault("unsupported", "gremlin_version_unsupported")
                if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in entry.content.data):
                    raise OperationFault("invalid", "invalid_vertex_property")
                for value in entry.content.data.values():
                    if type(value) not in (str, int, float, bool):
                        raise OperationFault("unsupported", "gremlin_scalar_required")
                if operation == "create" and (not isinstance(entry.content.data.get("label"), str) or not entry.content.data["label"]):
                    raise OperationFault("invalid", "vertex_label_required")
                if operation == "update" and ("label" in entry.content.data or not set(entry.content.data) - {"id", self.config.partition_key_field}):
                    raise OperationFault("unsupported", "vertex_label_update_unsupported")
        if any(value is not None for value in getattr(request, "expected_versions", ())):
            raise OperationFault("unsupported", "gremlin_version_unsupported")
        if operation == "query":
            if request.continuation or request.projection:
                raise OperationFault("unsupported", "gremlin_native_projection_without_continuation")
            read_traversal(request.expression, request.parameters)

    async def _run(self, traversal, context, *, mutation=False):
        context.session.client("driver")
        async def invoke():
            token = await context.session.credential.get_token(self.scope)
            values = parse_qs(unquote(token.token), keep_blank_values=True)
            if values.get("type") != ["resource"] or not values.get("sig", [""])[0]:
                raise OperationFault("denied", "resource_token_required")
            task = asyncio.create_task(asyncio.to_thread(self._submit, traversal, context, token.token, mutation))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(task)
                except Exception:
                    pass
                raise
        return await context.invoke(invoke, mutation=mutation)

    def _submit(self, traversal, context, token, mutation):
        from gremlin_python.driver.client import Client
        from gremlin_python.driver.protocol import GremlinServerError
        from gremlin_python.driver.serializer import GraphSONSerializersV2d0
        from .gremlin_transport import GremlinTransport

        timeout = max(0.001, context.deadline - time.monotonic())
        coordinates = self.config.target.coordinates
        url = self.config.endpoint + "/gremlin"
        client = Client(url, "g", username=f"/dbs/{coordinates['database']}/colls/{coordinates['container']}",
            password=token, message_serializer=GraphSONSerializersV2d0(), pool_size=1, max_workers=1,
            transport_factory=lambda: GremlinTransport(url, context.deadline, context.limits.max_output_bytes),
            enable_user_agent_on_connect=False)
        try:
            context.attempts += 1
            context.submitted = True
            result = client.submit(traversal, request_options={"evaluationTimeout": max(1, int(timeout * 1000)),
                                                             "batchSize": context.limits.max_items})
            values = result.all().result(timeout=timeout)
            json_bytes(values)
            return values
        except GremlinServerError as error:
            check_response(HttpResponse(error.status_code), mutation=mutation)
            raise OperationFault("unknown", "invalid_gremlin_response") from None
        except (TimeoutError, OSError, RuntimeError):
            raise OperationFault("unknown" if mutation else "failed", "gremlin_transport_unavailable") from None
        finally:
            client.close()

    def _vertex(self, key):
        return "g.V(" + literal([key.partition, key.parts["id"]]) + ")"

    def expected_content(self, record):
        content = {**plain(record.content.data), **plain(record.key.parts), self.config.partition_key_field: record.key.partition}
        return ContentValue(content)

    async def read_record(self, key, context):
        rows = await self._run(self._vertex(key) + ".limit(2)", context)
        if not rows:
            raise OperationFault("not_found", "record_not_found")
        if len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get("id") != key.parts["id"]:
            raise OperationFault("unknown", "provider_key_mismatch")
        vertex = rows[0]
        content = {"id": vertex["id"], "label": vertex.get("label")}
        for name, properties in vertex.get("properties", {}).items():
            if not isinstance(properties, list) or not all(isinstance(value, dict) and "value" in value for value in properties):
                raise OperationFault("failed", "invalid_vertex_properties")
            content[name] = properties[0]["value"] if len(properties) == 1 else [value["value"] for value in properties]
        if content.get(self.config.partition_key_field) != key.partition:
            raise OperationFault("unknown", "provider_partition_mismatch")
        return ContentValue(content), None

    async def write_record(self, operation, key, record, version, request, context):
        if operation == "delete":
            traversal = self._vertex(key) + ".sideEffect(__.drop()).count()"
        else:
            if operation == "create":
                traversal = "g.addV(" + literal(record.content.data["label"]) + ").property('id'," + literal(key.parts["id"]) + ")"
                traversal += ".property(" + literal(self.config.partition_key_field) + "," + literal(key.partition) + ")"
            else:
                traversal = self._vertex(key)
            for name, value in record.content.data.items():
                if name not in {"id", "label", self.config.partition_key_field}:
                    traversal += ".property(single," + literal(name) + "," + literal(value) + ")"
            traversal += ".count()"
        rows = await self._run(traversal, context, mutation=True)
        if rows == [0] and operation in {"update", "delete"}:
            raise OperationFault("not_found", "record_not_found")
        if rows != [1]:
            raise OperationFault("unknown", "gremlin_write_acknowledgment_invalid")
        return None

    async def execute(self, operation, request, context, evidence, cursor):
        if operation != "query":
            return await super().execute(operation, request, context, evidence, cursor)
        traversal = read_traversal(request.expression, request.parameters) + f".limit({context.limits.max_items + 1})"
        rows = await self._run(traversal, context)
        items = tuple(ItemResult(index, None, "success", ContentValue(row)) for index, row in enumerate(rows[:context.limits.max_items]))
        return AdapterResult(items, truncated=len(rows) > context.limits.max_items)