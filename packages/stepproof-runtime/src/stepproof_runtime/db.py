"""SQLite schema and connection management."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runbook_templates (
    template_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    risk_level TEXT NOT NULL,
    allowed_environments TEXT NOT NULL,   -- JSON array
    requires_human_signoff INTEGER NOT NULL DEFAULT 0,
    shadow INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'template',  -- 'template' | 'declared'
    steps TEXT NOT NULL,                   -- JSON array of StepTemplate
    source_path TEXT,                        -- File path if loaded from YAML
    intent TEXT                               -- Declared-plan intent (NULL for templates)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    template_version TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    current_step TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY (template_id) REFERENCES runbook_templates(template_id)
);

CREATE TABLE IF NOT EXISTS step_runs (
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '{}',   -- JSON
    verification_result TEXT,               -- JSON or NULL
    attempts INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    PRIMARY KEY (run_id, step_id),
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
);

CREATE TABLE IF NOT EXISTS liveness_heartbeats (
    run_id TEXT PRIMARY KEY,
    ttl_seconds INTEGER NOT NULL,
    registered_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    human_owner_id TEXT NOT NULL,
    run_id TEXT,
    step_id TEXT,
    action_type TEXT NOT NULL,
    tool TEXT,
    decision TEXT,
    policy_id TEXT,
    reason TEXT,
    compliance_tags TEXT NOT NULL DEFAULT '[]',  -- JSON array
    payload_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log(run_id);
"""


def db_path() -> str:
    """Resolve the SQLite database path, creating its parent dir if needed."""
    raw = os.getenv("STEPPROOF_DB_PATH", ".stepproof/runtime.db")
    p = Path(raw).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


async def init_db(path: str | None = None) -> None:
    """Create tables idempotently and apply small in-place migrations."""
    path = path or db_path()
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(SCHEMA_SQL)
        # Idempotent column migrations for pre-existing databases.
        for stmt in (
            "ALTER TABLE runbook_templates ADD COLUMN source TEXT NOT NULL DEFAULT 'template'",
            "ALTER TABLE runbook_templates ADD COLUMN intent TEXT",
        ):
            try:
                await conn.execute(stmt)
            except Exception:
                pass  # Column already exists; ALTER is idempotent-by-try.
        await conn.commit()


@asynccontextmanager
async def connect(path: str | None = None):
    """Yield a configured aiosqlite connection."""
    path = path or db_path()
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        await conn.close()
