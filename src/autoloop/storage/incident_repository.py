"""提供故障和发生记录的 SQLite 读写操作。"""

from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

from autoloop.schemas.incident import Category, Incident, IncidentStatus, Occurrence, Severity


def _parameters(model: Incident | Occurrence) -> dict[str, object]:
    return {
        name: value.astimezone(UTC).isoformat(timespec="microseconds")
        if isinstance(value, datetime) else value
        for name, value in model.model_dump().items()
    }


class IncidentRepository:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def get(self, incident_id: str) -> Incident | None:
        row = self.db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return Incident.model_validate(dict(row)) if row else None

    def by_fingerprint(self, fingerprint: str) -> Incident | None:
        row = self.db.execute(
            "SELECT * FROM incidents WHERE fingerprint = ?", (fingerprint,),
        ).fetchone()
        return Incident.model_validate(dict(row)) if row else None

    def create(self, incident: Incident) -> None:
        self.db.execute(
            """INSERT INTO incidents VALUES (
                :id, :project_id, :title, :category, :error_type, :error_message, :fingerprint,
                :first_seen, :last_seen, :occurrence_count, :status, :severity, :created_at, :updated_at
            )""", _parameters(incident),
        )

    def update(self, incident: Incident) -> None:
        self.db.execute(
            """UPDATE incidents SET title=:title, error_message=:error_message,
            last_seen=:last_seen, occurrence_count=:occurrence_count, status=:status,
            severity=:severity, updated_at=:updated_at WHERE id=:id""", _parameters(incident),
        )

    def list(
        self, *, status: IncidentStatus | None = None, category: Category | None = None,
        severity: Severity | None = None, limit: int = 20, offset: int = 0,
    ) -> list[Incident]:
        rows = self.db.execute(
            """SELECT * FROM incidents WHERE (? IS NULL OR status = ?)
            AND (? IS NULL OR category = ?) AND (? IS NULL OR severity = ?)
            ORDER BY last_seen DESC, id LIMIT ? OFFSET ?""",
            (status, status, category, category, severity, severity, limit, offset),
        )
        return [Incident.model_validate(dict(row)) for row in rows]

    def has_event(self, event_id: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM error_occurrences WHERE event_id = ?", (event_id,),
        ).fetchone() is not None

    def add_occurrence(self, occurrence: Occurrence) -> None:
        self.db.execute(
            """INSERT INTO error_occurrences VALUES (
            :id, :incident_id, :event_id, :timestamp, :source_file, :source_line,
            :source_offset, :raw_log, :stacktrace, :created_at
            )""", _parameters(occurrence),
        )

    def occurrences(
        self, incident_id: str, limit: int, offset: int, *, oldest_first: bool = False,
    ) -> list[Occurrence]:
        direction = "ASC" if oldest_first else "DESC"
        rows = self.db.execute(
            f"""SELECT * FROM error_occurrences WHERE incident_id = ?
            ORDER BY timestamp {direction}, id LIMIT ? OFFSET ?""",
            (incident_id, limit, offset),
        )
        return [Occurrence.model_validate(dict(row)) for row in rows]

    def totals(self) -> tuple[int, int]:
        row = self.db.execute("SELECT COUNT(*), COALESCE(SUM(occurrence_count), 0) FROM incidents").fetchone()
        return row[0], row[1]
