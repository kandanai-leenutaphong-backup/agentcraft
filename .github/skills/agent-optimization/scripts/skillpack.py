"""Verify or extract the independent optimization source payload without installing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile


PACK = Path(__file__).resolve().parents[1]
FORMAT = "agent-optimization-skillpack-v1"
PAYLOAD = "assets/implementation.zip"
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 4000
ROOTS = {"runtime", "example"}


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(name):
    if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
            or PurePosixPath(name).is_absolute() or ":" in name.split("/")[0]
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError("Payload paths must be normalized relative paths")
    if name.split("/")[0] not in ROOTS:
        raise ValueError("Unexpected payload root")
    return name


def verify(pack=PACK):
    pack = Path(pack).resolve()
    manifest_path = pack / "manifest.json"
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Manifest exceeds size bound")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != FORMAT or manifest.get("payload", {}).get("path") != PAYLOAD:
        raise ValueError("Unsupported skillpack manifest")
    payload = pack / PAYLOAD
    if file_digest(payload) != manifest["payload"]["sha256"]:
        raise ValueError("Payload SHA-256 mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Invalid payload inventory")
    expected = {}
    for entry in files:
        name = safe_path(entry["path"])
        if name in expected or type(entry.get("bytes")) is not int or entry["bytes"] < 0:
            raise ValueError("Duplicate or invalid inventory entry")
        expected[name] = entry
    with zipfile.ZipFile(payload) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(member.file_size for member in members) > MAX_BYTES:
            raise ValueError("Payload exceeds expansion bounds")
        names = set()
        for member in members:
            name = safe_path(member.filename)
            kind = stat.S_IFMT(member.external_attr >> 16)
            if member.is_dir() or kind not in (0, stat.S_IFREG) or name in names:
                raise ValueError("Payload requires unique regular files, not links or devices")
            names.add(name)
            if name not in expected or member.file_size != expected[name]["bytes"]:
                raise ValueError("Payload membership or size mismatch")
            digest = hashlib.sha256()
            with archive.open(member) as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected[name]["sha256"]:
                raise ValueError("Payload file hash mismatch")
        if names != set(expected):
            raise ValueError("Payload inventory is incomplete")
    return manifest


def extract(destination, pack=PACK):
    manifest = verify(pack)
    destination = Path(destination).absolute()
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("Destination cannot traverse symbolic links")
    if destination.exists():
        raise ValueError("Destination already exists; choose a new empty location")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".extract-", dir=destination.parent))
    try:
        with zipfile.ZipFile(Path(pack) / PAYLOAD) as archive:
            for member in archive.infolist():
                target = staging / safe_path(member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o700 if member.external_attr >> 16 & 0o111 else 0o600)
        for entry in manifest["files"]:
            if file_digest(staging / entry["path"]) != entry["sha256"]:
                raise ValueError("Extracted file failed hash readback")
        (staging / "skillpack-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists():
            raise ValueError("Destination appeared during extraction")
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"status": "extracted", "destination": str(destination), "files": len(manifest["files"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "extract"))
    parser.add_argument("--destination", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "extract":
            if arguments.destination is None:
                raise ValueError("extract requires --destination")
            result = extract(arguments.destination)
        else:
            manifest = verify()
            result = {"status": "verified", "files": len(manifest["files"]),
                      "sha256": manifest["payload"]["sha256"]}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())