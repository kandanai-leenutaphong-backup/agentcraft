from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

import webres

from .models import ScrapeOptions, ScrapeResult


def _write_verified(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if webres.sha256_bytes(path.read_bytes()) != webres.sha256_bytes(payload):
        raise OSError("Artifact read-back did not match the written bytes")


def save_result(result: ScrapeResult, root: Path, options: ScrapeOptions) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        publisher = urlsplit(result.url).hostname or "invalid-url"
    except ValueError:
        publisher = "invalid-url"
    directory = Path(tempfile.mkdtemp(prefix=webres.slugify(publisher, 40) + "-", dir=root))
    catalogue = webres.Catalogue(directory / "manifest.pending.json")
    artifacts = {}

    def record(name: str, payload: bytes, content_type: str, function: str) -> None:
        path = directory / name
        _write_verified(path, payload)
        catalogue.record(webres.Provenance(
            source_url=result.url,
            retrieved_at=result.retrieved_at or webres.now_iso(),
            status=result.status or 0,
            content_type=content_type,
            sha256=webres.sha256_bytes(payload),
            bytes=len(payload),
            title=result.title,
            publisher=publisher,
            subject="html-acquisition",
            function=function,
            artefact=catalogue.key_for(path),
        ))

    if result.ok:
        record("page.html", result.html.encode("utf-8-sig"), "text/html; charset=utf-8", result.method)
        artifacts["html"] = "page.html"
    if result.source_html is not None:
        record("source.html", result.source_html.encode("utf-8-sig"), "text/html; charset=utf-8", "http-source")
        artifacts["source"] = "source.html"
    if result.ok and result.screenshot is not None:
        record("screenshot.png", result.screenshot, "image/png", "browser-screenshot")
        artifacts["screenshot"] = "screenshot.png"
    metadata = asdict(result)
    for name in ("html", "source_html", "screenshot"):
        metadata.pop(name)
    metadata.update({"schema_version": 1, "artifacts": artifacts, "options": asdict(options)})
    record("result.json", (json.dumps(metadata, indent=2, ensure_ascii=True) + "\n").encode(),
           "application/json", "acquisition-metadata")
    catalogue.save()
    with catalogue.path.open("rb") as stream:
        os.fsync(stream.fileno())
    catalogue.path.rename(directory / "manifest.json")
    directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    verification = verify_result(directory)
    if not verification["ok"]:
        raise OSError("Saved acquisition failed manifest read-back verification")
    return directory


def verify_result(directory: Path) -> dict[str, object]:
    directory = directory.resolve()
    errors = []
    checked = 0
    acquisition_ok = None
    try:
        manifest = directory / "manifest.json"
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
            raise ValueError("Missing, oversized, or symlinked completion manifest")
        catalogue = webres.Catalogue(manifest)
        if not 1 <= len(catalogue.entries) <= 4 or "result.json" not in catalogue.entries:
            raise ValueError("Manifest has no result record or an invalid artifact count")
        for name, entry in catalogue.entries.items():
            path = catalogue.artefact_path(name)
            expected_size = entry.get("bytes")
            if type(expected_size) is not int or not 0 <= expected_size <= 64 * 1024 * 1024:
                raise ValueError("Invalid artifact size")
            if not path.is_file() or path.stat().st_size != expected_size:
                errors.append(f"Missing or changed artifact: {name}")
            elif webres.sha256_bytes(path.read_bytes()) != entry.get("sha256"):
                errors.append(f"Hash mismatch: {name}")
            checked += 1
        if not errors:
            metadata = json.loads(catalogue.artefact_path("result.json").read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or metadata.get("schema_version") != 1 or type(metadata.get("ok")) is not bool:
                raise ValueError("Invalid result record")
            acquisition_ok = metadata["ok"]
            artifacts = metadata.get("artifacts")
            if not isinstance(artifacts, dict) or any(name not in catalogue.entries for name in artifacts.values()):
                raise ValueError("Result references an uncatalogued artifact")
            if acquisition_ok and artifacts.get("html") != "page.html":
                raise ValueError("Successful acquisition has no HTML artifact")
    except (OSError, ValueError, TypeError, webres.AcquisitionError):
        errors.append("Invalid, incomplete, or unsafe acquisition manifest")
    return {"ok": not errors, "acquisition_ok": acquisition_ok, "directory": str(directory),
            "checked": checked, "errors": errors}