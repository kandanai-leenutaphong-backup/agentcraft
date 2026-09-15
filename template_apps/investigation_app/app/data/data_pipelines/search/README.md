# Publishing the knowledge index

One pipeline, one index, one source: pinned MITRE ATT&CK. It holds knowledge, not telemetry.

## What it reads

| Input | Path | What it contributes |
| --- | --- | --- |
| Normalised classification corpus | `cyber_kb/normalized/classification.jsonl` | ATT&CK techniques and tactics, as candidate situation types |
| Normalised detection corpus | `cyber_kb/normalized/corpus.jsonl` | ATT&CK analytics and detection strategies, as advisory material |

Both files hold several mirrors. Only records whose `source` is `attack` are published;
Sigma, Atomic, Sentinel, GuardSight and VERIS records are skipped, so nothing that is not
ATT&CK is served under the ATT&CK name. A record the upstream bundle has revoked or
deprecated is skipped too.

## What it writes

| Index | Documents | Key | Searched |
| --- | --- | --- | --- |
| `mitre-attack-<stamp>` | 3,908 (712 situation types, 3,196 analytics) | `safe_key("<doc_kind>:<doc_id>")` | `content`, plus title, definition, summary, body, symptoms, keywords, log sources |

The key is qualified by `doc_kind` because both corpora mint ids in the same `attack:<hex>`
namespace: unqualified, an analytic silently overwrites a situation type, and 697 of 712
techniques disappear without an error.

`<stamp>` is the pinned build's own retrieval stamp, from `classification_build.json` — so
the same inputs publish the same index name, and the name identifies one bundle rather
than whenever it was read. At the pinned commit
`6cda5ad8462c79e14fbb872f4e09059b18e0cfc4` that is `mitre-attack-20260829t163257z`,
displayed as `MITRE ATT&CK @ 2026-08-29T16:32:57Z`.

Every document carries `path`, `commit`, `license` and `retrieved_at`, so a hit pasted
elsewhere still says which bundle it came from and under whose terms.

## Running it

```bash
./deploy/deploy.sh search-load   -e prod          # publish, then verify
./deploy/deploy.sh search-verify -e prod          # read the index back, prove the refusal
./deploy/deploy.sh search-retire -e prod <index>  # delete exactly the named indexes
```

Directly, if you are not going through the operator entry point:

```bash
python3 -m app.data.data_pipelines.search.run publish \
  --endpoint https://<service>.search.windows.net
python3 -m app.data.data_pipelines.search.run retire \
  --endpoint https://<service>.search.windows.net --index <name>
```

`retire` names every index on the command line. There is no wildcard and no `--all`, and
`deploy.sh search-retire` additionally refuses the index the deployment is configured to
read. Each deletion is read back: the verb fails if a named index is still present.

## What it is not allowed to touch

One search service, and only the index it is told to write. It reads the normalised corpora
on disk and writes nowhere else: no ADX, no Gremlin, no canonical dataset, no telemetry.

Telemetry was published into `perth-events` and `ait-events` by an earlier version of this
pipeline. That was a mistake — a keyword copy of rows ADX already serves, filed as if it
were retrieval. Both indexes have been deleted and `deploy/verify_search.py` asserts they
stay gone.

## Authentication

The caller authenticates as itself with `DefaultAzureCredential`. The service has local
authentication disabled, so there is no admin or query key in this repository, this
process, or the image.
