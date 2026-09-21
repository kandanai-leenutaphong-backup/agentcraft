"""Loopback signed browser fixture with production lifespan and real public records."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import sys


async def serve(state, dist, public_key):
    import pytest
    import uvicorn
    from public_runtime import public_runtime

    with pytest.MonkeyPatch.context() as monkeypatch:
        original_connect = socket.socket.connect

        def loopback_only(connection, address):
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
                raise AssertionError("external socket refused by offline test")
            return original_connect(connection, address)

        monkeypatch.setattr(socket.socket, "connect", loopback_only)
        with public_runtime(monkeypatch, state, public_key, dist) as fixture:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            listener.setblocking(False)

            class Server(uvicorn.Server):
                async def startup(self, sockets=None):
                    await super().startup(sockets)
                    if not self.started:
                        raise RuntimeError("production lifespan failed before readiness")
                    print(json.dumps({"kind": "ready", "origin": f"http://127.0.0.1:{listener.getsockname()[1]}"}), flush=True)

            server = Server(uvicorn.Config(fixture.app, log_level="warning", lifespan="on", ws="none", timeout_graceful_shutdown=5))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                command = await asyncio.to_thread(sys.stdin.readline)
                assert json.loads(command)["command"] == "stop"
            finally:
                server.should_exit = True
                await task
                listener.close()
                request_path = state.parent / "native-model-requests.json"
                with request_path.open("x") as handle:
                    json.dump(fixture.model_requests, handle, indent=2)
                print(json.dumps({"kind": "closed", "production_lifespan": True,
                    "cosmos_queries": len(fixture.telemetry.requests), "graph_queries": len(fixture.graph.requests),
                    "search_requests": fixture.search_requests, "external_model_calls": 0,
                    "scripted_model_requests": len(fixture.model_requests), "native_request_evidence": str(request_path),
                    "transport": "synthetic stores; actual licensed package", "settled": True}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--frontend-dist", type=Path, required=True)
    args = parser.parse_args()
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    for name in ("AUTH_TENANT_ID", "AUTH_CLIENT_ID", "AUTH_PUBLIC_ORIGIN", "AUTH_SESSION_TABLE_ENDPOINT", "DEV_PUBLIC_KEY_ED25519", "DEV_REPLAY_LEDGER"):
        os.environ[name] = ""
    sys.path.insert(0, str(Path(__file__).parent))
    initial = json.loads(sys.stdin.readline())
    assert set(initial) == {"public_key"}
    asyncio.run(serve(args.state_dir, args.frontend_dist, initial["public_key"]))


if __name__ == "__main__":
    main()