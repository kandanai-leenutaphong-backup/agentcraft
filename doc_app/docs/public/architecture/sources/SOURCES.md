# Preserved architecture sources

These two files are supplied originals, copied byte-for-byte. They are not site pages: they
are standalone, light-themed writeups kept as the record the site-native pages were adapted
from.

**Preservation rule.** Do not edit, reformat, re-theme, or minify these files, and do not let
the build touch them. `scripts/postbuild.mjs` excludes this directory from identity-script
injection so the copies stay identical to their origins. Verify with `sha256sum` after any
build. Replacing a file means recording a new origin path, retrieval date, and hash here.

| File | Origin path | Retrieved | SHA-256 |
| --- | --- | --- | --- |
| `gridiq-modular-change-atlas.html` | `/home/hanchoong/CURRENT270425/gridiq_latest_main_020726/docs/architecture/gridiq-modular-change-atlas.html` | 2026-08-24 | `340ebdc452ff06758de88446da1f2dcdc6354004b59491c415a677ed988e27e9` |
| `gridiq-specialized-tools.html` | `/home/hanchoong/CURRENT270425/gridiq_latest_main_020726/docs/architecture/gridiq-specialized-tools.html` | 2026-08-24 | `08cf55ae1de0ff5ca95027fe86fc3ee019ac36c6d0f526514d66b67ea3cd8418` |

Served at `/architecture/sources/<file>` behind the site's existing ingress gate; they carry no
injected identity script of their own.

Adapted into [`/modular-change`](../../../pages/modular-change.mdx) and
[`/specialized-tools`](../../../pages/specialized-tools.mdx).
