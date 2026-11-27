"""独立生成并核验修复建议。"""

from datetime import UTC, datetime
from uuid import uuid4

from autoloop.agents.prompts import PLANNING_PROMPT
from autoloop.agents.structured import request
from autoloop.runtime.llm import LLMClient, ResponseFormatError
from autoloop.schemas.diagnosis import DiagnosisResult, DiagnosticContext, ModelCall
from autoloop.schemas.repair import RepairDraft, RepairPlan


def plan_repair(
    client: LLMClient, context: DiagnosticContext, diagnosis: DiagnosisResult,
) -> tuple[RepairPlan, ModelCall]:
    draft, metadata = request(
        client, PLANNING_PROMPT,
        {"context": context.model_dump(mode="json"), "diagnosis": diagnosis.model_dump(mode="json")},
        RepairDraft,
    )
    return RepairPlan(
        **draft.model_dump(), plan_id=f"PLAN-{uuid4().hex}", diagnosis_id=diagnosis.diagnosis_id,
        incident_id=diagnosis.incident_id, created_at=datetime.now(UTC),
    ), metadata


def validate_plan(diagnosis: DiagnosisResult, plan: RepairPlan) -> None:
    if plan.target_files:
        raise ResponseFormatError("修复计划包含未核实的目标文件")
    if not plan.requires_human_review:
        raise ResponseFormatError("修复计划必须标记为需要人工审查")
    if diagnosis.root_cause is None and plan.suggested_changes:
        raise ResponseFormatError("根因未明确时，修复计划只能建议调查与验证")
