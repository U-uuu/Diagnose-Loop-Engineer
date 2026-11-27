"""将诊断命令连接到统一运行时和结果仓储。"""

from pathlib import Path

from autoloop.runtime.executor import execute
from autoloop.schemas.diagnosis import DiagnosisRun
from autoloop.schemas.report import DiagnosisReport
from autoloop.storage.diagnosis_repository import DiagnosisRepository


def run_diagnosis(database: Path, incident_id: str) -> DiagnosisRun | DiagnosisReport:
    return execute(database, incident_id)


def get_diagnosis(database: Path, diagnosis_id: str) -> DiagnosisRun | DiagnosisReport:
    return DiagnosisRepository(database).get(diagnosis_id)


def diagnosis_history(database: Path, incident_id: str, limit: int, offset: int) -> list[DiagnosisRun]:
    return DiagnosisRepository(database).history(incident_id, limit, offset)
