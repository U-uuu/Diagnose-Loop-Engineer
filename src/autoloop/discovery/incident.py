"""将去重后的故障事件聚合到同一事件记录。"""

from datetime import UTC, datetime
from uuid import uuid4

from autoloop.schemas.incident import ErrorEvent, Incident, IncidentStatus, Occurrence, Severity
from autoloop.storage.incident_repository import IncidentRepository


def aggregate(
    repository: IncidentRepository, event: ErrorEvent, raw_log: str,
) -> tuple[str, bool] | None:
    if repository.has_event(event.event_id):
        return None
    now = datetime.now(UTC)
    incident = repository.by_fingerprint(event.fingerprint)
    created = incident is None
    title = f"{event.service}：{event.error_type}"
    if incident is None:
        incident = Incident(
            id=f"INC-{uuid4().hex}", project_id=event.project_id, title=title,
            category=event.error_category, error_type=event.error_type,
            error_message=event.error_message, fingerprint=event.fingerprint,
            first_seen=event.timestamp, last_seen=event.timestamp, occurrence_count=1,
            status=IncidentStatus.OPEN, severity=event.severity, created_at=now, updated_at=now,
        )
        repository.create(incident)
    else:
        if event.timestamp >= incident.last_seen:
            incident.last_seen = event.timestamp
            incident.error_message = event.error_message
        incident.occurrence_count += 1
        incident.updated_at = now
        if event.severity == Severity.CRITICAL:
            incident.severity = Severity.CRITICAL
        if incident.status == IncidentStatus.RESOLVED:
            incident.status = IncidentStatus.OPEN
        repository.update(incident)
    repository.add_occurrence(Occurrence(
        id=event.event_id, incident_id=incident.id, event_id=event.event_id,
        timestamp=event.timestamp, source_file=event.source_file, source_line=event.source_line,
        source_offset=event.source_offset, raw_log=raw_log, stacktrace=event.stacktrace,
        created_at=now,
    ))
    return incident.id, created
