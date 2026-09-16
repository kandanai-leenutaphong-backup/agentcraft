"""Trusted host composition and CLI; no input-supplied code or model execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from core import InvalidInput, craft_dataset, decode_json, digest, json_bytes, read_artifacts, select_mode, write_artifacts
from operations import OperationsMode, power_only, reference, replay_review
from replay import ABLATIONS, compare, comparison_artifacts, evaluate
import schemas


MODES = {"operations": OperationsMode()}
PREDICTORS = {"power_only": power_only, "reference": reference}


def load_dataset(root: Path) -> tuple[dict, list[dict], list[dict]]:
    manifest, artifacts = read_artifacts(root)
    inputs = []
    labels = []
    for kind in ("detection", "action"):
        for suffix, schema, destination in (("inputs", schemas.PUBLIC_VIEW, inputs), ("labels", schemas.LABEL, labels)):
            relative = f"{kind}.{suffix}.jsonl"
            if relative not in artifacts:
                raise InvalidInput(f"dataset artifact missing: {relative}")
            for line in artifacts[relative].splitlines():
                if not line:
                    raise InvalidInput("empty JSONL record")
                record = decode_json(line)
                schemas.validate(schema, record, relative)
                if record.get("task", record.get("kind")) != kind:
                    raise InvalidInput("dataset task/file mismatch")
                destination.append(record)
    return manifest, inputs, labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Craft or replay an immutable offline Operations dataset.")
    parser.add_argument("--mode", default="operations")
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--replay", type=Path, metavar="DATASET")
    source.add_argument("--compare", type=Path, metavar="DATASET")
    parser.add_argument("--predictor", choices=tuple(PREDICTORS), default="reference")
    parser.add_argument("--ablation", choices=ABLATIONS, default="none")
    args = parser.parse_args(argv)
    try:
        mode = select_mode(args.mode, MODES)
        if args.replay is not None or args.compare is not None:
            if args.resources is not None or args.source_root is not None:
                raise InvalidInput("replay reads a pinned dataset, not raw resources or source reports")
            original, inputs, labels = load_dataset(args.replay or args.compare)
            if original["mode"] != {"id": mode.id, "version": mode.version}:
                raise InvalidInput("dataset mode/version mismatch")
            if args.compare:
                runs = compare(inputs, labels, baseline=power_only, reference=reference)
            else:
                runs = {args.predictor: evaluate(inputs, labels, PREDICTORS[args.predictor], ablation=args.ablation)}
            artifacts = comparison_artifacts(runs)
            artifacts["REVIEW.md"] = ("# Offline Replay Review\n\nVisibility: evaluator_only.\n\n" + replay_review(runs)).encode()
            manifest = write_artifacts(args.output, artifacts, {"mode": original["mode"], "synthetic": True,
                "resource_pack_id": original["resource_pack_id"], "resource_manifest_sha256": original["resource_manifest_sha256"],
                "dataset_manifest_sha256": digest(json_bytes(original))})
        else:
            if args.resources is None or args.source_root is None:
                raise InvalidInput("craft requires --resources PACK and --source-root TESTBED")
            manifest = craft_dataset(mode_id=args.mode, registry=MODES, resources=args.resources, source_root=args.source_root, output=args.output)
        print(json.dumps({"status": "complete", "output": str(args.output), "artifacts": len(manifest["artifacts"]), "manifest_sha256": digest(json_bytes(manifest))}, sort_keys=True))
        return 0
    except (InvalidInput, OSError, UnicodeError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())