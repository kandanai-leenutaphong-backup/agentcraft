"""Agent package and build-context identity: allowlisted package files, source manifest, release label, staging.

The image layout (runtime files, Dockerfile, vendored libraries, runtime self-check) is the caller's
`ImageLayout`; everything here is layout-independent.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
from typing import Any, Protocol

from ..core import RefusedError, sha256_hex
from ..evaluation import validate_dataset_version

PACKAGE_IMAGE_DIR = "package"
MAX_PACKAGE_FILES = 256
MAX_PACKAGE_FILE_BYTES = 1024 * 1024
MODULE_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PACKAGE_SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|(?i:account_?key|shared_?access_?key)\s*[=:]\s*[A-Za-z0-9+/]{16,}|(?i:sharedaccesssignature)"
    r"|[?&]sig=[A-Za-z0-9%+/=]{16,}|\bghp_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|(?i:client_secret|password|passwd|api_?key|secret|token)\s*[=:]\s*[\"'][^\"'\s]{8,}[\"']")


class ImageLayout(Protocol):
    """Caller-owned image layout, supplied at the edge through `Clients.layout`."""

    def build_inputs(self, package: Path | None) -> dict[str, Path]:
        """Exact build context `{context-relative name: file}`; package files under `package/`."""

    def package_config(self, package: Path | None) -> dict[str, Any]:
        """`{agent, model, tools}` of the package's default agent; refuses an invalid package."""

    def self_check(self) -> dict[str, Any]:
        """Offline checks run before any billable build; raises on failure."""


def contained(path: Path, root: Path) -> Path:
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise RefusedError("source_path", "build source must be a non-symlink inside its owner")
    return path


def package_allowed(name: str) -> bool:
    parts = name.split("/")
    if any(part.startswith(".") for part in parts):
        return False
    if name == "configuration.yaml":
        return True
    if parts[0] == "prompts":
        return len(parts) > 1 and name.endswith((".md", ".txt"))
    return name.endswith(".py") and all(MODULE_PART.fullmatch(part) for part in [*parts[:-1], parts[-1][:-3]])


def check_package_content(files: dict[str, Path]) -> None:
    """Size, text and secret-shape refusals; messages name the file, never the content."""
    if len(files) > MAX_PACKAGE_FILES:
        raise RefusedError("package_size", f"package exceeds {MAX_PACKAGE_FILES} files")
    if "configuration.yaml" not in files:
        raise RefusedError("package_config", "package has no configuration.yaml")
    for name, path in files.items():
        data = path.read_bytes()
        if len(data) > MAX_PACKAGE_FILE_BYTES:
            raise RefusedError("package_size", f"package file exceeds {MAX_PACKAGE_FILE_BYTES} bytes: {name}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RefusedError("package_binary", f"package file is not UTF-8 text: {name}") from error
        if PACKAGE_SECRET.search(text):
            raise RefusedError("package_secret", f"secret-shaped content refused: {name}; use managed identity")


def package_inputs(root: Path, *, include: Callable[[str], bool] | None = None) -> dict[str, Path]:
    """Package-relative files under `root` (optionally only names passing `include`).

    Allowlist: `configuration.yaml`, `prompts/**/*.{md,txt}`, `*.py` tool modules with identifier names;
    `__pycache__` is skipped; any other file, dotfile or symlink refuses.
    """
    files: dict[str, Path] = {}
    if root.is_symlink() or not root.is_dir():
        raise RefusedError("package_path", "package folder missing or symlinked")
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            continue
        name = relative.as_posix()
        if include is not None and not include(name):
            continue
        if path.is_symlink():
            raise RefusedError("package_symlink", f"symlink in package refused: {name}")
        if path.is_dir():
            continue
        if not package_allowed(name):
            raise RefusedError("package_file", f"file outside the package allowlist: {name}")
        files[name] = contained(path, root)
    check_package_content(files)
    return files


def check_package_tools(tools: Any, files: dict[str, Path]) -> list[str]:
    """Every tool `module:function` must resolve to a module inside the package."""
    if not isinstance(tools, list):
        raise RefusedError("package_config", "agent model and tool list required")
    for reference in tools:
        module, _, function = str(reference).partition(":")
        path = module.replace(".", "/")
        if not MODULE_PART.fullmatch(function) or not all(MODULE_PART.fullmatch(part) for part in module.split(".")) \
                or not ({path + ".py", path + "/__init__.py"} & set(files)):
            raise RefusedError("package_tool", f"tool is not a module:function inside the package: {reference}")
    return list(tools)


def package_digest(files: dict[str, str]) -> str:
    """sha256 of json.dumps({package-relative path: file sha256}, sort_keys=True); the source digest's encoding."""
    return sha256_hex(json.dumps(files, sort_keys=True).encode())


def source_manifest(inputs: dict[str, Path]) -> dict[str, Any]:
    files = {name: sha256_hex(path.read_bytes()) for name, path in sorted(inputs.items())}
    prefix = PACKAGE_IMAGE_DIR + "/"
    package = {name[len(prefix):]: digest for name, digest in files.items() if name.startswith(prefix)}
    return {"files": files, "sha256": package_digest(files), "package_files": package,
            "package_sha256": package_digest(package), "config_sha256": files[prefix + "configuration.yaml"]}


def release_label(manifest: dict[str, Any]) -> str:
    """Image tag, ledger key and eval label (<= 50 chars) naming source and package; full digests stay the pins."""
    return validate_dataset_version(f"src-{manifest['sha256'][:24]}-pkg-{manifest['package_sha256'][:16]}")


def stage_context(inputs: dict[str, Path], manifest: dict[str, Any], directory: Path,
                  manifest_name: str = "app/source-manifest.json") -> Path:
    """Copy exactly the manifested bytes into `directory` and write the manifest where the runtime reads it."""
    for name, path in inputs.items():
        content = path.read_bytes()
        if sha256_hex(content) != manifest["files"][name]:
            raise RefusedError("source_changed", "source changed during staging")
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (directory / manifest_name).parent.mkdir(parents=True, exist_ok=True)
    (directory / manifest_name).write_text(json.dumps(manifest, sort_keys=True))
    return directory
