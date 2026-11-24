"""保存扫描历史和供后续阶段使用的文件位置。"""

import sqlite3

from autoloop.schemas.incident import ScanIssue, ScanRun


class ScanRepository:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def save(self, run: ScanRun) -> None:
        self.db.execute(
            """INSERT INTO scan_runs VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload""",
            (run.id, run.project_id, run.project_path, run.started_at.isoformat(timespec="microseconds"),
             run.status, run.model_dump_json()),
        )

    def history(self, limit: int, offset: int) -> list[ScanRun]:
        rows = self.db.execute(
            "SELECT payload FROM scan_runs ORDER BY started_at DESC, id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [ScanRun.model_validate_json(row[0]) for row in rows]

    def save_issue(self, scan_id: str, issue: ScanIssue) -> None:
        self.db.execute(
            """INSERT INTO scan_issues (scan_id, source_file, source_line, source_offset, reason)
            VALUES (?, ?, ?, ?, ?)""",
            (scan_id, issue.source_file, issue.source_line, issue.source_offset, issue.reason),
        )

    def issues(self, scan_id: str, limit: int, offset: int) -> list[ScanIssue]:
        if not self.db.execute("SELECT 1 FROM scan_runs WHERE id = ?", (scan_id,)).fetchone():
            raise ValueError(f"找不到扫描记录：{scan_id}")
        rows = self.db.execute(
            """SELECT source_file, source_line, source_offset, reason FROM scan_issues
            WHERE scan_id = ? ORDER BY id LIMIT ? OFFSET ?""", (scan_id, limit, offset),
        )
        return [ScanIssue.model_validate(dict(row)) for row in rows]

    def save_offset(self, project_id: str, source: str, identity: str, offset: int) -> None:
        self.db.execute(
            """INSERT INTO file_offsets VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, source_file) DO UPDATE SET
            file_identity=excluded.file_identity, end_offset=excluded.end_offset""",
            (project_id, source, identity, offset),
        )

    def invalidate_offset(self, project_id: str, source: str) -> None:
        self.db.execute(
            "DELETE FROM file_offsets WHERE project_id = ? AND source_file = ?",
            (project_id, source),
        )
