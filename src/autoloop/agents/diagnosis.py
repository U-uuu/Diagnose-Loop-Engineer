"""由故障证据生成并核验结构化根因假设。"""

from datetime import UTC, datetime

from autoloop.agents.prompts import DIAGNOSIS_PROMPT
from autoloop.agents.structured import request
from autoloop.runtime.llm import LLMClient, ResponseFormatError
from autoloop.schemas.diagnosis import DiagnosisDraft, DiagnosisResult, DiagnosticContext, ModelCall


def diagnose(
    client: LLMClient, context: DiagnosticContext, diagnosis_id: str, model_name: str,
) -> tuple[DiagnosisResult, ModelCall]:
    draft, metadata = request(
        client, DIAGNOSIS_PROMPT, {"context": context.model_dump(mode="json")}, DiagnosisDraft,
    )
    result = DiagnosisResult(
        **draft.model_dump(), diagnosis_id=diagnosis_id, incident_id=context.incident.incident_id,
        model_name=model_name, created_at=datetime.now(UTC),
    )
    return result, metadata


def validate_diagnosis(context: DiagnosticContext, result: DiagnosisResult) -> None:
    valid_ids = {item.evidence_id for item in context.evidence}
    if not set(result.evidence) <= valid_ids or len(set(result.evidence)) != len(result.evidence):
        raise ResponseFormatError("诊断引用了无效或重复的证据编号")
