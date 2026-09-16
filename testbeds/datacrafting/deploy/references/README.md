# Official Reference Provenance

[manifest.json](./manifest.json) records 22 acquired HTML/text artifacts from Microsoft Learn, including
source URL, retrieval time, HTTP status, byte count and SHA-256. Acquisition used the requested web-resource
skill with robots handling and rate limits, writing only this deployment-owned reference directory.

```bash
bash testbeds/datacrafting/deploy/deploy.sh research
```

This command now verifies the cached bytes and provenance offline. It does not refresh URLs or assert current
network liveness. The shared web-resource fetcher was removed by concurrent workspace work after acquisition;
[the exact missing-script refusal](../records/20260916T070144890239Z-refusal.json) is retained. No replacement
fetch implementation or write to shared cache was introduced. [sources.txt](./sources.txt) retains original URLs
for a future separately available public-page acquisition tool.

[python-bindings.md](./python-bindings.md) records the later editor-tool documentation read and runtime decision
with its source revision and explicit archive limitation. No notebook was written outside the allowed paths;
the expensive deployment findings are retained here and in the runbook instead.

Third-party source material remains its publisher's property, held for internal reference only. None of these
pages are runtime dependencies or instructions to the application. A failed early REST URL was corrected to
the documented Content Analyzers endpoint; no failed fetch was used as support for a success claim.