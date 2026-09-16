# Signing Migration Findings

Historical source: the retired signed-dev-access skill's GOTCHAS, wire contract,
browser pilot and tests. [Retirement hashes](signed-dev-access-retirement.json)
identify the exact bytes and external recovery. These are retained findings,
not newly reproduced production or browser measurements. The
[current contract](signed-dev-access.md) takes precedence.

| Source finding | Target interpretation |
| --- | --- |
| G1 Raw and decoded paths differ | Sign canonical raw path/query and exact body; caller/ingress must preserve them. |
| G2 Managed ingress can decode path bytes | Prefer query/body for risky values, or prove exact deployed byte preservation; local success is not ingress evidence. |
| G3 Optional context header can be stripped | Prove header preservation. An explicitly chosen empty slug may use the host's default agent identity; never weaken primary auth. |
| G4 Unbounded slug becomes downstream crash | Canonical verifier and signer normalize/bound the slug before identity mapping. |
| G5 Signature is replayable without a nonce store | Corrected: key the ledger by decoded signature digest, retaining through timestamp plus skew, not a fixed TTL from first sight. |
| G6 Process cache does not cover replicas/restarts | Mandatory caller-supplied ledger; unavailable/full denies. Shared-storage deployment remains a host decision. |
| G7 HTTP middleware can buffer/break streams | Keep the existing pure-ASGI middleware and original transport disconnect behavior. Browser CDP never buffers responses. |
| G8 CORS/mount order changes preflight | Prove the actual middleware stack; unsigned primary-auth/preflight paths are not silently authorized. |
| G9 Missing public key disables the signed path | Corrected: configure the public verifier explicitly. Retire automatic private-key discovery/derivation and unapproved enabling. |
| G10 Silent 401s need a known-good canary | Use a separately authorized bounded signed request and compare environments; never add verifier failure logs. |
| G11 Installer and direct constructor differ | Empty key makes the installer decline; canonical direct construction rejects empty key/missing ledger. |
| G12 Identical timestamps cause honest-request replay | Use microseconds plus locked monotonic issuance within the fixed skew budget; true repeated bytes still refuse. |

## Browser Evidence Retained

The old browser pilot records measurements on Playwright 1.62 / Chromium 151:
`route.continue_` missed later redirect legs and forwarded signing material;
`route.fetch(max_redirects=0)` closed that leak but buffered streaming output.
That source recorded first event at 1,515 ms for fetch/fulfill versus 35 ms for
CDP, with the CDP stream ending at 1,521 ms. These measurements were not rerun.

Its binary experiment observed lossy text for bytes 0x00-0xFF, while CDP
`postDataEntries[].bytes` preserved binary and a 256 KiB body. Target code retains
that byte-only boundary, now with strict decoding and explicit size/chunk bounds.
Unknown streamed/file-backed bodies abort instead of producing a guessed signature.

One CDP session per page is required. A context page event can yield before a new
page is attached, so the target retains synchronous caller-created-page attachment.
Popup first navigation, out-of-process frames, service-worker caches and competing
route handlers remain explicit limitations. Service workers are blocked in fresh
piloted contexts; no recording or inherited human-session convenience is retained.

Historical source is not copied as runtime under docs. The canonical client calls
the existing canonical-string function and the canonical browser adapter calls
that client. Server verification/replay has one unchanged owner.