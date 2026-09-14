# Private SQLite Reader

This is the private optimization dependency, not another application-level query package.
Only the optimization worker should import this internal API.

One class. It answers a `SELECT` against one SQLite file and refuses everything else. Nothing
here reads the environment: the caller passes the path.

```python
from agent_optimization._local_query import SQLiteReader, LocalQueryError, QueryDenied, QueryTimeout

reader = SQLiteReader("var/dataset/cases.sqlite")
result = reader.query(
    "SELECT category, count(*) FROM evidence WHERE case_id = :case_id GROUP BY category",
    {"case_id": "0f3a1c…"},
    max_rows=50,
    timeout_seconds=2.0,
    tables={"evidence", "training_profile"},
)
# {"columns": [...], "rows": [[...], ...], "truncated": False, "elapsed_ms": 1.606}
```

## `SQLiteReader(path).query(...)`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `sql` | — | One statement. A second statement is refused before execution |
| `parameters` | `None` | Named bindings (`:name`). Values are bound, never interpolated |
| `max_rows` | `200` | `max_rows + 1` are fetched; `truncated` reports whether more existed |
| `timeout_seconds` | `5.0` | Wall-clock deadline, enforced from a progress handler |
| `tables` | `None` | Narrows the readable set. Defaults to `cases`, `evidence`, `training_profile` |

Returns `{"columns": list[str], "rows": list[list], "truncated": bool, "elapsed_ms": float}`.

Raises `QueryDenied` for a refusal, `QueryTimeout` for a deadline, `LocalQueryError` for anything
else (missing file, syntax error, missing table). The latter two derive from `LocalQueryError`.

## How the refusal is enforced

The check is SQLite's own authorizer callback, not string matching on the SQL. Three locks:

1. The connection is opened `file:…?mode=ro`, so the file cannot be written even if a write
   somehow authorized.
2. The authorizer permits only `SQLITE_SELECT`, `SQLITE_READ`, `SQLITE_FUNCTION` and
   `SQLITE_RECURSIVE`. Every other action is denied by exclusion — INSERT, UPDATE, DELETE,
   CREATE, DROP, ALTER, PRAGMA, ATTACH, DETACH, transactions, `load_extension`.
3. `SQLITE_READ` is checked against the allowed table set. `labels` is refused unconditionally,
   including through `tables={"labels"}`, and so is any `sqlite_`-prefixed catalogue table.

**The catalogue is read before the authorizer is installed.** A read of a real table and a read
of a CTE alias reach the authorizer with identical arguments, so the list of real table names is
what tells them apart. Without it, `SELECT count(*) FROM labels` slips through, because
`count(*)` reads no column and so produces no column-level read to inspect. That was a real hole
found under test, not a hypothetical one.

Functions are allow-listed by name (`ALLOWED_FUNCTIONS`); `randomblob`, `readfile`,
`load_extension` and anything else unlisted are refused.

## What it does not do

It is not a sandbox and not a query planner. It does not rewrite SQL, does not scope rows to a
caller, and does not decide which case a caller may see — a caller needing per-case scoping
passes a `case_id` binding and the calling layer decides which one. It does not open more than
one database, so a cross-database join is impossible by construction.

## Tests

[test_local_query.py](../tests/test_local_query.py) covers the positive path, bounds and
truncation, every write and DDL form, PRAGMA, ATTACH, `load_extension`, unlisted functions, the
label table directly and through a nested `SELECT`, a CTE and `count(*)`, the system catalogue,
`tables` narrowing and attempted widening, multiple statements, and the deadline.

```bash
python3 -m pytest "$SKILL_ROOT/python/agent_optimization/tests/test_local_query.py" -q
```
