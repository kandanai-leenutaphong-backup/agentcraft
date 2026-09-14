"""The blob write plane — the four lies, and the verb that must not exist.

Framework-free, in the style of ``selftest.py``: no SDK, no network, no
credential. Every double models a behaviour blob storage actually has.

Run: ``python3 tests/unit/test_blob_write.py``
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.blobs.write import BlobObjects  # noqa: E402
from azdata.core.crud import WritePolicy  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(label: str, condition: bool) -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}")


class NotFound(Exception):
    __name__ = "ResourceNotFoundError"
    status_code = 404


class Exists(Exception):
    status_code = 409


NotFound.__name__ = "ResourceNotFoundError"


class FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class FakeProperties:
    def __init__(self, size: int, content_type: str, deleted: bool = False) -> None:
        self.size = size
        self.content_settings = type("S", (), {"content_type": content_type})()
        self.last_modified = "2026-09-01T00:00:00Z"
        self.etag = '"0x1"'
        self.deleted = deleted


class FakeBlob:
    def __init__(self, container: "FakeContainer", name: str) -> None:
        self._container = container
        self._name = name

    def upload_blob(self, data: bytes, *, overwrite: bool, content_settings: Any) -> None:
        self._container.calls.append(("upload", self._name, overwrite))
        if self._name in self._container.objects and not overwrite:
            raise Exists("blob already exists")
        self._container.objects[self._name] = (
            bytes(data),
            getattr(content_settings, "content_type", ""),
        )

    def get_blob_properties(self) -> FakeProperties:
        if self._name in self._container.soft_deleted:
            return FakeProperties(0, "", deleted=True)
        if self._name not in self._container.objects:
            raise NotFound("no such blob")
        data, content_type = self._container.objects[self._name]
        return FakeProperties(len(data), content_type)

    def download_blob(self, *, offset: int, length: int) -> FakeDownload:
        data, _ = self._container.objects[self._name]
        return FakeDownload(data[offset : offset + length])

    def delete_blob(self) -> None:
        self._container.calls.append(("delete", self._name, None))
        if self._name not in self._container.objects:
            raise NotFound("no such blob")
        del self._container.objects[self._name]


class FakeContainer:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.soft_deleted: set[str] = set()
        self.calls: list[tuple[str, str, Any]] = []

    def get_blob_client(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def list_blobs(self, *, name_starts_with: str | None = None) -> list[Any]:
        rows = []
        for name, (data, content_type) in sorted(self.objects.items()):
            if name_starts_with and not name.startswith(name_starts_with):
                continue
            rows.append(
                type(
                    "B",
                    (),
                    {
                        "name": name,
                        "size": len(data),
                        "content_settings": type(
                            "S", (), {"content_type": content_type}
                        )(),
                        "last_modified": "2026-09-01T00:00:00Z",
                    },
                )()
            )
        return rows


def objects(container: FakeContainer, policy: WritePolicy) -> BlobObjects:
    # ContentSettings is loaded from the SDK; substitute a local stand-in so
    # the test needs no azure-storage-blob installed.
    connector = BlobObjects(container_client=container, policy=policy)
    connector._content_settings = lambda content_type: type(  # noqa: SLF001
        "S", (), {"content_type": content_type}
    )()
    return connector


async def main() -> None:
    print("blob write plane")

    print("\ndenied by default")
    container = FakeContainer()
    reader = objects(container, WritePolicy.read_only())
    payload = json.loads(await reader.upload([{"name": "a.txt", "content": "x"}]))
    check("a read-only policy refuses upload", payload.get("error") is not None)
    check("and writes nothing", container.objects == {})
    payload = json.loads(await reader.delete(["a.txt"]))
    check("a read-only policy refuses delete", payload.get("error") is not None)

    print("\nwrite is a separate grant from delete")
    container = FakeContainer()
    writer = objects(container, WritePolicy.writable(verify_writes=False))
    payload = json.loads(await writer.upload([{"name": "a.txt", "content": "x"}]))
    check("upload with a write grant succeeds", payload.get("ok") is True)
    payload = json.loads(await writer.delete(["a.txt"]))
    check("delete without allow_delete is still refused", payload.get("error") is not None)
    check("and the blob survives", "a.txt" in container.objects)

    print("\ncreate refuses an existing name, upload overwrites it")
    container = FakeContainer()
    both = objects(
        container, WritePolicy.writable(allow_delete=True, verify_writes=False)
    )
    await both.upload([{"name": "a.txt", "content": "first"}])
    payload = json.loads(await both.create([{"name": "a.txt", "content": "second"}]))
    check("create on an existing name reports a failure", payload.get("failed"))
    check("and does not overwrite", container.objects["a.txt"][0] == b"first")
    payload = json.loads(await both.upload([{"name": "a.txt", "content": "second"}]))
    check("upload overwrites", container.objects["a.txt"][0] == b"second")
    check("and reports one success", payload.get("count") == 1)
    check(
        "create was sent with overwrite=False",
        ("upload", "a.txt", False) in container.calls,
    )

    print("\na delete of a missing blob is a failed delete, not a success")
    payload = json.loads(await both.delete(["absent.txt"]))
    failed = payload.get("failed") or []
    check("the missing name is reported failed", len(failed) == 1)
    check("with a reason naming absence", "no blob" in str(failed[0].get("detail")))

    print("\nsoft delete cannot make a delete verify falsely")
    container = FakeContainer()
    verified = objects(
        container, WritePolicy.writable(allow_delete=True, verify_writes=True)
    )
    container.objects["s.txt"] = (b"x", "text/plain")
    container.soft_deleted.add("s.txt")
    # The blob is still readable through properties; the reader must treat a
    # soft-deleted blob as absent or the verification below is a lie.
    check("a soft-deleted blob reads as absent", await verified._do_read("s.txt") is None)

    print("\nverification catches a write that did not land")
    container = FakeContainer()
    liar = objects(
        container,
        WritePolicy.writable(verify_writes=True).with_overrides(
            verify_attempts=2, verify_delay_secs=0.01
        ),
    )
    original = container.get_blob_client

    class Swallow(FakeBlob):
        def upload_blob(self, data: bytes, *, overwrite: bool, content_settings: Any) -> None:
            return None  # accepted, stored nowhere

    container.get_blob_client = lambda name: Swallow(container, name)  # type: ignore[assignment]
    payload = json.loads(
        await liar.upload(
            [{"name": "ghost.txt", "content": "x"}], verify=True
        )
    )
    check("an accepted write that never appears fails", payload.get("error") is not None)
    container.get_blob_client = original  # type: ignore[assignment]

    print("\nprefix listing is bounded and is not a query language")
    container = FakeContainer()
    lister = objects(container, WritePolicy.read_only())
    for index in range(10):
        container.objects[f"logs/{index}.txt"] = (b"x", "text/plain")
        container.objects[f"other/{index}.txt"] = (b"x", "text/plain")
    payload = json.loads(await lister.query("logs/"))
    check("a prefix listing returns only the prefix", payload["count"] == 10)
    check("every row carries the prefix", all(r["name"].startswith("logs/") for r in payload["results"]))
    payload = json.loads(await lister.query("", max_rows=3))
    check("a listing is capped by max_rows", payload["count"] == 3)

    print("\ncontent is capped and reports truncation")
    container = FakeContainer()
    container.objects["big.bin"] = (b"0123456789", "application/octet-stream")
    peeker = objects(container, WritePolicy.read_only())
    got = await peeker.content("big.bin", max_bytes=4)
    check("only max_bytes are returned", got is not None and got["data"] == b"0123")
    check("truncation is reported", got is not None and got["truncated"] is True)
    check("the true size survives", got is not None and got["size"] == 10)
    check("a missing blob is None", await peeker.content("absent", max_bytes=4) is None)

    print("\nthe container verbs do not exist")
    for verb in (
        "create_container",
        "delete_container",
        "create_account",
        "delete_account",
        "set_container_access_policy",
    ):
        check(f"BlobObjects has no {verb}", not hasattr(BlobObjects, verb))

    print()
    if FAILED:
        print(f"{len(FAILED)} check(s) failed:")
        for label in FAILED:
            print(f"  - {label}")
        sys.exit(1)
    print(f"blob write plane: {PASSED} checks passed")


if __name__ == "__main__":
    asyncio.run(main())
