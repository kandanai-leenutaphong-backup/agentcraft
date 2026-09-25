"""Declarative hosted-agent lifecycle: one digest-pinned `RunSpec` drives package -> build -> deploy -> invoke/stream
-> verify -> register-evaluator -> evaluate -> optimize -> select -> promote -> re-verify -> re-evaluate.

Composition layer: may import every stage subpackage; nothing inside `foundry_ops` imports `pipeline`.
Stages take `(spec, clients, ledger, **options)`; `Clients` is built at the edge (`cloud_clients`) or by tests.
"""

from .clients import Clients, cloud_clients
from .inputs import (canonical, data_module, input_json, load_journeys, load_rows, parse_json, project_rows, read_input,
                     read_rows, referenced_file, register_rows)
from .run import STAGE_INPUTS, plan, run, stage_record, window
from .source import (PACKAGE_IMAGE_DIR, ImageLayout, check_package_content, check_package_tools, contained,
                     package_allowed, package_digest, package_inputs, release_label, source_manifest, stage_context)
from .spec import (DATA_MODES, DEFAULT_BOUNDS, ENV_FORMATS, ENV_TARGETS, INPUT_KINDS, KIND, MANIFEST_KEYS, PURPOSE,
                   STAGES, WRITE_STAGES, InputRef, RunSpec, data_available, load_env_manifest, load_run_spec,
                   open_ledger, parse_env, spec_from_value, validate_env)
from .stages import (build, current_deployment, current_label, deploy, evaluate, expected_identity, inspect, invoke,
                     invoke_journeys, logs, optimization_overlay, optimize, preflight, promote, register_evaluator,
                     select, teardown, verify)

__all__ = [
    "Clients", "cloud_clients",
    "canonical", "data_module", "input_json", "load_journeys", "load_rows", "parse_json", "project_rows", "read_input",
    "read_rows", "referenced_file", "register_rows",
    "STAGE_INPUTS", "plan", "run", "stage_record", "window",
    "PACKAGE_IMAGE_DIR", "ImageLayout", "check_package_content", "check_package_tools", "contained",
    "package_allowed", "package_digest", "package_inputs", "release_label", "source_manifest", "stage_context",
    "DATA_MODES", "DEFAULT_BOUNDS", "ENV_FORMATS", "ENV_TARGETS", "INPUT_KINDS", "KIND", "MANIFEST_KEYS", "PURPOSE",
    "STAGES", "WRITE_STAGES", "InputRef", "RunSpec", "data_available", "load_env_manifest", "load_run_spec",
    "open_ledger", "parse_env", "spec_from_value", "validate_env",
    "build", "current_deployment", "current_label", "deploy", "evaluate", "expected_identity", "inspect", "invoke",
    "invoke_journeys", "logs", "optimization_overlay", "optimize", "preflight", "promote", "register_evaluator",
    "select", "teardown", "verify",
]
