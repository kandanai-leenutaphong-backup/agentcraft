"""Bounded public-reference acquisition and offline inventory verification."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

PROJECT = Path(__file__).resolve().parents[3]
PIN = "2c6468359916f0cec2bb7a6f91a108a4747837b58fbfe0ad0d877adba6decd6b"
ALLOWED = {"learn.microsoft.com", "azure.microsoft.com", "www.microsoft.com"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


class Article(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.main = 0
        self.hidden = 0
        self.parts = []
        self.links = []
        self.heading = None
        self.headings = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "main":
            self.main += 1
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if self.main and not self.hidden:
            if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
                self.parts.append("\n")
            if tag in {"h1", "h2", "h3", "h4"}:
                self.heading = []
            if tag == "a" and attrs.get("href"):
                self.anchor = {"url": urljoin(self.url, attrs["href"]), "text": ""}

    def handle_endtag(self, tag):
        if tag == "main":
            self.main = max(0, self.main - 1)
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"h1", "h2", "h3", "h4"} and self.heading is not None:
            self.headings.append(" ".join(self.heading).strip())
            self.heading = None
        if tag == "a" and self.anchor is not None:
            self.links.append(self.anchor)
            self.anchor = None

    def handle_data(self, data):
        if self.main and not self.hidden:
            self.parts.append(data)
            if self.heading is not None:
                self.heading.append(data.strip())
            if self.anchor is not None:
                self.anchor["text"] += data


def excerpt(text, terms):
    text = re.sub(r"[ \t]+", " ", unescape(text))
    text = re.sub(r"\n\s*\n", "\n", text).strip()
    chunks = [text[:3500]]
    for term in terms:
        match = re.search(re.escape(term), text, re.I)
        if match and match.start() > 3500:
            chunks.append(text[max(0, match.start() - 180):match.end() + 1000])
    return "\n[... excerpt boundary ...]\n".join(chunks)[:10000], len(text)


def acquire(targets, output):
    from webres import AcquisitionError, fetch
    from webres.cli.fetch_page import to_text

    output = output.resolve()
    output.relative_to(PROJECT)
    if output.exists():
        raise ValueError("output already exists; choose a fresh project-relative output")
    rows = json.loads(targets.read_text())
    assert len({row["name"] for row in rows}) == len(rows)
    receipts = []
    for row in rows:
        url = row["url"]
        assert urlsplit(url).scheme == "https" and urlsplit(url).hostname in ALLOWED
        started = datetime.now(timezone.utc).isoformat()
        record = {"id": row.get("id", row["name"]), "name": row["name"], "url": url,
                  "started_at": started, "source_revision": None, "live_integration": "not_verified"}
        try:
            payload, provenance = fetch(url, timeout=30, obey_robots=True)
            record["provenance"] = asdict(provenance)
            record["source_payload_sha256"] = digest(payload)
            record["status"] = provenance.status
            record["title"] = provenance.title or row["name"]
            text = payload.decode("utf-8", errors="replace")
            if "json" in provenance.content_type:
                record["navigation"] = json.loads(text)
            else:
                parser = Article(url)
                parser.feed(text)
                record["headings"] = parser.headings
                record["links"] = parser.links[:800]
                record["excerpt"], record["original_text_characters"] = excerpt(
                    "".join(parser.parts) or to_text(text), row.get("terms", []))
            record["retention"] = "Limited extracted reference; original payload not retained. Microsoft owns source."
        except (AcquisitionError, TimeoutError, ValueError) as error:
            record["status"] = "failed"
            record["error"] = str(error)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        path = output / (row["name"] + ".json")
        save(path, record)
        receipts.append({"id": record["id"], "path": path.relative_to(PROJECT).as_posix(),
                         "sha256": digest(path.read_bytes()), "status": record["status"]})
        print(json.dumps({"id": record["id"], "status": record["status"],
                          "title": record.get("title"), "error": record.get("error")}), flush=True)
    save(output / "catalogue.json", receipts)


def prior(source, output):
    output = output.resolve()
    output.relative_to(PROJECT)
    rows = json.loads((source / "catalogue.json").read_text())
    receipts = []
    for number, row in enumerate(rows, 1):
        path = source / row["path"]
        payload = path.read_bytes()
        assert digest(payload) == row["sha256"], path
        data = json.loads(payload)
        text, size = excerpt(data.get("text", ""), ["preview", "cost", "limit", "config", "Responses", "protocol", "private", "generally available", "supported", "endpoint"])
        record = {"id": f"P{number:02}", "name": row["name"], "url": row["url"],
                  "title": data.get("title", row["name"]), "status": row["status"],
                  "fetched_at": data.get("fetched_at", row["retrieved_at"]),
                  "source_revision": data.get("modified"), "origin": str(path),
                  "origin_sha256": row["sha256"], "origin_catalogue_entry": row,
                  "excerpt": text, "original_text_characters": size,
                  "headings": data.get("headings", []), "links": data.get("links", []),
                  "warnings": data.get("warnings", []), "live_integration": "not_verified",
                  "retention": "Hash-verified derivative of prior evidence; not a fresh fetch. Microsoft owns source."}
        target = output / (record["id"] + ".json")
        save(target, record)
        receipts.append({"id": record["id"], "path": target.relative_to(PROJECT).as_posix(),
                         "sha256": digest(target.read_bytes()), "status": record["status"]})
    save(output / "catalogue.json", receipts)
    print(json.dumps({"prior_verified": len(receipts), "output": str(output)}))


def verify():
    assert digest((PROJECT / "constitution/constitution.yaml").read_bytes()) == PIN
    parsed = 0
    for path in PROJECT.rglob("*.json"):
        if "records" not in path.relative_to(PROJECT).parts:
            json.loads(path.read_text())
            parsed += 1
    sources = {}
    batches = {}
    for catalogue in (PROJECT / "results/20260921-research").rglob("catalogue.json"):
        timestamps = []
        for row in json.loads(catalogue.read_text()):
            assert digest((PROJECT / row["path"]).read_bytes()) == row["sha256"], row
            assert row["id"] not in sources, "duplicate source id"
            sources[row["id"]] = row
            record = json.loads((PROJECT / row["path"]).read_text())
            if record.get("started_at") and record.get("finished_at"):
                timestamps.append((record["started_at"], record["finished_at"]))
        if timestamps:
            started = min(item[0] for item in timestamps)
            finished = max(item[1] for item in timestamps)
            batches[catalogue.parent.name] = {
                "started_at": started, "finished_at": finished, "sources": len(timestamps),
                "observed_wall_seconds": (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(),
                "scope": "UTC wall-clock acquisition interval, not whole-stage effort or monotonic duration"}
    inventory = PROJECT / "FEATURES.md"
    features = []
    if inventory.exists():
        features = re.findall(r"^\| ([A-Z]{2}\d{2}) \|", inventory.read_text(), re.M)
        assert len(features) == len(set(features)), "duplicate feature id"
        references = re.findall(r"SOURCES\.md#([a-z]\d+)", inventory.read_text())
        assert all(reference.upper() in sources for reference in references), "unknown source id"
        assert all(sources[reference.upper()]["status"] == 200 for reference in references), "failed source cited as feature evidence"
        feature_rows = [line for line in inventory.read_text().splitlines() if re.match(r"\| [A-Z]{2}\d{2} \|", line)]
        assert all(len(line.split("|")) == 9 for line in feature_rows), "malformed feature columns"
    source_doc = PROJECT / "SOURCES.md"
    if source_doc.exists():
        for reference in re.findall(r"SOURCES\.md#([a-z]\d+)", inventory.read_text()):
            assert f'id="{reference}"' in source_doc.read_text(), "missing source anchor"
    source_index = PROJECT / "dataset/source-index.json"
    if source_index.exists():
        indexed = json.loads(source_index.read_text())
        assert {row["id"] for row in indexed} == set(sources), "source index mismatch"
        assert all(row["sha256"] == sources[row["id"]]["sha256"] for row in indexed)
    manifest = json.loads((PROJECT / "dataset/manifest.json").read_text())
    if manifest.get("research_outputs"):
        assert manifest["research_outputs"]["feature_entries"] == len(features)
        assert manifest["research_outputs"]["feature_families"] == len({item[:2] for item in features})
    links = 0
    markdown = list(PROJECT.glob("*.md")) + list((PROJECT / "results/20260921-research/evidence").glob("*.md"))
    for path in markdown:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent / target.split("#")[0]).exists(), (path.name, target)
            links += 1
    from collections import Counter

    artifacts = markdown + list((PROJECT / "dataset").glob("*.json")) + [Path(__file__).resolve()]
    local_references = ["docs/README.md", "libraries/capabilities.json", "libraries/llm-interface/README.md",
                        "libraries/modular-agents/README.md", ".github/skills/agent-optimization/CONTRACT.md",
                        "libraries/azure-data-connectors/README.md"]
    report = {"status": "pass", "verified_at": datetime.now(timezone.utc).isoformat(),
              "constitution_sha256": PIN, "json_parsed": parsed,
              "source_receipts": len(sources), "features": len(features),
              "relative_links": links, "families": dict(sorted(Counter(item[:2] for item in features).items())),
              "source_statuses": dict(Counter(str(row["status"]) for row in sources.values())),
              "acquisition_batches": batches,
              "artifacts": [{"path": path.relative_to(PROJECT).as_posix(), "sha256": digest(path.read_bytes())}
                            for path in sorted(artifacts)],
              "local_reference_hashes": [{"repository_path": path, "sha256": digest((PROJECT.parents[2] / path).read_bytes())}
                                         for path in local_references],
              "limits": "No cloud, model or integration checks. Source payload hashes are not backups. Whole-stage duration, host effort, tokens and assistance cost unknown."}
    print(json.dumps(report, indent=2))
    return report


def index():
    rows = []
    prior_targets = []
    for catalogue in sorted((PROJECT / "results/20260921-research").rglob("catalogue.json")):
        for receipt in json.loads(catalogue.read_text()):
            path = PROJECT / receipt["path"]
            assert digest(path.read_bytes()) == receipt["sha256"]
            source = json.loads(path.read_text())
            observed = source.get("fetched_at") or source.get("provenance", {}).get("retrieved_at")
            status = "fresh HTTP " + str(source["status"])
            if source.get("origin"):
                status = "prior HTTP " + str(source["status"]) + "; hash-verified, not refetched"
                prior_targets.append({"id": source["id"], "name": source["id"], "url": source["url"],
                                      "notes": "Refresh to a new output; preserve historical evidence"})
            if "/api/search?" in source["url"]:
                status += "; discovery only"
            if source["status"] != 200:
                status += "; NOT feature evidence"
            if source["name"] == "foundry-toc":
                status += "; navigation, not release proof"
            rows.append({"id": source["id"], "url": source["url"], "title": source["title"],
                         "observed_at": observed, "availability": status,
                         "source_revision": source.get("source_revision"),
                         "evidence": receipt["path"], "sha256": receipt["sha256"]})
    rows.sort(key=lambda row: row["id"])
    save(PROJECT / "dataset/source-index.json", rows)
    save(PROJECT / "dataset/prior-targets.json", sorted(prior_targets, key=lambda row: row["id"]))
    source_doc = PROJECT / "SOURCES.md"
    document = source_doc.read_text()
    marker = "<!-- GENERATED SOURCE INDEX -->"
    assert document.count(marker) == 1 and document.rstrip().endswith(marker)
    table = ["", "| ID | Official title / URL | Observed UTC | Availability / retained evidence |",
             "| --- | --- | --- | --- |"]
    for row in rows:
        title = row["title"].replace("|", "&#124;").replace("\n", " ")
        table.append(f'| <a id="{row["id"].lower()}"></a>{row["id"]} | [{title}]({row["url"]}) | '
                     f'{row["observed_at"] or "unknown"} | {row["availability"]}; [extract]({row["evidence"]}) |')
    source_doc.write_text(document + "\n".join(table) + "\n", encoding="utf-8")
    verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["acquire", "prior", "verify", "index"])
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    assert digest((PROJECT / "constitution/constitution.yaml").read_bytes()) == PIN
    if args.action == "acquire":
        acquire(args.targets, args.out)
    elif args.action == "prior":
        prior(args.source, args.out)
    elif args.action == "index":
        index()
    else:
        report = verify()
        if args.out:
            args.out.resolve().relative_to(PROJECT)
            save(args.out, report)


if __name__ == "__main__":
    main()