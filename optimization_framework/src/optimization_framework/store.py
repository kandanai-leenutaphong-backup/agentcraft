"""Single-host owner-scoped SQLite index over immutable, verified JSON artifacts."""

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading

from .contracts import Refusal, SCHEMA_VERSION, canonical, digest, text


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().absolute()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise Refusal("unsafe_storage_root")
        os.chmod(self.root, 0o700)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(mode=0o700, exist_ok=True)
        if self.artifacts.is_symlink():
            raise Refusal("unsafe_artifact_directory")
        os.chmod(self.artifacts, 0o700)
        database = self.root / "index.sqlite3"
        descriptor = os.open(database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        os.chmod(database, 0o600)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise Refusal("unsupported_store_version", 409)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, digest TEXT NOT NULL,
                revision INTEGER NOT NULL, admission_key TEXT NOT NULL,
                request_digest TEXT NOT NULL, UNIQUE(owner, admission_key));
            CREATE TABLE IF NOT EXISTS revisions (
                run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL,
                digest TEXT NOT NULL, PRIMARY KEY(run_id, revision));
            CREATE TRIGGER IF NOT EXISTS immutable_revision_update
                BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT, 'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_revision_delete
                BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT, 'immutable'); END;
            PRAGMA user_version=1;
        """)

    def put(self, value: object) -> str:
        payload = canonical(value)
        identity = digest(payload)
        destination = self.artifacts / identity
        with self.lock:
            if destination.exists():
                if self.read_artifact(identity) != value:
                    raise Refusal("artifact_conflict", 409)
                return identity
            descriptor, pending = tempfile.mkstemp(prefix=".pending-", dir=self.artifacts)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(pending, destination, follow_symlinks=False)
            except FileExistsError:
                if self.read_artifact(identity) != value:
                    raise Refusal("artifact_conflict", 409)
            directory = os.open(self.artifacts, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
                self.read_artifact(identity)
                os.unlink(pending)
                os.fsync(directory)
            finally:
                os.close(directory)
        return identity

    def read_artifact(self, identity: str) -> object:
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise Refusal("invalid_artifact_id")
        try:
            descriptor = os.open(self.artifacts / identity, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                payload = stream.read()
            if digest(payload) != identity:
                raise Refusal("artifact_integrity_failure", 409)
            return json.loads(payload)
        except (OSError, ValueError) as error:
            raise Refusal("artifact_unavailable", 409) from error

    def _row(self, owner: str, run_id: str):
        row = self.db.execute("SELECT owner,digest,revision FROM runs WHERE id=?",
                              (run_id,)).fetchone()
        if row is None or row[0] != owner:
            raise Refusal("run_not_found", 404)
        return row

    def get(self, owner: str, run_id: str) -> dict:
        with self.lock:
            row = self._row(owner, run_id)
            return self.read_artifact(row[1])

    def list(self, owner: str) -> list[dict]:
        with self.lock:
            return [self.get(owner, row[0]) for row in self.db.execute(
                "SELECT id FROM runs WHERE owner=? ORDER BY rowid DESC", (owner,)).fetchall()]

    def create(self, owner: str, record: dict, key: str, request: dict) -> tuple[dict, bool]:
        text(owner, "owner", 128)
        text(key, "idempotency_key", 128)
        fingerprint = digest(canonical(request))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                prior = self.db.execute(
                    "SELECT id,request_digest FROM runs WHERE owner=? AND admission_key=?",
                    (owner, key)).fetchone()
                if prior:
                    if prior[1] != fingerprint:
                        raise Refusal("idempotency_conflict", 409)
                    result = self.get(owner, prior[0])
                    self.db.execute("COMMIT")
                    return result, False
                identity = self.put(record)
                self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
                                (record["id"], owner, identity, 1, key, fingerprint))
                self.db.execute("INSERT INTO revisions VALUES (?,?,?)",
                                (record["id"], 1, identity))
                self.db.execute("COMMIT")
                return self.get(owner, record["id"]), True
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def update(self, owner: str, run_id: str, change) -> dict:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(owner, run_id)
                before = self.read_artifact(row[1])
                after = json.loads(canonical(before))
                change(after)
                for field in ("id", "task_id", "baseline_candidate_id", "frozen"):
                    if field in before and after.get(field) != before[field]:
                        raise Refusal("immutable_run_field", 409)
                for field in ("candidates", "events", "restorations", "attempts"):
                    previous = before.get(field, [])
                    if after.get(field, [])[:len(previous)] != previous:
                        raise Refusal("immutable_evidence", 409)
                identity = self.put(after)
                if identity != row[1]:
                    revision = row[2] + 1
                    self.db.execute("INSERT INTO revisions VALUES (?,?,?)",
                                    (run_id, revision, identity))
                    self.db.execute("UPDATE runs SET digest=?,revision=? WHERE id=?",
                                    (identity, revision, run_id))
                self.db.execute("COMMIT")
                return self.get(owner, run_id)
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.db.close()