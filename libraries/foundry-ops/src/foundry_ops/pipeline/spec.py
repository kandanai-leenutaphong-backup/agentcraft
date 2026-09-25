"""One declarative run spec: targets, agent, models, pinned inputs, bounds, records and explicit cloud-write
authorization. Loaded from a digest-pinned JSON (canonical) or YAML file; unknown fields, secrets, placeholders,
aliases and duplicate keys refuse before any side effect. `load_env_manifest` maps the older env + run-manifest
pair onto the same `RunSpec`."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from ..core import (RECORD_NAME, EvidenceLedger, RefusedError, RunManifest, load_run_manifest, safe_identifier,
                    series_directory, sha256_hex)

SCHEMA_VERSION = 1
KIND = "foundry-hosted-agent-run"
PURPOSE = "foundry-hosted-agent"
STAGES = ("preflight", "build", "deploy", "invoke", "verify", "register_evaluator", "evaluate", "optimize", "select",
          "promote", "reverify", "reevaluate")
WRITE_STAGES = frozenset({"build", "deploy", "invoke", "register_evaluator", "evaluate", "optimize", "promote",
                          "reverify", "reevaluate", "teardown"})
NAME = r"[a-z0-9][a-z0-9-]{0,62}"
ENVIRONMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
ENV_FORMATS = {
    "AZURE_TENANT_ID": GUID,
    "AZURE_SUBSCRIPTION_ID": GUID,
    "FOUNDRY_PROJECT_RESOURCE_ID": (r"/subscriptions/" + GUID + r"/resourceGroups/[A-Za-z0-9._()-]{1,90}"
                                    r"/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]{2,64}"
                                    r"/projects/[A-Za-z0-9_-]{1,64}"),
    "FOUNDRY_PROJECT_ENDPOINT": r"https://[a-z0-9-]{2,64}\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_-]{1,64}",
    "ACR_NAME": r"[A-Za-z0-9]{5,50}",
    "ACR_LOGIN_SERVER": r"[a-z0-9]{5,50}\.azurecr\.io",
    "IMAGE_REPOSITORY": r"[a-z0-9]+(?:[._/-][a-z0-9]+){0,20}",
    "MODEL_ACCOUNT": r"[A-Za-z0-9-]{2,64}",
    "MODEL_RESOURCE_GROUP": r"[A-Za-z0-9._()-]{1,90}",
    "MODEL_DEPLOYMENT": r"[A-Za-z0-9._-]{1,64}",
}
ENV_TARGETS = {"AZURE_TENANT_ID": "tenant_id", "AZURE_SUBSCRIPTION_ID": "subscription_id",
               "FOUNDRY_PROJECT_RESOURCE_ID": "project_resource_id", "FOUNDRY_PROJECT_ENDPOINT": "project_endpoint",
               "ACR_NAME": "acr_name", "ACR_LOGIN_SERVER": "acr_login_server", "IMAGE_REPOSITORY": "image_repository",
               "MODEL_ACCOUNT": "model_account", "MODEL_RESOURCE_GROUP": "model_resource_group"}
TARGET_FORMATS = {target: ENV_FORMATS[env] for env, target in ENV_TARGETS.items()}
MODEL_FORMAT = ENV_FORMATS["MODEL_DEPLOYMENT"]
IMAGE_FORMAT = r"[a-z0-9.-]+/[a-z0-9]+(?:[._/-][a-z0-9]+)*@sha256:[0-9a-f]{64}"
SECRET_NAME = re.compile(r"(?i)(secret|password|passwd|token|api_?key|account_?key|connection_?string|"
                         r"(^|_)sas($|_)|_key$|credential)")
SECRET_VALUE = re.compile(r"(?i)(eyJ[A-Za-z0-9_-]{10,}|-----BEGIN|accountkey=|sharedaccesskey=|sharedaccesssignature|"
                          r"(^|[?&;])sig=|password=|secret=|token=|client_secret|ghp_|github_pat_|\bsk-[A-Za-z0-9]{8,}|"
                          r"[A-Za-z0-9+/]{30,}={1,2}$)")
AUTH_NAME = re.compile(r"(?i)auth")
AUTH_OFF = frozenset({"false", "0", "off", "no", "disabled", "none", "anonymous"})
AGENT_ACCESS_NAME = re.compile(r"(?i)(agent_access|signed_dev|dev_access)")
INPUT_KINDS = frozenset({"journeys", "criteria", "items", "train", "validation", "optimization", "evaluator",
                         "selection_rule", "candidate_record", "optimization_config"})
DATASET_KINDS = frozenset({"items", "train", "validation"})
FILE_SECTIONS = ("evaluator", "optimization", "selection_rule")
MANIFEST_KEYS = frozenset({"schema_version", "purpose", "series", "agent", "actions", "env_sha256",
                           "previous_version", "previous_image"})
OPTIONAL_MANIFEST_KEYS = frozenset({"package_dir", "inputs"})
DEFAULT_BOUNDS = {"max_invocations": 20, "eval_wait_seconds": 1800, "optimize_wait_seconds": 3600,
                  "deploy_wait_seconds": 300, "max_candidates": 20}
BOUND_CEILINGS = {"max_invocations": 20, "eval_wait_seconds": 1800, "optimize_wait_seconds": 21600,
                  "deploy_wait_seconds": 900, "max_candidates": 20}
DATA_MODES = ("inline", "dataset")
TOP_FIELDS = frozenset({"schema_version", "kind", "series", "targets", "agent", "models", "inputs", *FILE_SECTIONS,
                        "bounds", "records", "authorization", "data"})
REQUIRED_TOP = ("schema_version", "kind", "series", "targets", "agent", "models", "records", "authorization")


@dataclass(frozen=True)
class InputRef:
    """A repository-relative file pinned by sha256, or (items/train/validation) a registered dataset reference."""

    path: str | None = None
    sha256: str | None = None
    dataset: Mapping[str, str] | None = None


@dataclass(frozen=True)
class RunSpec:
    series: str
    agent: str
    targets: Mapping[str, str]
    models: Mapping[str, str | None]
    repo: Path
    records: Path
    package_dir: str | None = None
    package: Path | None = None
    previous_version: str | None = None
    previous_image: str | None = None
    inputs: Mapping[str, tuple[InputRef, ...]] = field(default_factory=dict)
    bounds: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_BOUNDS))
    authorization: frozenset[str] = frozenset()
    data: str = "inline"
    sha256: str | None = None
    raw: bytes | None = None
    origin: str = "spec"
    observed_inputs: dict[str, dict[str, str]] = field(default_factory=dict, compare=False)

    def require(self, stage: str) -> None:
        """Cloud-write stages run only when the reviewed spec names them under `authorization.cloud_write`."""
        if stage in WRITE_STAGES and stage not in self.authorization:
            raise RefusedError("stage_unauthorized", f"cloud-write stage not authorized by the run spec: {stage}")

    def declared(self, kind: str) -> str | None:
        """The one declared file path for `kind`, else None."""
        paths = [ref.path for ref in self.inputs.get(kind, ()) if ref.path is not None]
        return paths[0] if len(paths) == 1 else None


def data_available() -> bool:
    if "foundry_ops.data" in sys.modules:
        return sys.modules["foundry_ops.data"] is not None
    try:
        return importlib.util.find_spec("foundry_ops.data") is not None
    except (ImportError, ValueError):
        return False


# --- env + run manifest (the template's per-environment pair) --------------------------------

def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise RefusedError("env_syntax", f"line {number}: expected KEY=VALUE")
        if key in values:
            raise RefusedError("env_duplicate", f"duplicate variable {key}")
        values[key] = value
    return values


def _check_targets(targets: Mapping[str, str], prefix: str) -> None:
    if targets["project_resource_id"].split("/")[2].lower() != targets["subscription_id"].lower():
        raise RefusedError(f"{prefix}_subscription", "project resource id is outside the subscription")
    if targets["acr_login_server"] != targets["acr_name"].lower() + ".azurecr.io":
        raise RefusedError(f"{prefix}_registry", "ACR login server does not match ACR name")


def validate_env(values: dict[str, str]) -> dict[str, str]:
    """Refuse before any side effect. Messages name the variable, never its value."""
    for key, value in values.items():
        if SECRET_NAME.search(key) or SECRET_VALUE.search(value):
            raise RefusedError("env_secret", f"secret-shaped variable refused: {key}; use managed identity or Key Vault")
        if AUTH_NAME.search(key) and value.strip().lower() in AUTH_OFF:
            raise RefusedError("env_auth_disabled", f"variable would disable authentication: {key}")
        if AGENT_ACCESS_NAME.search(key):
            raise RefusedError("env_agent_access", f"variable would enable unrequested agent access: {key}")
    unknown = sorted(set(values) - set(ENV_FORMATS))
    if unknown:
        raise RefusedError("env_unknown", "unknown variables: " + ", ".join(unknown))
    missing = sorted(key for key in ENV_FORMATS if not values.get(key))
    if missing:
        raise RefusedError("env_missing", "missing variables: " + ", ".join(missing))
    placeholders = sorted(key for key, value in values.items() if "<" in value or ">" in value)
    if placeholders:
        raise RefusedError("env_placeholder", "placeholder values: " + ", ".join(placeholders))
    malformed = sorted(key for key, pattern in ENV_FORMATS.items() if not re.fullmatch(pattern, values[key]))
    if malformed:
        raise RefusedError("env_format", "malformed variables: " + ", ".join(malformed))
    _check_targets({target: values[env] for env, target in ENV_TARGETS.items()}, "env")
    return values


def package_path(value: Any, repo: Path, code: str = "manifest_package") -> Path | None:
    if value is None:
        return None
    if not _relative(value):
        raise RefusedError(code, "package_dir must be a repository-relative path without . or ..")
    path = repo / value
    if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(repo.resolve()):
        raise RefusedError(code, "package_dir missing, symlinked or outside the repository")
    return path


def _relative(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not value.startswith(("/", "~")) and "\\" not in value \
        and all(part not in ("", ".", "..") for part in value.rstrip("/").split("/"))


def _pins_valid(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return bool(values) and len(set(map(str, values))) == len(values) and all(
        isinstance(item, str) and SHA256.fullmatch(item) for item in values)


def load_env_manifest(environment: str, manifest_sha256: str, action: str, *, env_dir: Path, records: Path,
                      repo: Path, purpose: str = PURPOSE) -> tuple[RunSpec, RunManifest, EvidenceLedger]:
    """Env targets, then the digest-pinned run manifest binding them; only then create evidence state.

    Manifest `inputs` pin sha256 only (paths arrive per action); `actions` doubles as the cloud-write
    authorization; data stays inline."""
    if not ENVIRONMENT.fullmatch(environment or ""):
        raise RefusedError("environment", "environment name must match " + ENVIRONMENT.pattern)
    env_path = env_dir / f"{environment}.env"
    if env_path.is_symlink() or not env_path.is_file():
        raise RefusedError("env_path", "environment file missing or symlinked")
    env = validate_env(parse_env(env_path.read_text()))
    run = load_run_manifest(env_dir / f"{environment}.run.json", expected_sha256=manifest_sha256, action=action,
                            allowed_root=env_dir, pins={"env_sha256": env_path}, purpose=purpose,
                            series_pattern=NAME, agent_pattern=NAME)
    extra = sorted(set(run.value) - MANIFEST_KEYS - OPTIONAL_MANIFEST_KEYS)
    if extra:
        raise RefusedError("manifest_fields", "unknown manifest fields: " + ", ".join(extra))
    previous = run.value.get("previous_version")
    if previous is not None and not (isinstance(previous, str) and previous.isdigit()):
        raise RefusedError("manifest_previous", "previous_version must be a version number string or null")
    inputs = run.value.get("inputs", {})
    if not isinstance(inputs, dict) or set(inputs) - INPUT_KINDS or any(not _pins_valid(value) for value in inputs.values()):
        raise RefusedError("manifest_inputs", "inputs must map known kinds to sha256 hex (or a list of distinct "
                                              "sha256 hex): " + ", ".join(sorted(INPUT_KINDS)))
    package = package_path(run.value.get("package_dir"), repo)
    records.mkdir(exist_ok=True)
    ledger = EvidenceLedger(series_directory(records, run.series))
    run.bind(ledger)
    spec = RunSpec(
        series=run.series, agent=run.agent or "", repo=repo, records=records,
        targets={target: env[name] for name, target in ENV_TARGETS.items()},
        models={"runtime": env["MODEL_DEPLOYMENT"], "judge": None, "optimizer": None},
        package_dir=run.value.get("package_dir"), package=package, previous_version=previous,
        previous_image=run.value.get("previous_image"),
        inputs={kind: tuple(InputRef(sha256=pin) for pin in (value if isinstance(value, list) else [value]))
                for kind, value in inputs.items()},
        authorization=frozenset(str(item).replace("-", "_") for item in run.value["actions"]) & WRITE_STAGES,
        sha256=run.sha256, raw=run.raw, origin="manifest")
    return spec, run, ledger


# --- run spec document -----------------------------------------------------------------------

def _refuse_secrets(value: Any, where: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _refuse_secrets(item, f"{where}.{key}" if where else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _refuse_secrets(item, f"{where}[{index}]")
    elif isinstance(value, str):
        if SECRET_VALUE.search(value):
            raise RefusedError("spec_secret", f"secret-shaped value refused at {where}; use managed identity")
        if "<" in value or ">" in value:
            raise RefusedError("spec_placeholder", f"placeholder value at {where}")


def _section(value: Mapping[str, Any], name: str, allowed: frozenset[str] | set[str],
             required: tuple[str, ...] | set[str] = ()) -> dict[str, Any]:
    section = value.get(name, {})
    if not isinstance(section, dict):
        raise RefusedError("spec_shape", f"{name} must be an object")
    unknown = sorted(set(section) - set(allowed))
    if unknown:
        raise RefusedError("spec_field", f"unknown fields in {name}: " + ", ".join(unknown))
    missing = sorted(key for key in required if section.get(key) in (None, ""))
    if missing:
        raise RefusedError("spec_missing", f"missing fields in {name}: " + ", ".join(missing))
    return section


def _input_ref(kind: str, value: Any) -> InputRef:
    if not isinstance(value, dict):
        raise RefusedError("spec_input", f"inputs.{kind}: expected {{path, sha256}} or {{dataset}}")
    if "dataset" in value:
        dataset = value["dataset"]
        if kind not in DATASET_KINDS or set(value) != {"dataset"} or not isinstance(dataset, dict) \
                or not {"name", "version", "sha256"} <= set(dataset) <= {"name", "version", "sha256", "rows"} \
                or not isinstance(dataset.get("version"), str) \
                or not isinstance(dataset.get("sha256"), str) or not SHA256.fullmatch(dataset["sha256"]) \
                or ("rows" in dataset and not (type(dataset["rows"]) is int and dataset["rows"] > 0)):
            raise RefusedError("spec_input", f"inputs.{kind}: dataset refs ({', '.join(sorted(DATASET_KINDS))}) need "
                                             "name, version, sha256 and optionally rows (count)")
        safe_identifier(dataset["name"], "dataset name")
        safe_identifier(dataset["version"], "dataset version")
        return InputRef(dataset=dict(dataset))
    if set(value) != {"path", "sha256"} or not _relative(value.get("path")) \
            or not isinstance(value.get("sha256"), str) or not SHA256.fullmatch(value["sha256"]):
        raise RefusedError("spec_input", f"inputs.{kind}: file refs need a repository-relative path and sha256 hex")
    return InputRef(path=value["path"], sha256=value["sha256"])


def _inputs(value: Mapping[str, Any]) -> dict[str, tuple[InputRef, ...]]:
    declared = _section(value, "inputs", INPUT_KINDS)
    for name in FILE_SECTIONS:
        if name in value:
            if name in declared:
                raise RefusedError("spec_input", f"{name} declared twice (top level and inputs)")
            declared = {**declared, name: value[name]}
    inputs: dict[str, tuple[InputRef, ...]] = {}
    for kind, item in declared.items():
        items = item if isinstance(item, list) else [item]
        refs = tuple(_input_ref(kind, entry) for entry in items)
        digests = [ref.sha256 or (ref.dataset or {}).get("sha256") for ref in refs]
        if not refs or len(set(digests)) != len(digests):
            raise RefusedError("spec_input", f"inputs.{kind}: non-empty list of distinct pins required")
        inputs[kind] = refs
    return inputs


def spec_from_value(value: Any, *, repo: Path, sha256: str | None = None, raw: bytes | None = None,
                    available: bool | None = None) -> RunSpec:
    if not isinstance(value, dict):
        raise RefusedError("spec_shape", "run spec must be an object")
    _refuse_secrets(value, "")
    unknown = sorted(set(value) - TOP_FIELDS)
    if unknown:
        raise RefusedError("spec_field", "unknown run spec fields: " + ", ".join(unknown))
    missing = [key for key in REQUIRED_TOP if key not in value]
    if missing:
        raise RefusedError("spec_missing", "missing run spec fields: " + ", ".join(missing))
    if value["schema_version"] != SCHEMA_VERSION or value["kind"] != KIND:
        raise RefusedError("spec_schema", f"run spec needs schema_version {SCHEMA_VERSION} and kind {KIND}")
    series = value["series"]
    if not isinstance(series, str) or not re.fullmatch(NAME, series) or not RECORD_NAME.fullmatch(series):
        raise RefusedError("spec_series", "series must match " + NAME)
    targets = _section(value, "targets", set(TARGET_FORMATS), set(TARGET_FORMATS))
    malformed = sorted(key for key, pattern in TARGET_FORMATS.items()
                       if not isinstance(targets[key], str) or not re.fullmatch(pattern, targets[key]))
    if malformed:
        raise RefusedError("spec_target_format", "malformed targets: " + ", ".join(malformed))
    _check_targets(targets, "spec")
    agent = _section(value, "agent", {"name", "package_dir", "previous_version", "previous_image"}, ("name",))
    if not isinstance(agent["name"], str) or not re.fullmatch(NAME, agent["name"]):
        raise RefusedError("spec_agent", "agent.name must match " + NAME)
    previous, image = agent.get("previous_version"), agent.get("previous_image")
    if previous is not None and not (isinstance(previous, str) and previous.isdigit()):
        raise RefusedError("spec_agent", "agent.previous_version must be a version number string or null")
    if image is not None and not (isinstance(image, str) and re.fullmatch(IMAGE_FORMAT, image)):
        raise RefusedError("spec_agent", "agent.previous_image must be a digest-pinned image or null")
    models = _section(value, "models", {"runtime", "judge", "optimizer"}, ("runtime",))
    if any(item is not None and not (isinstance(item, str) and re.fullmatch(MODEL_FORMAT, item))
           for item in models.values()):
        raise RefusedError("spec_models", "models are deployment names or null")
    bounds = _section(value, "bounds", set(DEFAULT_BOUNDS))
    if any(type(item) is not int or not 0 < item <= BOUND_CEILINGS[key] for key, item in bounds.items()):
        raise RefusedError("spec_bounds", "bounds are positive integers within: " + ", ".join(
            f"{key}<={ceiling}" for key, ceiling in BOUND_CEILINGS.items()))
    records = value["records"]
    if not _relative(records) or (repo / records).is_symlink() or not (repo / records).parent.is_dir() \
            or not (repo / records).resolve().is_relative_to(repo.resolve()):
        raise RefusedError("spec_records", "records must be a repository-relative directory with an existing parent")
    authorization = _section(value, "authorization", {"cloud_write"}, ())
    stages = authorization.get("cloud_write", [])
    if not isinstance(stages, list) or len(set(map(str, stages))) != len(stages) or set(stages) - WRITE_STAGES:
        raise RefusedError("spec_authorization", "authorization.cloud_write lists distinct write stages: "
                           + ", ".join(sorted(WRITE_STAGES)))
    inputs = _inputs(value)
    data = value.get("data", "dataset" if (data_available() if available is None else available) else "inline")
    if data not in DATA_MODES:
        raise RefusedError("spec_data", "data must be inline or dataset")
    if data != "dataset" and any(ref.dataset for refs in inputs.values() for ref in refs):
        raise RefusedError("spec_data", "dataset input refs need data: dataset")
    return RunSpec(series=series, agent=agent["name"], targets=dict(targets), repo=repo, records=repo / records,
                   models={key: models.get(key) for key in ("runtime", "judge", "optimizer")},
                   package_dir=agent.get("package_dir"),
                   package=package_path(agent.get("package_dir"), repo, "spec_package"),
                   previous_version=previous, previous_image=image, inputs=inputs,
                   bounds={**DEFAULT_BOUNDS, **bounds}, authorization=frozenset(stages), data=data,
                   sha256=sha256, raw=raw, origin="spec")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise RefusedError("spec_duplicate", "duplicate key in run spec")
    return dict(pairs)


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as error:
        raise RefusedError("spec_yaml", "YAML run spec needs PyYAML; use the canonical JSON form") from error

    class Loader(yaml.SafeLoader):
        pass

    def mapping(loader: Any, node: Any) -> dict[str, Any]:
        loader.flatten_mapping(node)
        return _json_object(loader.construct_pairs(node, deep=True))

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        if any(isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None)
               for event in yaml.parse(text, Loader=yaml.SafeLoader)):
            raise RefusedError("spec_alias", "YAML anchors and aliases are refused")
        return yaml.load(text, Loader=Loader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as error:
        raise RefusedError("spec_syntax", "run spec is not valid YAML") from error


def load_run_spec(path: str | os.PathLike[str], *, expected_sha256: str, repo: str | os.PathLike[str],
                  available: bool | None = None) -> RunSpec:
    """Digest-pinned spec inside `repo`: `.json` (canonical) or `.yaml`/`.yml`; paths in it are repo-relative."""
    root = Path(repo).resolve()
    source = Path(path)
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
        raise RefusedError("spec_path", "run spec missing, symlinked or outside the repository")
    raw = source.read_bytes()
    if not isinstance(expected_sha256, str) or sha256_hex(raw) != expected_sha256:
        raise RefusedError("spec_digest", "run spec digest mismatch")
    suffix = source.suffix.lower()
    try:
        text = raw.decode("utf-8")
        if suffix == ".json":
            value = json.loads(text, object_pairs_hook=_json_object)
        elif suffix in (".yaml", ".yml"):
            value = _load_yaml(text)
        else:
            raise RefusedError("spec_format", "run spec must be .json, .yaml or .yml")
    except ValueError as error:
        if isinstance(error, RefusedError):
            raise
        raise RefusedError("spec_syntax", "run spec is not UTF-8 JSON") from error
    return spec_from_value(value, repo=root, sha256=expected_sha256, raw=raw, available=available)


def open_ledger(spec: RunSpec) -> EvidenceLedger:
    """Create `<records>/<series>` and bind the exact spec bytes once; different bytes under the series refuse."""
    spec.records.mkdir(exist_ok=True)
    ledger = EvidenceLedger(series_directory(spec.records, spec.series))
    if spec.raw is not None:
        ledger.retain_bytes("run-spec.json" if spec.origin == "spec" else "run-manifest.json", spec.raw,
                            allow_identical=True)
    return ledger
