# Resource Explorer Gotchas

## G1 - A sibling editable install does not travel

**Symptom.** A copied backend raises `ModuleNotFoundError: azdata` during test collection.
**Cause.** The input setup installed another component by a sibling filesystem path.
**Fix.** This skill bundles the source dependency and declares it in its local lock. Backend
tests and runtime entry points resolve only paths inside this directory.

## G2 - HTTP readiness needs the built browser assets

**Symptom.** The backend process runs, but readiness reports a static-asset failure.
**Cause.** The browser source is not a browser bundle. The original static tests cover this state.
**Fix.** Run the frontend build before serving the browser. MCP tree/content/search needs no browser build.

## G3 - Base64 node IDs are not authorization tokens

**Symptom.** A caller can construct a well-formed ID for another subscription or group.
**Cause.** The codec validates structure, not the operator's authorization policy.
**Fix.** The MCP adapter checks decoded coordinates against its configured scope before reading.
Its SDK test proves cross-subscription and cross-group refusals.

## G4 - A forbidden branch is not an empty branch

**Symptom.** A missing role or private network looks like a resource containing nothing.
**Cause.** Flattening the wire's degradation states loses the diagnosis.
**Fix.** Preserve `status`, `error`, `fixtures` and `truncated`. The native selftest walks all fixture states.

## G5 - Search order is not resource type

**Symptom.** A search-to-content test cannot find a properties leaf under its first hit.
**Cause.** The first match can be a resource group; fixture renaming exposed that assumption.
**Fix.** Select a hit by `kind` before asking for resource-specific children. Search IDs still round trip.

## G6 - The UI's forwarded principal is not independent identity verification

**Symptom.** A directly exposed backend accepts a caller-supplied principal header.
**Cause.** The inherited guard assumes an authenticated edge that strips and sets those headers.
**Fix.** Retain that edge for real HTTP use. Fixture browser tests simulate its input and separately
test anonymous refusal; they do not prove a deployed Entra integration. MCP does not expose this HTTP app.

## G7 - Truncation is part of a successful result

**Symptom.** A large index or content sample shows only part of the available data.
**Cause.** The source contract caps children, bytes and rows; it does not implement pagination.
**Fix.** Surface `truncated` and the size fields. Do not treat a bounded result as a complete inventory.

Dependency-specific failures remain in [vendor/azdata/GOTCHAS.md](vendor/azdata/GOTCHAS.md).