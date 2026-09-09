from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .errors import Code, FinalityError
from .models import PaymentFinalityAuthority, ProtectedValidationEvidence, iso_z


class SQLiteFinalityStore:
    """Durable evidence and consume state for one sink trust domain."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS evidence (
          evidence_id TEXT PRIMARY KEY,
          candidate_act_id TEXT NOT NULL,
          instruction_digest TEXT NOT NULL,
          payload TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS authorities (
          authority_id TEXT PRIMARY KEY,
          candidate_act_id TEXT NOT NULL,
          evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
          instruction_digest TEXT NOT NULL,
          nonce TEXT NOT NULL UNIQUE,
          sink_id TEXT NOT NULL,
          payload TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('UNUSED','CONSUMED_PENDING','POSTED','FAILED_DEFINITE')),
          settlement_ref TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_digest_live
          ON authorities(instruction_digest)
          WHERE state IN ('CONSUMED_PENDING','POSTED');
        """)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def commit_evidence(self, evidence: ProtectedValidationEvidence) -> None:
        with self._tx() as db:
            db.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?)",
                (evidence.evidence_id, evidence.candidate_act_id, evidence.instruction_digest,
                 json.dumps(evidence.to_dict(), sort_keys=True), iso_z(evidence.issued_at)),
            )

    def evidence_payload(self, evidence_id: str) -> dict | None:
        row = self._conn.execute("SELECT payload FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def register_authority(self, authority: PaymentFinalityAuthority) -> None:
        now = datetime.now(timezone.utc)
        with self._tx() as db:
            db.execute(
                "INSERT INTO authorities VALUES (?, ?, ?, ?, ?, ?, ?, 'UNUSED', NULL, ?)",
                (authority.authority_id, authority.candidate_act_id, authority.evidence_id,
                 authority.binding["instruction_digest"]["value"], authority.binding["nonce"],
                 authority.binding["finality_sink_id"], json.dumps(authority.to_dict(), sort_keys=True), iso_z(now)),
            )

    def reserve(self, authority_id: str, digest: str, sink_id: str) -> None:
        now = iso_z(datetime.now(timezone.utc))
        with self._tx() as db:
            row = db.execute("SELECT * FROM authorities WHERE authority_id=?", (authority_id,)).fetchone()
            if row is None:
                raise FinalityError(Code.NO_FINALITY_AUTHORITY, "authority is not registered")
            if row["state"] != "UNUSED":
                raise FinalityError(Code.AUTHORITY_ALREADY_USED, f"authority state is {row['state']}")
            if row["instruction_digest"] != digest:
                raise FinalityError(Code.INSTRUCTION_SUBSTITUTION, "registered digest mismatch")
            if row["sink_id"] != sink_id:
                raise FinalityError(Code.SINK_MISMATCH, "registered sink mismatch")
            try:
                changed = db.execute(
                    "UPDATE authorities SET state='CONSUMED_PENDING', updated_at=? WHERE authority_id=? AND state='UNUSED'",
                    (now, authority_id),
                ).rowcount
            except sqlite3.IntegrityError as exc:
                raise FinalityError(Code.REPLAY_DETECTED, "digest already consumed by another authority") from exc
            if changed != 1:
                raise FinalityError(Code.AUTHORITY_ALREADY_USED, "authority won concurrent consume race")

    def complete(self, authority_id: str, settlement_ref: str) -> None:
        with self._tx() as db:
            changed = db.execute(
                "UPDATE authorities SET state='POSTED', settlement_ref=?, updated_at=? "
                "WHERE authority_id=? AND state='CONSUMED_PENDING'",
                (settlement_ref, iso_z(datetime.now(timezone.utc)), authority_id),
            ).rowcount
            if changed != 1:
                raise FinalityError(Code.FAIL_CLOSED, "authority was not reserved")

    def fail_definite(self, authority_id: str) -> None:
        with self._tx() as db:
            db.execute(
                "UPDATE authorities SET state='FAILED_DEFINITE', updated_at=? "
                "WHERE authority_id=? AND state='CONSUMED_PENDING'",
                (iso_z(datetime.now(timezone.utc)), authority_id),
            )

    def state(self, authority_id: str) -> str | None:
        row = self._conn.execute("SELECT state FROM authorities WHERE authority_id=?", (authority_id,)).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self._conn.close()

