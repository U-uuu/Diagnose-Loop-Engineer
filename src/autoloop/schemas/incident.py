"""日志、故障及扫描记录的数据契约。"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class Category(StrEnum):
    NULL_POINTER = "NULL_POINTER"
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    FILE_IO = "FILE_IO"
    MEMORY = "MEMORY"
    TYPE_ERROR = "TYPE_ERROR"
    VALIDATION = "VALIDATION"
    UNKNOWN = "UNKNOWN"


class Severity(StrEnum):
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class ScanStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class LogEntry(BaseModel):
    timestamp: AwareDatetime
    level: str = Field(min_length=1, strict=True)
    service: str = Field(min_length=1, strict=True)
    message: str = Field(min_length=1, strict=True)
    exception_type: str | None = None
    exception_message: str | None = None
    stacktrace: str | None = None
    trace_id: str | None = None
    source_file: str
    source_line: int
    source_offset: int

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("时间戳必须是带时区的 ISO 8601 字符串")
        return datetime.fromisoformat(value)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("level", "service", "message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("必需字段不能为空")
        return value.strip()


class ErrorEvent(BaseModel):
    event_id: str
    project_id: str
    timestamp: datetime
    service: str
    error_type: str
    error_message: str
    error_category: Category
    severity: Severity
    stacktrace: str | None
    fingerprint: str
    source_file: str
    source_line: int
    source_offset: int


class Incident(BaseModel):
    id: str
    project_id: str
    title: str
    category: Category
    error_type: str
    error_message: str
    fingerprint: str
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int = Field(ge=0)
    status: IncidentStatus
    severity: Severity
    created_at: datetime
    updated_at: datetime


class Occurrence(BaseModel):
    id: str
    incident_id: str
    event_id: str
    timestamp: datetime
    source_file: str
    source_line: int
    source_offset: int
    raw_log: str
    stacktrace: str | None
    created_at: datetime


class ScanIssue(BaseModel):
    source_file: str
    source_line: int | None = None
    source_offset: int | None = None
    reason: str


class ScanRun(BaseModel):
    id: str
    project_id: str
    project_path: str
    started_at: datetime
    finished_at: datetime | None = None
    status: ScanStatus = ScanStatus.RUNNING
    scanned_files: int = 0
    scanned_lines: int = 0
    parsed_entries: int = 0
    parse_errors: int = 0
    detected_errors: int = 0
    new_incidents: int = 0
    updated_incidents: int = 0
    skipped_entries: int = 0
    file_errors: int = 0
    error_message: str | None = None
    issues: list[ScanIssue] = Field(default_factory=list)


class ScanOutcome(BaseModel):
    run: ScanRun
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
