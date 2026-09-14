#!/usr/bin/env python3
"""The integration seam, worked: a protected API with ownership rules.

Runs with no Entra tenant. Without `AUTH_ENABLED=true` it starts in development
mode, where each caller declares an identity with `X-User-Id` — which is enough
to exercise the ownership rules properly, because two callers really are two
identities. Set the environment variables and the same code validates real
tokens; no route changes.

    python3 examples/api.py                  # self-driving demo, no server
    python3 examples/api.py --serve          # http://127.0.0.1:8080

Try it:

    curl -H 'X-User-Id: alice' localhost:8080/api/records
    curl -H 'X-User-Id: bob'   localhost:8080/api/records/alice-1     # 404
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entraauth as ea

# Stand-in for a datastore. The owner id is the principal id — never the email,
# which changes when a person's name does.
RECORDS: dict[str, dict] = {
    "alice-1": {"owner_id": "alice", "title": "Alice's first record"},
    "alice-2": {"owner_id": "alice", "title": "Alice's second record"},
    "bob-1": {"owner_id": "bob", "title": "Bob's record"},
    "sample": {"owner_id": ea.DEFAULT_SHARED_OWNER, "title": "Shared sample"},
    "orphan": {"owner_id": "", "title": "Predates the ownership column"},
}


def build_app():
    """Compose the application. The only place auth is wired.

    The framework is imported here rather than at module scope for the same
    reason the box does it: FastAPI is this example's dependency, not the
    capability's.
    """
    from fastapi import Depends, FastAPI

    config = ea.AuthConfig.from_env()

    app = FastAPI(title="entra-api-auth example")
    validator = ea.install_auth(app, config)
    current = ea.principal_dependency(validator)
    policy = ea.OwnershipPolicy()

    @app.get("/api/me")
    async def me(principal: ea.Principal = Depends(current)) -> dict:
        """Who the caller is, as the API sees them."""
        return {
            "id": principal.id,
            "name": principal.name,
            "kind": principal.kind,
            "tenant_id": principal.tenant_id,
            # Worth surfacing: a developer identity proves nothing, and an
            # operator looking at this endpoint should be able to tell.
            "proven": not principal.is_developer,
        }

    @app.get("/api/records")
    async def list_records(principal: ea.Principal = Depends(current)) -> dict:
        """Only what the caller may see — filtered, not merely checked.

        Listing is where ownership is most often forgotten: a per-item check on
        the detail route feels like enough, right up until the list route hands
        over every title in the database.
        """
        visible = {
            record_id: record for record_id, record in RECORDS.items()
            if policy.can_read(record["owner_id"], principal)
        }
        return {"records": visible, "count": len(visible)}

    @app.get("/api/records/{record_id}")
    async def get_record(record_id: str,
                         principal: ea.Principal = Depends(current)) -> dict:
        """One record. 404 whether it is absent or simply not theirs."""
        record = RECORDS.get(record_id)
        if record is None:
            raise ea.NotFoundError(resource_id=record_id)
        policy.assert_readable(record["owner_id"], principal, record_id)
        return record

    @app.delete("/api/records/{record_id}")
    async def delete_record(record_id: str,
                            principal: ea.Principal = Depends(current)) -> dict:
        """Mutation. Shared templates refuse with 403; strangers get 404."""
        record = RECORDS.get(record_id)
        if record is None:
            raise ea.NotFoundError(resource_id=record_id)
        policy.assert_writable(record["owner_id"], principal, "delete", record_id)
        return {"deleted": record_id}

    return app


def demo() -> int:
    """Drive the API in-process and print what each caller sees."""
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app, raise_server_exceptions=False)
    enabled = app.state.auth_config.enabled

    print(f"auth enabled: {enabled}")
    if enabled:
        print("Real tokens required — this demo drives unauthenticated calls, "
              "so every request below will be a 401. That is the point.\n")
    else:
        print("Development mode: X-User-Id declares the caller.\n")

    def call(method: str, path: str, who: str) -> None:
        response = client.request(method, path, headers={"X-User-Id": who})
        body = response.json()
        summary = (
            body.get("count") if "count" in body
            else body.get("title") or body.get("message") or body.get("id") or body
        )
        print(f"  {who:<6} {method:<6} {path:<26} -> {response.status_code} {summary}")

    print("identity")
    call("GET", "/api/me", "alice")

    print("\nlisting is filtered, not just checked")
    call("GET", "/api/records", "alice")
    call("GET", "/api/records", "bob")

    print("\nreading someone else's record is indistinguishable from absence")
    call("GET", "/api/records/alice-1", "alice")
    call("GET", "/api/records/alice-1", "bob")
    call("GET", "/api/records/does-not-exist", "bob")

    print("\nshared templates: readable by all, writable by none")
    call("GET", "/api/records/sample", "bob")
    call("DELETE", "/api/records/sample", "bob")

    print("\nunowned records are not public by default")
    call("GET", "/api/records/orphan", "alice")

    print("\nmutation follows the same rule as reading")
    call("DELETE", "/api/records/alice-1", "bob")
    call("DELETE", "/api/records/alice-1", "alice")

    print("\nsign-in configuration is public by necessity")
    print(f"  {'-':<6} {'GET':<6} {'/api/auth_setup':<26} -> "
          f"{client.get('/api/auth_setup').json()}")
    return 0


def main() -> int:
    # The box logs every denial. Surfacing it here is the point: an operator can
    # see what the caller was not told.
    import logging
    logging.basicConfig(level=logging.WARNING, format="  log: %(message)s")
    if "--serve" in sys.argv:
        import uvicorn
        uvicorn.run(build_app(), host="127.0.0.1", port=8080)
        return 0
    return demo()


if __name__ == "__main__":
    raise SystemExit(main())
