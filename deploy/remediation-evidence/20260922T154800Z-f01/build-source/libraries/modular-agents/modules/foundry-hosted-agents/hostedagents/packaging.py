"""Content-addressed host bundles; canonical libraries install as distributions."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .definition import Definition
from .policy import RuntimePolicy, RuntimeTarget

MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024 * 1024
_OWNED_PACKAGES = ("agentconfig", "toolshape", "hostedagents")
_EXCLUDED = frozenset({"__pycache__", "node_modules", "build", "dist", "tests", "artifacts"})
_SUFFIXES = frozenset({".py", ".json", ".yaml", ".yml", ".md", ".txt", ".toml", ".csv"})
_SECRET = re.compile(
    rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|"
    rb"(?i:AccountKey|SharedAccessSignature)\s*=\s*[^\s;\"']+|"
    rb"(?i:client_secret|api_key|access_token)\s*[:=]\s*[\"'][A-Za-z0-9_+/.=-]{20,}[\"']"
)


class BundleError(ValueError):
    """A source bundle is incomplete, nonportable, or fails integrity checks."""


@dataclass(frozen=True)
class Bundle:
    directory: Path
    zip_path: Path
    sha256: str
    artifact_id: str
    runtime_sha256: str
    metadata: dict[str, Any]
    config: dict[str, Any]


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _source_files(source: Path, prefix: str) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or not (source / "__init__.py").is_file():
        raise BundleError(f"{prefix} must be a plain Python package directory")
    files: dict[str, bytes] = {}
    size = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part.startswith(".") or part in _EXCLUDED or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.is_symlink():
            raise BundleError(f"symlinks are not packaged: {prefix}/{relative}")
        if not path.is_file():
            continue
        if path.suffix in (".pyc", ".pyo"):
            continue
        if path.suffix not in _SUFFIXES:
            raise BundleError(f"unsupported source asset: {prefix}/{relative}")
        size += path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise BundleError("package source exceeds the uncompressed size limit")
        content = path.read_bytes()
        if _SECRET.search(content):
            raise BundleError(f"credential-shaped content refused in {prefix}/{relative}")
        files[f"{prefix}/{relative.as_posix()}"] = content
    return files


def build_bundle(
    definition: Definition,
    *,
    package_sources: Mapping[str, Path],
    output_dir: Path,
    policy: RuntimePolicy | None = None,
    target: RuntimeTarget | None = None,
    requirements: Path | None = None,
    cpu: str = "1",
    memory: str = "2Gi",
) -> Bundle:
    """Write a content-addressed artifact; never overwrite or remove caller files."""
    policy = policy or RuntimePolicy()
    target = target or RuntimeTarget()
    if policy.allow_model and not target.model_endpoint:
        raise BundleError("an explicit model endpoint is required before enabling model calls")
    if set(policy.allowed_tools) - set(definition.tools.names):
        raise BundleError("operator policy names a tool absent from this agent")
    if cpu not in ("0.5", "1", "2", "4") or memory not in ("1Gi", "2Gi", "4Gi", "8Gi"):
        raise BundleError("unsupported CPU or memory bound")
    for name in package_sources:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise BundleError("package_sources keys must be top-level Python package names")
        if name in _OWNED_PACKAGES or name in ("main", "llm_interface", "agent_framework", "starlette", "pydantic", "openai", "azure", "httpx", "uvicorn", "yaml"):
            raise BundleError(f"package name conflicts with the runtime: {name}")
    required_packages = {reference.split(":", 1)[0].split(".", 1)[0] for reference in definition.tools.references}
    if required_packages - set(package_sources):
        raise BundleError("every tool's package must have an explicit source directory")
    for function in definition.spec.tools:
        name = function.__module__.split(".", 1)[0]
        actual = Path(inspect_source(function)).resolve()
        source = Path(package_sources[name]).resolve()
        if not actual.is_relative_to(source):
            raise BundleError(f"{name}: supplied source differs from the imported tool")
    config = {
        "format": 1,
        "agent_id": definition.spec.agent_id,
        "name": definition.spec.name,
        "description": definition.spec.description,
        "model": definition.spec.model,
        "instructions": definition.spec.instructions,
        "tools": list(definition.tools.references),
        "policy": policy.model_dump(mode="json"),
        "target": target.model_dump(mode="json"),
    }
    runtime = Path(__file__).parent / "runtime"
    requirement_path = requirements or runtime / "requirements.txt"
    if not requirement_path.is_file():
        raise BundleError("runtime distribution requirements are missing")
    requirement_bytes = requirement_path.read_bytes()
    declared = set()
    for line in requirement_bytes.decode().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not re.fullmatch(
            r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+!-]+(?:\s*;[^\r\n]+)?", stripped
        ):
            raise BundleError("runtime dependencies must be exact pins, without URLs or local paths")
        if stripped and not stripped.startswith("#"):
            declared.add(stripped)
    if not {"modular-agents[hosted]==0.2.0", "llm-interface[openai]==0.1.0a1"} <= declared:
        raise BundleError("bundle requires the canonical modular-agents and llm-interface releases")
    files = {
        "main.py": (runtime / "main.py").read_bytes(),
        "agent_config.json": _json(config),
        "tool_schemas.json": _json(definition.tools.schemas),
        "requirements.txt": requirement_bytes,
    }
    for name, source in package_sources.items():
        files.update(_source_files(Path(source), name))
    if sum(map(len, files.values())) > MAX_SOURCE_BYTES:
        raise BundleError("bundle source exceeds the uncompressed size limit")
    for name, content in files.items():
        if _SECRET.search(content):
            raise BundleError(f"credential-shaped content refused in {name}")
    files["runtime_manifest.json"] = _json({
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    })
    metadata = {
        "description": " ".join(definition.spec.description.split())[:512],
        "definition": {
            "kind": "hosted",
            "protocol_versions": [{"protocol": "invocations", "version": "2.0.0"}],
            "cpu": cpu,
            "memory": memory,
            "code_configuration": {
                "runtime": "python_3_13",
                "entry_point": ["python", "main.py"],
                "dependency_resolution": "remote_build",
            },
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    zip_bytes = buffer.getvalue()
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise BundleError("zip exceeds the 64 MiB local limit")
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    metadata_bytes = _json(metadata)
    artifact_id = hashlib.sha256(zip_bytes + metadata_bytes).hexdigest()
    manifest = {
        "sha256": checksum,
        "artifact_id": artifact_id,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    directory = Path(output_dir) / artifact_id
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "agent.zip": zip_bytes, "metadata.json": metadata_bytes, "manifest.json": _json(manifest),
    }.items():
        path = directory / name
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                raise BundleError("existing content-addressed artifact has been modified")
        else:
            with path.open("xb") as output:
                output.write(content)
    return load_bundle(directory)


def inspect_source(function: Any) -> str:
    import inspect

    source = inspect.getsourcefile(inspect.unwrap(function))
    if not source:
        raise BundleError("tool source cannot be located")
    return source


def load_bundle(directory: Path) -> Bundle:
    """Read back all artifact bytes, verifying zip, metadata and member integrity."""
    directory = Path(directory)
    for name in ("agent.zip", "metadata.json", "manifest.json"):
        if (directory / name).is_symlink():
            raise BundleError("artifact files must not be symlinks")
    try:
        zip_path = directory / "agent.zip"
        payload = zip_path.read_bytes()
        metadata_bytes = (directory / "metadata.json").read_bytes()
        metadata = json.loads(metadata_bytes)
        manifest = json.loads((directory / "manifest.json").read_bytes())
        checksum = hashlib.sha256(payload).hexdigest()
        artifact_id = hashlib.sha256(payload + metadata_bytes).hexdigest()
        if checksum != manifest["sha256"] or artifact_id != manifest["artifact_id"]:
            raise BundleError("bundle digest does not match its manifest")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(manifest["files"]):
                raise BundleError("zip members do not match the manifest")
            for name in names:
                if name.startswith("/") or ".." in Path(name).parts:
                    raise BundleError("zip member escapes the bundle")
                if hashlib.sha256(archive.read(name)).hexdigest() != manifest["files"][name]:
                    raise BundleError("zip member digest differs")
            config = json.loads(archive.read("agent_config.json"))
            runtime_sha256 = hashlib.sha256(archive.read("runtime_manifest.json")).hexdigest()
        return Bundle(directory, zip_path, checksum, artifact_id, runtime_sha256, metadata, config)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as failure:
        raise BundleError("artifact is incomplete or fails integrity verification") from failure