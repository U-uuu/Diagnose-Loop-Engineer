"""修复建议及其校验规则。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from autoloop.schemas.diagnosis import ShortText


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RepairDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: ShortText
    steps: list[ShortText] = Field(min_length=1, max_length=12)
    suggested_changes: list[ShortText] = Field(max_length=12)
    target_files: list[ShortText] = Field(max_length=12)
    expected_behavior: ShortText
    test_strategy: list[ShortText] = Field(min_length=1, max_length=12)
    risk_level: RiskLevel
    requires_human_review: bool = Field(strict=True)


class RepairPlan(RepairDraft):
    plan_id: str
    diagnosis_id: str
    incident_id: str
    created_at: datetime
