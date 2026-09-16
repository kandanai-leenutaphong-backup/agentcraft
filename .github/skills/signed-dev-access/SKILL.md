---
name: signed-dev-access
description: "Use when piloting deployed apps through browser and API with Ed25519 request signing, or diagnosing signed-request 401s. Agent identity, auth intact. Never disable auth or add bypass headers."
license: MIT
---

# Signed Dev Access

Use installed `signed-dev-access`; import `signed_dev_access`. Read the
[canonical client/server guide](../../../libraries/signed-dev-access/docs/skills/signed-dev-access.md)
for signing APIs, the metadata-only module CLI, Chromium piloting, private-key
checks, auth/replay boundaries, errors, limits and cleanup. `devauth` and skill-local
scripts are retired. Loading this entry creates no key, enables no caller, and
grants no application, model or cloud action; primary auth must stay intact.
