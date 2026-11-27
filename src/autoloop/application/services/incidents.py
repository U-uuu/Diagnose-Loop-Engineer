"""查询故障、管理状态并统计发生次数。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from autoloop.schemas.incident import Category, Incident, IncidentStatus, Occurrence, Severity
from autoloop.storage.execution_store import connect
from autoloop.storage.incident_repository import IncidentRepository


class IncidentNotFound(ValueError):
    """指定的故障不存在。"""


def _require(repository: IncidentRepository, incident_id: str) -> Incident:
    incident = repository.get(incident_id)
    if incident is None:
        raise IncidentNotFound(f"找不到故障：{incident_id}")
    return incident


class IncidentManager:
    def __init__(self, database: Path) -> None:
        self.database = database

    def create(self, incident: Incident) -> None:
        with connect(self.database) as db, db:
            IncidentRepository(db).create(incident)

    def get(self, incident_id: str) -> Incident:
        with connect(self.database) as db:
            return _require(IncidentRepository(db), incident_id)

    def by_fingerprint(self, fingerprint: str) -> Incident | None:
        with connect(self.database) as db:
            return IncidentRepository(db).by_fingerprint(fingerprint)

    def list(
        self, status: IncidentStatus | None, category: Category | None,
        severity: Severity | None, limit: int, offset: int,
    ) -> list[Incident]:
        with connect(self.database) as db:
            return IncidentRepository(db).list(
                status=status, category=category, severity=severity, limit=limit, offset=offset,
            )

    def occurrences(self, incident_id: str, limit: int, offset: int) -> list[Occurrence]:
        with connect(self.database) as db:
            repository = IncidentRepository(db)
            _require(repository, incident_id)
            return repository.occurrences(incident_id, limit, offset)

    def diagnostic_occurrences(self, incident_id: str, limit: int) -> list[Occurrence]:
        with connect(self.database) as db, db:
            db.execute("BEGIN")
            repository = IncidentRepository(db)
            recent = repository.occurrences(incident_id, limit, 0)
            first = repository.occurrences(incident_id, 1, 0, oldest_first=True)
            return list({item.id: item for item in first + recent}.values())

    def set_status(self, incident_id: str, status: IncidentStatus) -> Incident:
        with connect(self.database) as db, db:
            db.execute("BEGIN IMMEDIATE")
            repository = IncidentRepository(db)
            incident = _require(repository, incident_id)
            incident.status = status
            incident.updated_at = datetime.now(UTC)
            repository.update(incident)
            return incident

    def totals(self) -> tuple[int, int]:
        with connect(self.database) as db:
            return IncidentRepository(db).totals()
