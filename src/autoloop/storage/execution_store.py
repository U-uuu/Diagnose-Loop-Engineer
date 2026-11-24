"""初始化 SQLite 数据库并管理连接。"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED')),
    severity TEXT NOT NULL CHECK (severity IN ('ERROR','CRITICAL')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS incident_list ON incidents (last_seen DESC, id);
CREATE TABLE IF NOT EXISTS error_occurrences (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    source_offset INTEGER NOT NULL,
    raw_log TEXT NOT NULL,
    stacktrace TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS occurrence_list ON error_occurrences (incident_id, timestamp DESC, id);
CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED','PARTIAL')),
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scan_history ON scan_runs (started_at DESC, id);
CREATE TABLE IF NOT EXISTS scan_issues (
    id INTEGER PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES scan_runs(id),
    source_file TEXT NOT NULL,
    source_line INTEGER,
    source_offset INTEGER,
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scan_issue_list ON scan_issues (scan_id, id);
CREATE TABLE IF NOT EXISTS file_offsets (
    project_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    file_identity TEXT NOT NULL,
    end_offset INTEGER NOT NULL CHECK (end_offset >= 0),
    PRIMARY KEY (project_id, source_file)
);
"""


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        yield connection
    finally:
        connection.close()
