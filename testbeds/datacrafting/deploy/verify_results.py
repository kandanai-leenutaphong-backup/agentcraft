from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import json
import math
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "azure-extraction"))

from azure_extraction.contracts import METHODS, Refusal, artifact_path, documents_from_manifest, require_content, require_method, validate_input
from azure_extraction.provider import CU_API_VERSION


RECEIPT_KEYS = {"schema_version", "method", "execution", "status", "input", "started_at", "elapsed_seconds",
                "versions", "provider", "outputs", "warnings", "error"}
ACCEPTED_RECEIPTS = {"yallourn": "20260916T065358185028Z", "murray": "20260916T065409548693Z"}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments = []

    def handle_data(self, data):
        self.fragments.append(data)


def normalize(text: str) -> str:
    parser = VisibleText()
    parser.feed(text)
    parser.close()
    visible = unicodedata.normalize("NFKC", " ".join(parser.fragments)).casefold()
    return " ".join(re.findall(r"\w+(?:\.\w+)*", visible))


def phrase_present(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(normalize(phrase)) + r"(?!\w)", text) is not None


def source_observations(native: dict, text: str, probes: list[dict], relationships: list[dict]) -> dict:
    normalized = normalize(text)
    facts = [{"id": probe["id"], "category": probe["category"],
              "missing": [phrase for phrase in probe["phrases"] if not phrase_present(normalized, phrase)]}
             for probe in probes]
    tables = [table for content in native["result"]["contents"] for table in content.get("tables", [])]
    rows = []
    for probe in relationships:
        passed = False
        for table in tables:
            cells = table.get("cells", [])
            for anchor in cells:
                if normalize(anchor.get("content", "")) != normalize(probe["label"]):
                    continue
                start = anchor["rowIndex"]
                end = start + anchor.get("rowSpan", 1)
                associated = [cell for cell in cells if cell["rowIndex"] < end and cell["rowIndex"] + cell.get("rowSpan", 1) > start]
                associated.sort(key=lambda cell: (cell["rowIndex"], cell["columnIndex"]))
                row_text = normalize(" ".join(cell.get("content", "") for cell in associated))
                passed = passed or all(phrase_present(row_text, phrase) for phrase in probe["phrases"])
        rows.append({"id": probe["id"], "passed": passed})
    narrative = [fact for fact in facts if fact["category"] == "narrative"]
    if not narrative or any(fact["missing"] for fact in narrative) or not rows or any(not row["passed"] for row in rows):
        raise Refusal("CU source narrative facts or native row relationships no longer pass")
    return {"narrative": {"passed": len(narrative), "total": len(narrative)},
            "table_relationships": {"passed": len(rows), "total": len(rows)},
            "diagram_label_observations": [fact for fact in facts if fact["category"] == "diagram-label"],
            "diagram_topology_verified": False, "baseline_lexical_metrics": "historical only; raw baselines archived"}


def verify_receipt(path: Path, document, method: str) -> dict:
    model_id = require_method(method)
    receipt = json.loads(path.read_text())
    if set(receipt) != RECEIPT_KEYS or receipt["schema_version"] != 1:
        raise Refusal("Receipt shape differs from RESULT_CONTRACT")
    if receipt["method"] != method or receipt["execution"] != "azure-function":
        raise Refusal("Receipt method or execution differs from the actual Function path")
    if set(receipt["input"]) != {"file", "sha256", "bytes", "pages"} or set(receipt["outputs"]) != {"text", "markdown", "native"}:
        raise Refusal("Receipt input/output fields differ from RESULT_CONTRACT")
    if set(receipt["provider"]) != {"api_version", "model_id"}:
        raise Refusal("Receipt provider fields differ from RESULT_CONTRACT")
    if receipt["provider"] != {"api_version": CU_API_VERSION, "model_id": model_id}:
        raise Refusal("Receipt provider differs from CU GA 2025-11-01/prebuilt-layout")
    if (receipt["input"]["file"], receipt["input"]["sha256"], receipt["input"]["bytes"]) != (document.file, document.sha256, document.bytes):
        raise Refusal("Receipt does not match the immutable input manifest")
    started = datetime.fromisoformat(receipt["started_at"])
    if started.tzinfo is None or started.utcoffset().total_seconds() != 0:
        raise Refusal("Receipt timestamp is not UTC")
    elapsed = receipt["elapsed_seconds"]
    if type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0:
        raise Refusal("Receipt duration is not a measured nonnegative number")
    if not isinstance(receipt["warnings"], list) or not isinstance(receipt["versions"], dict) or not receipt["versions"]:
        raise Refusal("Receipt versions or warnings are invalid")
    outputs = {}
    for kind, relative in receipt["outputs"].items():
        if relative is None:
            continue
        artifact = (path.parent / artifact_path(relative)).resolve()
        if not artifact.is_relative_to(path.parent.resolve()) or not artifact.is_file():
            raise Refusal("Receipt output is missing or escaped its result directory")
        outputs[kind] = artifact
    if receipt["status"] != "succeeded":
        if receipt["status"] not in {"failed", "unavailable"} or not isinstance(receipt["error"], dict) or set(receipt["error"]) != {"type", "message"}:
            raise Refusal("Failed receipt does not carry the required bounded error")
        return {"receipt": receipt, "success": False}
    if receipt["error"] is not None or "text" not in outputs or "native" not in outputs:
        raise Refusal("Success is missing text/native evidence or carries an error")
    native = json.loads(outputs["native"].read_text())
    if str(native.get("status", "")).lower() != "succeeded":
        raise Refusal("Provider-native operation did not succeed")
    text, markdown, pages = require_content(native, method)
    if outputs["text"].read_text() != text or receipt["input"]["pages"] != pages:
        raise Refusal("Receipt text/pages differ from provider-native evidence")
    if (markdown is None) != ("markdown" not in outputs) or (markdown is not None and outputs["markdown"].read_text() != markdown):
        raise Refusal("Markdown differs from unmodified provider output")
    result = native["result"]
    if result.get("apiVersion") != CU_API_VERSION or result.get("analyzerId") != model_id:
        raise Refusal("Actual native API/model differs from the receipt")
    contents = result["contents"]
    summary = {"method": method, "document_id": document.id, "pages": pages, "elapsed_seconds": elapsed,
               "text_characters": len(text), "text_bytes": outputs["text"].stat().st_size,
               "native_bytes": outputs["native"].stat().st_size, "native_sha256": sha256(outputs["native"].read_bytes()).hexdigest(),
               "tables": sum(len(content.get("tables", [])) for content in contents),
               "figures": sum(len(content.get("figures", [])) for content in contents),
               "provider": receipt["provider"], "versions": receipt["versions"], "usage": result.get("usage", native.get("usage")),
               "warnings": receipt["warnings"], "cost_usd": "unknown"}
    return {"receipt": receipt, "success": True, "native": native, "text": text, "markdown": markdown, "summary": summary}


def verify_all(root: Path) -> dict:
    manifest_bytes = (root / "source_data" / "manifest.json").read_bytes()
    documents = documents_from_manifest(json.loads(manifest_bytes))
    for document in documents.values():
        validate_input((root / "source_data" / document.file).read_bytes(), document)
    selection = root / "content-understanding" / "evidence" / "selection"
    frozen = json.loads((selection / "comparison.json").read_text())
    probe_bytes = (selection / "probes.json").read_bytes()
    probes = json.loads(probe_bytes)
    if sha256(manifest_bytes).hexdigest() != frozen["source_manifest_sha256"] or sha256(probe_bytes).hexdigest() != frozen["probes_sha256"]:
        raise Refusal("Source manifest or source-reviewed probes differ from selection evidence")
    selected = []
    failures = []
    for method in METHODS:
        for document in documents.values():
            accepted = None
            for path in sorted((root / method / "results" / document.id).glob("*/receipt.json")):
                checked = verify_receipt(path, document, method)
                if checked["success"] and path.parent.name == ACCEPTED_RECEIPTS[document.id]:
                    reference = next(result for result in frozen["results"] if result["method"] == method and result["document"] == document.id)
                    if reference["receipt"] != str(path.relative_to(root)):
                        raise Refusal("Accepted CU receipt identity differs from frozen comparison")
                    for kind, expected_hash in reference["artifact_sha256"].items():
                        artifact = path if kind == "receipt" else path.parent / artifact_path(checked["receipt"]["outputs"][kind])
                        if sha256(artifact.read_bytes()).hexdigest() != expected_hash:
                            raise Refusal("Accepted CU artifact differs from its frozen selection hash")
                    facts = source_observations(checked["native"], checked["text"], probes["documents"][document.id], probes["table_relationships"][document.id])
                    accepted = checked["summary"] | {"receipt": str(path.relative_to(root)), "source_facts": facts}
                elif not checked["success"]:
                    failures.append({"receipt": str(path.relative_to(root)), "error": checked["receipt"]["error"]})
            if accepted is None:
                raise Refusal(f"Missing frozen accepted CU receipt for {document.id}")
            selected.append(accepted)
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "successful_method_document_pairs": len(selected),
            "results": selected, "retained_failed_attempts": failures, "input_hashes_verified": True,
            "receipt_contract_verified": True, "native_content_verified": True, "frozen_artifact_hashes_verified": True,
            "source_facts_verified": True, "selection_policy": "fixed accepted CU receipts, not latest success",
            "quality_winner": "CU selected for native integration on two reports; no global accuracy claim", "ongoing_cost_usd": "unknown"}


def verify_documentation(root: Path) -> dict:
    paths = [root / "README.md", root / "RESULT_CONTRACT.md", root / "deploy" / "README.md", root / "azure-extraction" / "README.md",
             root / "deploy" / "references" / "README.md", root / "deploy" / "references" / "python-bindings.md"]
    paths.extend(root / method / "SKILL.md" for method in METHODS)
    paths.extend(sorted((root / "content-understanding" / "evidence" / "selection").glob("*.md")))
    canonical = root.resolve().parents[1] / ".github" / "skills" / "azure-content-understanding" / "SKILL.md"
    links = 0
    for path in paths:
        text = path.read_text()
        if path.name == "SKILL.md" and not text.startswith("---\nname: " + path.parent.name + "\n"):
            raise Refusal("Method skill name/frontmatter does not match its folder")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not resolved.exists() and resolved != canonical:
                raise Refusal(f"Broken local documentation link in {path.name}: {target}")
            links += 1
    return {"documents_checked": len(paths), "local_links_checked": links, "method_skill_names_verified": True,
            "parent_owned_canonical_skill": "present" if canonical.exists() else "promotion pending; no runtime dependency"}