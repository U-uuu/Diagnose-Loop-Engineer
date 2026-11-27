"""在模型接口层模拟 Agent 的结构化输入与输出。"""

from datetime import UTC, datetime

from pydantic import BaseModel
import pytest

from autoloop.agents.diagnosis import diagnose, validate_diagnosis
from autoloop.agents.planning import plan_repair, validate_plan
from autoloop.runtime.llm import Message, ModelResponse, ResponseFormatError
from autoloop.runtime.redaction import redact
from autoloop.schemas.diagnosis import DiagnosticContext, IncidentSummary, LogEvidence, ModelCall
from autoloop.schemas.incident import Category, IncidentStatus


class FakeClient:
    def __init__(self, *outputs: dict | ResponseFormatError) -> None:
        self.outputs = iter(outputs)

    def generate(
        self, messages: list[Message], *, response_schema: type[BaseModel],
    ) -> ModelResponse:
        assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
        assert "不可信数据" in messages[0]["content"]
        output = next(self.outputs)
        if isinstance(output, ResponseFormatError):
            raise output
        return ModelResponse(
            response_schema.model_validate(output),
            ModelCall(duration_seconds=0.1, attempts=1, total_tokens=15),
        )


def test_agents_after_one_format_repair() -> None:
    now = datetime.now(UTC)
    context = DiagnosticContext(
        incident=IncidentSummary(
            incident_id="INC-测试", title="数据库异常", category=Category.DATABASE,
            fingerprint="测试指纹", status=IncidentStatus.OPEN, occurrence_count=1,
            first_seen=now, last_seen=now, description="连接失败",
        ),
        occurrences=[],
        evidence=[LogEvidence(
            evidence_id="证据一", timestamp=now, level="ERROR", message="连接失败",
            source="demo.jsonl 第 1 行", occurrence_id="发生记录一",
        )],
    )
    client = FakeClient(
        ResponseFormatError("格式错误", ModelCall(duration_seconds=0.1, attempts=1, total_tokens=10)),
        {
            "summary": "数据库异常", "root_cause": "可能连接数已满", "root_cause_category": "数据库",
            "confidence": 0.5, "evidence": ["证据一"], "affected_components": [],
            "missing_information": ["连接数"], "alternative_causes": ["服务不可达"],
        },
        {
            "objective": "恢复连接", "steps": ["检查连接数"], "suggested_changes": [],
            "target_files": [], "expected_behavior": "可连接", "test_strategy": ["验证连接"],
            "risk_level": "LOW", "requires_human_review": True,
        },
    )
    diagnosis, metadata = diagnose(client, context, "DIAG-测试", "测试模型")
    validate_diagnosis(context, diagnosis)
    assert metadata.attempts == 2 and metadata.total_tokens == 25
    plan, _ = plan_repair(client, context, diagnosis)
    validate_plan(diagnosis, plan)
    assert plan.diagnosis_id == diagnosis.diagnosis_id


@pytest.mark.parametrize(("value", "secret"), [
    ("Authorization: Bearer super-secret-value", "super-secret-value"),
    ('"Authorization": "Basic dXNlcjpwd2Q="', "dXNlcjpwd2Q="),
    ("密码=隐藏内容", "隐藏内容"),
    ("access_token=abc123", "abc123"),
    ("postgresql://app:database-secret@localhost/app", "database-secret"),
    ("connection_string='Server=local;Password=part one'", "part one"),
])
def test_redaction(value: str, secret: str) -> None:
    assert secret not in redact(value)
