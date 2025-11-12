"""Simple job persistence layer backed by SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

DB_PATH = os.path.join(os.path.dirname(__file__), "hashstore.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_job_store() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT,
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _utc_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def create_job(job_type: str, payload: Optional[Dict[str, Any]] = None) -> str:
    job_id = uuid4().hex
    now = _utc_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jobs (id, type, status, payload, result, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_type,
                "queued",
                json.dumps(payload or {}),
                None,
                None,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def update_job(
    job_id: str,
    status: str,
    *,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, result = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(result) if result is not None else None,
                error,
                _utc_iso(),
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    result = dict(row)
    if result.get("payload"):
        result["payload"] = json.loads(result["payload"])
    if result.get("result"):
        result["result"] = json.loads(result["result"])
    return result

