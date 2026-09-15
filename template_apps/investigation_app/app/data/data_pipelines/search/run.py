"""Publish the pinned ATT&CK knowledge index, or retire a named obsolete index.

    python3 -m app.data.data_pipelines.search.run publish \
        --endpoint https://<svc>.search.windows.net

    python3 -m app.data.data_pipelines.search.run retire \
        --endpoint https://<svc>.search.windows.net --index perth-events

    ./deploy/deploy.sh search-load -e prod        coordinates from the environment file

The index name is derived from the pinned build's own retrieval stamp, so the same inputs
publish the same name. `retire` deletes exactly the indexes named on the command line and
reads each back; there is no wildcard and no `--all`.

The caller authenticates as itself with `DefaultAzureCredential`; there is no key to pass,
because the service has local authentication disabled.

Exit codes: 0 done and read back, 1 refused or failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from template_foundations.azure_search import SearchConfig, SearchError, SearchIndexClient

from .documents import ANALYTIC, SITUATION_TYPE, build_document, mitre_index
from .load import LoadRefused, ensure_index, load_documents
from .sources import NORMALIZED_DIR, display_name, index_name, mitre_provenance, mitre_records

#: A published index that reports no documents is a failed publish, not an empty one.
MIN_DOCUMENTS = 1


def _settled_count(client: SearchIndexClient, index: str, expected: int,
                   *, attempts: int = 15) -> int:
    """The queryable document count once it stops moving. Indexing is not instantaneous."""
    count = client.search_count(index)
    for _ in range(attempts):
        if count >= expected:
            return count
        time.sleep(2.0)
        count = client.search_count(index)
    return count


def _publish(client: SearchIndexClient, args: argparse.Namespace,
             say) -> tuple[int, dict]:
    directory = Path(args.normalized) if args.normalized else NORMALIZED_DIR
    provenance = mitre_provenance(directory)
    name = args.index or index_name(provenance["retrieved_at"])
    say(f"index {name}  ({display_name(provenance['retrieved_at'])})")

    records = list(mitre_records(directory))
    if not records:
        raise LoadRefused(f"no ATT&CK records under {directory}")
    kinds = {SITUATION_TYPE: 0, ANALYTIC: 0}
    for record in records:
        kinds[SITUATION_TYPE if record.get("type_id") else ANALYTIC] += 1

    state = ensure_index(client, mitre_index(name))
    say(f"index {name}: {state}")
    report = load_documents(
        client, index=name, rows=records, build=build_document,
        checkpoint=Path(args.checkpoint) if args.checkpoint else None,
        progress=None if args.quiet else (lambda read, sent: say(f"{read} read, {sent} uploaded")),
    )
    count = _settled_count(client, name, len(records))
    payload = report.as_dict() | {
        "index": name,
        "display_name": display_name(provenance["retrieved_at"]),
        "document_count": count,
        "expected": len(records),
        "situation_types": kinds[SITUATION_TYPE],
        "analytics": kinds[ANALYTIC],
        "provenance": provenance,
    }
    if count < MIN_DOCUMENTS or count != len(records):
        print(f"FAILED: index {name} reports {count} documents, expected {len(records)}",
              file=sys.stderr)
        return 1, payload
    say(f"{name}: {count} documents, read back from the service")
    return 0, payload


def _retire(client: SearchIndexClient, args: argparse.Namespace, say) -> tuple[int, dict]:
    """Delete exactly the named indexes and prove each is gone."""
    results = []
    failed = False
    for name in args.index:
        existed = client.index_exists(name)
        client.delete_index(name, missing_ok=True)
        still_there = client.index_exists(name)
        results.append({"index": name, "existed": existed, "present_after": still_there})
        say(f"{name}: existed={existed} present_after={still_there}")
        failed = failed or still_there
    if failed:
        print("FAILED: an index named for deletion is still present", file=sys.stderr)
    return (1 if failed else 0), {"retired": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("publish", "retire"))
    parser.add_argument("--endpoint", required=True,
                        help="https://<service>.search.windows.net")
    parser.add_argument("--index", action="append", default=[],
                        help="publish: override the derived name. retire: name to delete, "
                             "repeatable. There is no wildcard.")
    parser.add_argument("--normalized", default="",
                        help="override the normalised corpus directory")
    parser.add_argument("--checkpoint", default="", help="resume file; deleted on success")
    parser.add_argument("--report", default="", help="write the report as JSON here")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    def say(message: str) -> None:
        if not args.quiet:
            print(f"   {message}", flush=True)

    client = SearchIndexClient(SearchConfig(endpoint=args.endpoint))
    try:
        if args.command == "retire":
            if not args.index:
                print("FAILED: retire needs at least one --index", file=sys.stderr)
                return 1
            code, payload = _retire(client, args, say)
        else:
            if len(args.index) > 1:
                print("FAILED: publish writes one index", file=sys.stderr)
                return 1
            args.index = args.index[0] if args.index else ""
            code, payload = _publish(client, args, say)
    except (LoadRefused, SearchError, FileNotFoundError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if code == 0 and args.command == "publish" and args.checkpoint:
        checkpoint = Path(args.checkpoint)
        if checkpoint.exists():
            checkpoint.unlink()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
