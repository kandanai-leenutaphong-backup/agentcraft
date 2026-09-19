"""Caller-owned, explicit config-only adapters. No discovery or document imports."""

import inspect
import csv
import io
import json
from pathlib import Path
import re

from .contracts import Refusal, TaskAdapter, canonical, digest, strict_json, text


def _code_identity(value):
    if inspect.iscode(value):
        return {"bytecode": value.co_code.hex(), "constants": [_code_identity(item) for item in value.co_consts],
                "names": value.co_names, "varnames": value.co_varnames, "freevars": value.co_freevars,
                "cellvars": value.co_cellvars, "arguments": [value.co_argcount, value.co_posonlyargcount,
                                                             value.co_kwonlyargcount],
                "flags": value.co_flags, "exceptions": value.co_exceptiontable.hex()}
    if isinstance(value, tuple):
        return {"tuple": [_code_identity(item) for item in value]}
    if isinstance(value, frozenset):
        return {"frozenset": sorted((_code_identity(item) for item in value), key=canonical)}
    return {"type": type(value).__name__, "value": repr(value)}


def _schema(schema, value=None, *, definition=False, depth=0):
    if depth > 8 or not isinstance(schema, dict):
        raise ValueError("invalid schema")
    kind = schema.get("type")
    fields = {
        "object": {"type", "properties", "required", "additionalProperties"},
        "array": {"type", "items", "maxItems", "uniqueItems"},
        "string": {"type", "enum", "pattern", "maxLength"},
        "integer": {"type", "minimum", "maximum"},
        "number": {"type", "minimum", "maximum"},
        "boolean": {"type"},
    }
    if not isinstance(kind, str) or kind not in fields or set(schema) - fields[kind]:
        raise ValueError("unsupported schema keyword")
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if (schema.get("additionalProperties") is not False or not isinstance(properties, dict)
                or not isinstance(required, list) or any(not isinstance(key, str) for key in required)
                or len(set(required)) != len(required) or set(required) != set(properties)):
            raise ValueError("closed object with all fields required")
        for child in properties.values():
            _schema(child, definition=True, depth=depth + 1)
        if not definition:
            if not isinstance(value, dict) or set(value) != set(properties):
                raise ValueError("exact fields required")
            for key, child in properties.items():
                _schema(child, value[key], depth=depth + 1)
    elif kind == "array":
        if (type(schema.get("maxItems")) is not int or not 0 <= schema["maxItems"] <= 256
                or type(schema.get("uniqueItems", False)) is not bool):
            raise ValueError("bounded array required")
        _schema(schema.get("items"), definition=True, depth=depth + 1)
        if not definition:
            if not isinstance(value, list) or len(value) > schema["maxItems"]:
                raise ValueError("invalid array")
            if schema.get("uniqueItems") and len({canonical(item) for item in value}) != len(value):
                raise ValueError("unique items required")
            for item in value:
                _schema(schema["items"], item, depth=depth + 1)
    elif kind == "string":
        if "pattern" in schema:
            re.compile(schema["pattern"])
        if "maxLength" in schema and (type(schema["maxLength"]) is not int or schema["maxLength"] < 1):
            raise ValueError("invalid string bound")
        if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]
                                  or any(not isinstance(item, str) for item in schema["enum"])):
            raise ValueError("invalid enum")
        if not definition and (not isinstance(value, str) or len(value) > schema.get("maxLength", 8192)
                or ("enum" in schema and value not in schema["enum"])
                or ("pattern" in schema and re.fullmatch(schema["pattern"], value) is None)):
            raise ValueError("invalid string")
    elif kind in {"integer", "number"}:
        for bound in ("minimum", "maximum"):
            if bound in schema and (type(schema[bound]) not in (int, float)
                                    or not -float("inf") < schema[bound] < float("inf")):
                raise ValueError("invalid number bound")
        if schema.get("minimum", -float("inf")) > schema.get("maximum", float("inf")):
            raise ValueError("inverted number bounds")
        if not definition and (type(value) not in ((int,) if kind == "integer" else (int, float))
                or not -float("inf") < value < float("inf")
                or value < schema.get("minimum", -float("inf"))
                or value > schema.get("maximum", float("inf"))):
            raise ValueError("invalid number")
    elif not definition and type(value) is not bool:
        raise ValueError("boolean required")


class TaskRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, adapter: TaskAdapter) -> None:
        if (isinstance(adapter, type) or not isinstance(adapter, TaskAdapter)
                or not isinstance(adapter.id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,127}", adapter.id)):
            raise Refusal("invalid_task_adapter")
        if adapter.id in self._adapters:
            raise Refusal("duplicate_task", 409)
        self._task(adapter)
        self._evaluator_digest(adapter)
        self._adapters[adapter.id] = adapter

    def adapter(self, task_id: str) -> TaskAdapter:
        if not isinstance(task_id, str) or task_id not in self._adapters:
            raise Refusal("unknown_task", 404)
        return self._adapters[task_id]

    def _task(self, adapter):
        try:
            description = json.loads(canonical(adapter.describe()))
            fields = {"id", "name", "description", "domain", "task_version", "evaluator_version",
                      "configuration_schema", "submissions", "desired_behavior", "baseline_checks", "candidate_checks"}
            if set(description) != fields or description["id"] != adapter.id:
                raise ValueError("exact description fields required")
            for field in ("name", "description", "domain", "evaluator_version", "desired_behavior"):
                text(description[field], field)
            if type(description["task_version"]) is not int or description["task_version"] < 1:
                raise ValueError("invalid version")
            for field in ("baseline_checks", "candidate_checks"):
                names = description[field]
                if (not isinstance(names, list) or not names or any(not isinstance(name, str) or
                        not re.fullmatch(r"[a-z][a-z0-9-]{0,127}", name) for name in names)
                        or len(set(names)) != len(names)):
                    raise ValueError("named checks required")
            _schema(description["configuration_schema"], definition=True)
            if description["configuration_schema"]["type"] != "object":
                raise ValueError("configuration must be object")
            snapshot = json.loads(canonical(adapter.baseline()))
            if (set(snapshot) != {"schema_version", "task_id", "files"} or type(snapshot["schema_version"]) is not int
                    or snapshot["schema_version"] != 1 or snapshot["task_id"] != adapter.id
                    or set(snapshot["files"]) != {"source.py", "config.json"}
                    or not isinstance(snapshot["files"]["source.py"], str)):
                raise ValueError("config-only baseline required")
            config = strict_json(snapshot["files"]["config.json"], "invalid_candidate_configuration")
            submissions = description["submissions"]
            if not isinstance(submissions, list) or not 1 <= len(submissions) <= 2:
                raise ValueError("one or two offline submissions required")
            for candidate in [config, *submissions]:
                self._validate(adapter, description, canonical(candidate).decode())
            return {**description, "source": snapshot["files"]["source.py"], "configs": [config, *submissions],
                    "baseline_snapshot": snapshot}
        except (ValueError, TypeError, KeyError, RecursionError, Refusal, re.error) as error:
            raise Refusal("invalid_task_adapter", 409) from error

    @staticmethod
    def _evaluator_digest(adapter):
        try:
            parts = []
            methods = [getattr(adapter, name) for name in ("describe", "baseline", "validate_candidate", "evaluate")]
            for ancestor in type(adapter).__mro__:
                for value in vars(ancestor).values():
                    function = value.__func__ if isinstance(value, (staticmethod, classmethod)) else value
                    if inspect.isfunction(function):
                        methods.append(function)
            for method in methods:
                function = getattr(method, "__func__", method)
                parts.extend([inspect.getsource(method).encode(), canonical(_code_identity(function.__code__))])
                filename = inspect.getsourcefile(method)
                if filename is None:
                    raise ValueError("source required")
                parts.append(Path(filename).read_bytes())
            parts.append(Path(__file__).read_bytes())
            return digest(b"\0".join(parts))
        except (OSError, TypeError, AttributeError, ValueError) as error:
            raise Refusal("adapter_source_unavailable", 409) from error

    def task(self, task_id):
        return self._task(self.adapter(task_id))

    def pins(self, task_id):
        task = self.task(task_id)
        return {"task_digest": digest(canonical(task)),
                "evaluator_digest": self._evaluator_digest(self.adapter(task_id))}

    def tasks(self):
        return [{key: task[key] for key in ("id", "name", "description", "domain")}
                for task in (self.task(task_id) for task_id in self._adapters)]

    @staticmethod
    def _validate(adapter, task, content):
        config = strict_json(content, "invalid_candidate_configuration")
        try:
            _schema(task["configuration_schema"], config)
            adapter.validate_candidate(json.loads(canonical(config)))
        except (ValueError, TypeError, Refusal) as error:
            raise Refusal("invalid_candidate_configuration", 409) from error
        return config

    def validate_candidate(self, task_id, content):
        return self._validate(self.adapter(task_id), self.task(task_id), content)

    def evaluate(self, task_id, snapshot, baseline, *, native=False):
        task = self.task(task_id)
        files = snapshot.get("files", {})
        if set(files) != {"source.py", "config.json"} or files["source.py"] != task["source"]:
            raise Refusal("untrusted_candidate_source", 409)
        config = self._validate(self.adapter(task_id), task, files["config.json"])
        if not native and config not in task["configs"]:
            raise Refusal("untrusted_candidate_configuration", 409)
        checks = self.adapter(task_id).evaluate(json.loads(canonical(snapshot)), baseline)
        names = task["baseline_checks" if baseline else "candidate_checks"]
        if (not isinstance(checks, list) or len(checks) != len(names)
                or any(not isinstance(check, dict) or set(check) != {"name", "status", "detail"}
                       or not isinstance(check["name"], str) or check["status"] not in ("passed", "failed", "blocked")
                       or not isinstance(check["detail"], str) for check in checks)
                or sorted(check["name"] for check in checks) != sorted(names)):
            raise Refusal("invalid_evaluator_result", 409)
        checks = json.loads(canonical(checks))
        if not baseline:
            checks.append({"name": "configuration-changed", "status": "passed" if config != task["configs"][0] else "failed",
                           "detail": "Baseline configuration must change"})
        return checks


class _DemoAdapter:
    def describe(self):
        return {"id": self.id, "name": self.name, "description": self.description, "domain": self.domain,
                "task_version": 1, "evaluator_version": "synthetic-1", "configuration_schema": self.schema,
                "submissions": self.configs[1:], "desired_behavior": self.desired,
                "baseline_checks": self.baseline_checks, "candidate_checks": self.candidate_checks}

    def baseline(self):
        return {"schema_version": 1, "task_id": self.id,
                "files": {"source.py": self.source, "config.json": json.dumps(self.configs[0], indent=2, sort_keys=True) + "\n"}}

    def validate_candidate(self, config):
        return None

    def _execute(self):
        namespace = {}
        exec(compile(self.source, "<trusted-synthetic-template>", "exec"), namespace)
        return namespace["execute"]


class AgentToolAdapter(_DemoAdapter):
    id = "agent-tool-availability"
    name = "Agent tool availability"
    description = "Synthetic tool allowlist change with a retained invalid submission and bounded repair."
    domain = "agent-configuration"
    source = '''def execute(config, operation, value):
    if operation not in config["tools"]:
        raise PermissionError("tool_not_available")
    if operation == "read":
        return value
    if operation == "search":
        return "needle" in value
    if operation == "export":
        return {"result": value}
    raise PermissionError("unknown_tool")
'''
    configs = [{"tools": ["read", "search"]}, {"tools": ["read", "export", "shell"]},
               {"tools": ["read", "search", "export"]}]
    schema = {"type": "object", "additionalProperties": False, "required": ["tools"],
              "properties": {"tools": {"type": "array", "maxItems": 16, "uniqueItems": True,
                  "items": {"type": "string", "pattern": "[a-z][a-z0-9_-]{0,63}"}}}}
    desired = ('Registered operations: read returns its input; search detects "needle"; export returns '
               '{"result": input}. Preserve read/search, make export callable, and refuse shell and '
               'every unregistered tool. Grant only operations needed for this behavior.')
    baseline_checks = ["preserve-read", "preserve-search", "least-privilege-tools", "shell-refused"]
    candidate_checks = [*baseline_checks, "export-callable"]

    def evaluate(self, snapshot, baseline):
        config = json.loads(snapshot["files"]["config.json"])
        execute = self._execute()
        checks = []

        def check(name, condition, detail):
            checks.append({"name": name, "status": "passed" if condition else "failed", "detail": detail})

        for operation, expected in (("read", "needle"), ("search", True)):
            try:
                observed = execute(config, operation, "needle")
            except PermissionError:
                observed = None
            check(f"preserve-{operation}", observed == expected, f"Observed {observed!r}; expected {expected!r}")
        permitted = {"read", "search"} if baseline else {"read", "search", "export"}
        check("least-privilege-tools", set(config["tools"]) == permitted, "Exact registered tool allowlist")
        try:
            execute(config, "shell", "ignored")
        except PermissionError:
            check("shell-refused", "shell" not in config["tools"], "Unregistered shell must not be available")
        else:
            check("shell-refused", False, "Shell unexpectedly available")
        if not baseline:
            try:
                observed = execute(config, "export", "needle")
            except PermissionError:
                observed = None
            check("export-callable", observed == {"result": "needle"}, "Export must return the exact typed result")
        return checks


class CsvExportAdapter(_DemoAdapter):
    id = "csv-export-transformation"
    name = "CSV export transformation"
    description = "Synthetic uppercase export change preserving commas, quotes and newlines."
    domain = "csv-transformation"
    source = '''def execute(config, rows):
    import csv
    import io
    output = io.StringIO(newline="")
    records = [["name", "amount"]]
    for row in rows:
        name = row["name"].upper() if config["uppercase"] else row["name"]
        records.append([name, str(row["amount"])])
    if config["quoted"]:
        csv.writer(output, lineterminator="\\n").writerows(records)
    else:
        output.write("".join(",".join(record) + "\\n" for record in records))
    return output.getvalue()
'''
    configs = [{"uppercase": False, "quoted": True}, {"uppercase": True, "quoted": False},
               {"uppercase": True, "quoted": True}]
    schema = {"type": "object", "additionalProperties": False, "required": ["uppercase", "quoted"],
              "properties": {"uppercase": {"type": "boolean"}, "quoted": {"type": "boolean"}}}
    desired = ('The trusted exporter uses uppercase to transform names and quoted to select csv.writer '
               'instead of comma joining. Export uppercase names while preserving amounts, commas, '
               'embedded quotes and newlines on CSV roundtrip. Keep header name,amount and empty-input header.')
    baseline_checks = ["csv-roundtrip", "header-and-row-count", "empty-export"]
    candidate_checks = baseline_checks

    def evaluate(self, snapshot, baseline):
        config = json.loads(snapshot["files"]["config.json"])
        execute = self._execute()
        rows = [{"name": 'Ada, "A"', "amount": 12}, {"name": "two\nlines", "amount": 0}]
        parsed = list(csv.reader(io.StringIO(execute(config, rows), newline="")))
        expected = [["name", "amount"]] + [[row["name"] if baseline else row["name"].upper(),
                                            str(row["amount"])] for row in rows]
        return [{"name": name, "status": "passed" if condition else "failed", "detail": detail}
                for name, condition, detail in (
                    ("csv-roundtrip", parsed == expected, f"Observed {parsed!r}; expected {expected!r}"),
                    ("header-and-row-count", len(parsed) == 3 and parsed[0] == ["name", "amount"],
                     "Header and both records survive export"),
                    ("empty-export", execute(config, []) == "name,amount\n", "Empty input retains header"))]


def default_registry() -> TaskRegistry:
    registry = TaskRegistry()
    registry.register(AgentToolAdapter())
    registry.register(CsvExportAdapter())
    return registry