"""诊断节点间流转的状态。"""

from typing import TypedDict

from autoloop.schemas.diagnosis import DiagnosisResult, DiagnosisRun, DiagnosisStatus, DiagnosticContext, ModelCall
from autoloop.schemas.incident import Incident
from autoloop.schemas.repair import RepairPlan
from autoloop.schemas.report import DiagnosisReport


class DiagnosisState(TypedDict, total=False):
    incident_id: str
    run: DiagnosisRun
    incident: Incident
    context: DiagnosticContext
    diagnosis: DiagnosisResult
    repair_plan: RepairPlan
    errors: list[str]
    status: DiagnosisStatus
    retryable: bool
    execution_metadata: dict[str, ModelCall]
    report: DiagnosisReport
