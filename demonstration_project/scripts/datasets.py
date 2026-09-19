"""Acquire the two approved public datasets; retain a reproducible, content-pinned inventory."""

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request
import zipfile

from webres import USER_AGENT, fetch, open_public


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "data"
LOCK = PROJECT / "datasets.lock.json"
UWF = "https://datasets.uwf.edu/data/UWF-ZeekData22/"
HIKARI = "https://zenodo.org/records/6463389/files/ALLFLOWMETER_HIKARI2021.csv.zip?download=1"
CSV_NAME = "ALLFLOWMETER_HIKARI2021.csv"
CHUNK = 1024 * 1024
MAX_FILE = 2 * 1024**3
MAX_TOTAL = 8 * 1024**3
SOURCES = {
    "hikari-2021": {
        "publisher": "Ferriyan, Thamrin, Takeda and Murai; Zenodo record 6463389, version 1.4.0",
        "landing_page": "https://zenodo.org/records/6463389",
        "citation": "https://doi.org/10.5281/zenodo.6463389",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "scope": "HIKARI-2021 CSV archive only; no pickle files, 2022 extension or packet captures.",
    },
    "uwf-zeekdata22": {
        "publisher": "University of West Florida Cyber Analytics Research Group",
        "landing_page": "https://datasets.uwf.edu/",
        "citation": "https://doi.org/10.3390/data8010018",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "scope": "All published CSV subset files and weekly Parquet tables; no raw PCAP or original log corpus.",
    },
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path):
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            sha256.update(block)
            md5.update(block)
            size += len(block)
    return {"bytes": size, "sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


def contained(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Output path escapes dataset root")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Symlinked dataset paths are refused")
    return path


def save_new(path, value):
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text() != encoded:
            raise ValueError(f"Refusing to overwrite {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for name, value in attrs if name == "href" and value)


def listing(url):
    payload, provenance = fetch(url)
    parser = Links()
    parser.feed(payload.decode("utf-8"))
    urls = sorted({urljoin(url, link) for link in parser.links})
    return [link for link in urls if link.startswith(url) and link != url], provenance.to_dict()


def discover():
    files = [{"dataset": "hikari-2021", "url": HIKARI,
              "path": "hikari-2021/" + CSV_NAME + ".zip",
              "publisher_md5": "d7d9e277fe4a66cb00764d7f91a810dd"}]
    provenance = []
    csv_urls, page = listing(UWF + "csv/")
    provenance.append(page)
    weeks, page = listing(UWF + "parquet/")
    provenance.append(page)
    parquet_urls = []
    weeks = [url for url in weeks if re.fullmatch(r"\d{4}-\d{2}-\d{2} - \d{4}-\d{2}-\d{2}", unquote(urlsplit(url).path.rstrip("/").split("/")[-1]))]
    if not weeks or len(weeks) > 52:
        raise ValueError("Unexpected UWF weekly directory count")
    for week in weeks:
        urls, page = listing(week)
        provenance.append(page)
        parquet_urls.extend(url for url in urls if url.endswith(".parquet"))
    csv_urls = [url for url in csv_urls if url.endswith(".csv")]
    if not csv_urls or not parquet_urls or len(csv_urls) + len(parquet_urls) > 128:
        raise ValueError("Unexpected UWF table inventory")
    for url in csv_urls + parquet_urls:
        files.append({"dataset": "uwf-zeekdata22", "url": url,
                      "path": "uwf-zeekdata22/" + unquote(url.removeprefix(UWF))})
    for entry in files:
        request = Request(entry["url"], method="HEAD", headers={"User-Agent": USER_AGENT})
        with open_public(request, timeout=60) as response:
            entry["bytes"] = int(response.headers["Content-Length"])
        if not 0 < entry["bytes"] <= MAX_FILE:
            raise ValueError("Unexpected download size")
    if sum(entry["bytes"] for entry in files) > MAX_TOTAL:
        raise ValueError("Inventory exceeds the 8 GiB download ceiling; review before raising it")
    return {"schema_version": 1, "sources": SOURCES, "files": files, "index_provenance": provenance}


def check_file(path, entry):
    observed = fingerprint(path)
    for field in ("bytes", "sha256"):
        if field in entry and observed[field] != entry[field]:
            raise ValueError(f"Integrity mismatch: {entry['path']} ({field})")
    if entry.get("publisher_md5") and observed["md5"] != entry["publisher_md5"]:
        raise ValueError(f"Publisher checksum mismatch: {entry['path']}")
    suffix = Path(entry["path"]).suffix
    with path.open("rb") as stream:
        first = stream.read(4)
        if suffix == ".zip" and first != b"PK\x03\x04":
            raise ValueError("Expected a ZIP archive")
        if suffix == ".parquet":
            stream.seek(-4, os.SEEK_END)
            if first != b"PAR1" or stream.read(4) != b"PAR1":
                raise ValueError("Expected a Parquet table")
        if suffix == ".csv" and first.lstrip().startswith(b"<"):
            raise ValueError("HTML returned instead of CSV")
    return observed


def acquire(entry, root):
    destination = contained(root, entry["path"])
    receipt_path = contained(root, entry["path"] + ".receipt.json")
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if receipt and (receipt["url"] != entry["url"] or receipt["path"] != entry["path"]):
        raise ValueError("Receipt source mismatch")
    if destination.exists():
        if not receipt:
            raise ValueError(f"Existing file has no receipt: {destination}")
        check_file(destination, receipt)
        check_file(destination, entry)
        print(f"Verified, skipped: {entry['path']}", flush=True)
        return receipt
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = contained(root, entry["path"] + ".partial")
    expected = {**entry, **({"sha256": receipt["sha256"]} if receipt else {})}
    started = time.monotonic()
    with open_public(entry["url"], timeout=120) as response, partial.open("wb") as output:
        if response.status != 200:
            raise ValueError("Expected a complete HTTP 200 response")
        size = 0
        while block := response.read(CHUNK):
            size += len(block)
            if size > entry["bytes"] or time.monotonic() - started > 1800:
                raise ValueError("Download exceeds frozen size or 30-minute per-file limit")
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
        response_info = {"final_url": response.geturl(), "content_type": response.headers.get("Content-Type"),
                         "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
    observed = check_file(partial, expected)
    receipt = receipt or {**entry, **observed, **response_info, "retrieved_at": utc_now()}
    save_new(receipt_path, receipt)
    os.link(partial, destination)
    partial.unlink()
    check_file(destination, receipt)
    print(f"Downloaded: {entry['path']} ({observed['bytes']} bytes)", flush=True)
    return receipt


def extract_hikari(root, expected=None):
    source = root / "hikari-2021" / (CSV_NAME + ".zip")
    destination = contained(root, "hikari-2021/" + CSV_NAME)
    receipt_path = contained(root, "hikari-2021/" + CSV_NAME + ".receipt.json")
    if destination.exists():
        receipt = json.loads(receipt_path.read_text())
        check_file(destination, receipt)
        if expected:
            check_file(destination, expected)
        return receipt
    with zipfile.ZipFile(source) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == CSV_NAME]
        if len(matches) != 1 or not 0 < matches[0].file_size <= MAX_FILE or matches[0].is_dir():
            raise ValueError("Unexpected HIKARI CSV archive member")
        partial = contained(root, "hikari-2021/" + CSV_NAME + ".partial")
        with archive.open(matches[0]) as stream, partial.open("wb") as output:
            shutil.copyfileobj(stream, output, CHUNK)
            output.flush()
            os.fsync(output.fileno())
    receipt = {"path": "hikari-2021/" + CSV_NAME, "derived_from": "hikari-2021/" + CSV_NAME + ".zip",
               **fingerprint(partial)}
    if expected and any(receipt[field] != expected[field] for field in ("bytes", "sha256")):
        raise ValueError("Extracted CSV differs from the pinned content")
    save_new(receipt_path, receipt)
    os.link(partial, destination)
    partial.unlink()
    check_file(destination, receipt)
    return receipt


def download():
    DATA.mkdir(parents=True, exist_ok=True)
    plan_path = DATA / "download-plan.json"
    if LOCK.exists():
        plan = json.loads(LOCK.read_text())
    elif plan_path.exists():
        plan = json.loads(plan_path.read_text())
    else:
        plan = discover()
        save_new(plan_path, plan)
    required = sum(entry["bytes"] for entry in plan["files"]) + MAX_FILE
    if shutil.disk_usage(DATA).free < required:
        raise ValueError("Insufficient free space for frozen downloads and extraction")
    receipts = [acquire(entry, DATA) for entry in plan["files"]]
    derived = extract_hikari(DATA, plan.get("derived"))
    document = {**plan, "files": receipts, "derived": derived}
    if not LOCK.exists():
        save_new(LOCK, document)
    verify()


def verify():
    document = json.loads(LOCK.read_text())
    entries = [*document["files"], document["derived"]]
    for entry in entries:
        check_file(contained(DATA, entry["path"]), entry)
    print(json.dumps({"status": "verified", "files": len(entries),
                      "bytes": sum(entry["bytes"] for entry in entries),
                      "lock_sha256": fingerprint(LOCK)["sha256"],
                      "scope": "content integrity and file signatures; labels/splits not evaluated"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("download", "verify"))
    command = parser.parse_args().command
    try:
        (download if command == "download" else verify)()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(2, f"Dataset acquisition refused: {error}\n")


if __name__ == "__main__":
    main()