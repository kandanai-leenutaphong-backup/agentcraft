"""Real hosting SDK smoke without network or inference."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starlette.testclient import TestClient
from main import create_server, loaded_spec


def check():
    os.environ["FOUNDRY_AGENT_NAME"] = "agentcraft-iris-optimization"
    os.environ["FOUNDRY_AGENT_VERSION"] = "smoke"
    spec, config = loaded_spec(None)
    manifest = {"sha256": "smoke", "files": {"app/configuration.yaml": "smoke"}}
    server = create_server("https://smoke.invalid/api/projects/smoke", manifest, spec, config,
                           configure_observability=None)
    with TestClient(server, raise_server_exceptions=False) as client:
        assert client.get("/readiness").status_code == 200
        response = client.post("/responses", json={"input": "", "stream": False, "store": False})
        assert response.status_code >= 400 or response.json().get("status") == "failed"
    return {"readiness": True, "invalid_input_refused": True, "model": spec.model, "config_source": config.source}


if __name__ == "__main__":
    print(json.dumps(check()))