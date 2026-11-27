"""合并任务、证据、诊断和修复建议。"""

import json

from pydantic import BaseModel

from autoloop.schemas.diagnosis import DiagnosisResult, DiagnosisRun, LogEvidence
from autoloop.schemas.repair import RepairPlan


class DiagnosisReport(BaseModel):
    run: DiagnosisRun
    result: DiagnosisResult
    plan: RepairPlan
    evidence: list[LogEvidence]

    @classmethod
    def rehydrate(cls, run: DiagnosisRun, result: str, evidence: str, plan: str) -> "DiagnosisReport":
        return cls.model_validate({
            "run": run,
            "result": json.loads(result),
            "plan": json.loads(plan),
            **json.loads(evidence),
        })
