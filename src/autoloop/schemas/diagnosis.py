"""诊断输入、模型输出和诊断任务的数据契约。"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from autoloop.schemas.incident import Category, IncidentStatus

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


class IncidentSummary(BaseModel):
    incident_id: str
    title: str
    category: Category
    fingerprint: str
    status: IncidentStatus
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime
    description: str


class OccurrenceSummary(BaseModel):
    occurrence_id: str
    event_id: str
    timestamp: datetime
    exception_type: str
    message: str
    stack_trace: str | None
    source_file: str
    source_line: int


class LogEvidence(BaseModel):
    evidence_id: str
    timestamp: datetime
    level: str
    message: str
    source: str
    occurrence_id: str


class ProjectContext(BaseModel):
    project_root: str
    project_name: str
    language: str | None = None
    framework: str | None = None
    project_structure_summary: str | None = None


class DiagnosticContext(BaseModel):
    incident: IncidentSummary
    occurrences: list[OccurrenceSummary]
    evidence: list[LogEvidence]
    project_context: ProjectContext | None = None


class DiagnosisDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: ShortText
    root_cause: ShortText | None
    root_cause_category: ShortText | None
    confidence: float = Field(ge=0, le=1, strict=True)
    evidence: list[ShortText] = Field(max_length=12)
    affected_components: list[ShortText] = Field(max_length=12)
    missing_information: list[ShortText] = Field(max_length=12)
    alternative_causes: list[ShortText] = Field(max_length=12)

    @model_validator(mode="after")
    def check_evidence(self) -> "DiagnosisDraft":
        if self.root_cause and not self.evidence:
            raise ValueError("根因假设需要证据")
        if not self.root_cause and not self.missing_information:
            raise ValueError("根因未明时需要列出待补充信息")
        return self


class DiagnosisResult(DiagnosisDraft):
    diagnosis_id: str
    incident_id: str
    model_name: str
    created_at: datetime


class DiagnosisStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ModelCall(BaseModel):
    duration_seconds: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    attempts: int = Field(ge=1)


class DiagnosisRun(BaseModel):
    diagnosis_id: str
    incident_id: str
    status: DiagnosisStatus = DiagnosisStatus.RUNNING
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    retryable: bool = False
    input_summary: dict[str, int] = Field(default_factory=dict)
    model_calls: dict[str, ModelCall] = Field(default_factory=dict)
