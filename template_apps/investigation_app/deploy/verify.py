"""Read back the local template; --scan additionally queries the existing ADX replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:9011")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification/api.json"))
    arguments = parser.parse_args()
    origin = urlsplit(arguments.api)
    if (origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost"}
            or origin.username or origin.password or origin.path not in {"", "/"}
            or origin.query or origin.fragment):
        parser.error("verification requires a plain loopback HTTP origin")
    checks = []

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})

    with httpx.Client(base_url=arguments.api.rstrip("/"), timeout=90, trust_env=False) as client:
        response = client.get("/healthz")
        check("liveness", response.status_code == 200 and response.json() == {"status": "ok"})
        response = client.get("/api/whoami")
        check("local_identity", response.status_code == 200 and response.json().get("issuer") == "local-preview")
        for name, headers in (("foreign_origin", {"Origin": "https://untrusted.example"}),
                              ("foreign_host", {"Host": "untrusted.example"})):
            response = client.get("/api/whoami", headers=headers)
            check(name, response.status_code == 401 and not response.content)
        response = client.get("/api/cyber/detector/configuration")
        body = response.json()
        check("detector_readback", response.status_code == 200 and body.get("historical_replay") is True
              and len(body.get("configuration_digest", "")) == 64)
        response = client.get("/api/cyber/optimization")
        check("optimizer_removed", response.status_code == 404)
        response = client.get("/api/cyber/inventory/tree")
        check("guide_not_composed", response.status_code == 200 and not any(
            node.get("useCaseId") == "guide" for node in response.json().get("children", [])))
        window = {"start": "2026-08-13T02:30:00Z", "end": "2026-08-13T03:40:59Z"}
        response = client.post("/api/cyber/scan", json={**window, "end": window["start"]})
        check("invalid_window_refused", response.status_code == 400)
        if arguments.scan:
            response = client.post("/api/cyber/scan", json=window)
            body = response.json()
            check("live_adx_scan", response.status_code == 200, status_code=response.status_code,
                  summary=body.get("summary"))
            situations = body.get("situations", [])
            if response.status_code == 200:
                check("replay_situations_present", bool(situations), count=len(situations))
            if situations:
                response = client.get(f"/api/cyber/evidence/{situations[0]['situation_id']}", params=window)
                evidence = response.json()
                check("evidence_readback", response.status_code == 200 and evidence.get("row_count", 0) > 0,
                      status_code=response.status_code, row_count=evidence.get("row_count"))
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "api": arguments.api,
              "live_adx_requested": arguments.scan, "model_calls": False,
              "checks": checks, "passed": all(item["passed"] for item in checks)}
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())