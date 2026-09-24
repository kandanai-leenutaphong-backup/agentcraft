"""Read official public image manifests and verify content-addressed identities."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


def image(registry, repository, tag, token_url):
    with urllib.request.urlopen(token_url, timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(f"https://{registry}/v2/{repository}/manifests/{tag}", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
        digest = response.headers["Docker-Content-Digest"]
    if digest != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise ValueError("registry digest mismatch")
    manifests = json.loads(payload)["manifests"]
    platform = [entry for entry in manifests if entry.get("platform", {}).get("architecture") == "amd64"
                and entry.get("platform", {}).get("os") == "linux"]
    if len(platform) != 1:
        raise ValueError("ambiguous linux/amd64 image")
    return {"registry": registry, "repository": repository, "tag": tag, "index_digest": digest,
            "linux_amd64_digest": platform[0]["digest"], "manifest": json.loads(payload)}


if __name__ == "__main__":
    result = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
              "uv": image("ghcr.io", "astral-sh/uv", "0.9.30", "https://ghcr.io/token?scope=repository:astral-sh/uv:pull&service=ghcr.io"),
              "python": image("registry-1.docker.io", "library/python", "3.12.12-slim-bookworm",
                              "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull")}
    with (Path(__file__).parent / "images.json").open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({name: {key: value for key, value in result[name].items() if key != "manifest"} for name in ("uv", "python")}))