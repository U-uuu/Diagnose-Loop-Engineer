"""使用本地 SQLite 和 HTTP 模拟覆盖完整诊断链路。"""

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from autoloop.application.services.discovery import scan_discovery
from autoloop.application.services.incidents import IncidentManager
from autoloop.cli.discovery import app
from autoloop.config.settings import ContextLimits, LLMSettings
from autoloop.runtime.context import ContextBuilder
from autoloop.runtime.executor import execute
from autoloop.schemas.diagnosis import DiagnosisDraft, DiagnosisRun, DiagnosisStatus
from autoloop.schemas.repair import RepairDraft
from autoloop.schemas.report import DiagnosisReport
from autoloop.storage.diagnosis_repository import DiagnosisRepository
from autoloop.storage.execution_store import connect


@pytest.fixture
def scanned(tmp_path: Path) -> tuple[Path, str]:
    db = tmp_path / "data" / "incidents.sqlite3"
    project = tmp_path / "project"
    project.mkdir()
    records = [
        {
            "timestamp": f"2026-01-01T00:00:{second:02d}Z",
            "service": "订单服务", "level": "ERROR", "exception_type": "SQLException",
            "message": "数据库连接失败 password=fixture-password",
            "stacktrace": 'at demo.Order.load(Order.java:21)\n' + "重复堆栈" * 1000,
        }
        for second in range(6)
    ]
    for name in ("service.jsonl", "worker.jsonl"):
        (project / name).write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in records),
            encoding="utf-8",
        )
    outcome = scan_discovery(db, project)
    incident_id, = outcome.created
    return db, incident_id


def config() -> LLMSettings:
    return LLMSettings(
        provider="compatible", model="测试模型", base_url="https://llm.example/v1",
        api_key="fixture-key", max_retries=0,
    )


def draft(evidence: list[str]) -> dict:
    return {
        "summary": "订单服务报告数据库连接失败", "root_cause": "数据库连接池可能耗尽",
        "root_cause_category": "数据库", "confidence": 0.45, "evidence": evidence,
        "affected_components": ["连接池"], "missing_information": ["连接池使用率"],
        "alternative_causes": ["数据库限流", "连接地址错误"],
    }


def repair() -> dict:
    return {
        "objective": "恢复数据库连接", "steps": ["检查连接池使用率"],
        "suggested_changes": ["验证连接池假设后评估池大小"], "target_files": [],
        "expected_behavior": "服务可连接数据库", "test_strategy": ["验证数据库连接"],
        "risk_level": "MEDIUM", "requires_human_review": True,
    }


def output(data: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(data, ensure_ascii=False)}}],
        "usage": {"total_tokens": 70},
    })


def payload(request: httpx.Request) -> dict:
    messages = json.loads(request.content)["messages"]
    return next(json.loads(item["content"]) for item in messages
                if item["role"] == "user" and item["content"].startswith('{"context"'))


def respond(request: httpx.Request) -> httpx.Response:
    assert "fixture-password" not in request.content.decode()
    data = payload(request)
    if "diagnosis" in data:
        return output(repair())
    return output(draft([data["context"]["evidence"][0]["evidence_id"]]))


def test_complete_workflow_and_persist_history(scanned: tuple[Path, str]) -> None:
    db, incident_id = scanned
    outcomes = [
        execute(db, incident_id, settings_loader=config, transport=httpx.MockTransport(respond))
        for _ in range(2)
    ]
    for report in outcomes:
        assert isinstance(report, DiagnosisReport)
        assert report.run.status == DiagnosisStatus.COMPLETED
        assert report.run.model_calls["diagnose"].total_tokens == 70
        assert report.run.model_calls["plan_repair"].attempts == 1
        assert report.evidence[0].evidence_id == report.result.evidence[0]
        assert report.plan.diagnosis_id == report.run.diagnosis_id
        assert len(report.result.alternative_causes) == 2
        assert DiagnosisReport.model_validate_json(report.model_dump_json()) == report
        assert DiagnosisRepository(db).get(report.run.diagnosis_id) == report
    assert len(DiagnosisRepository(db).history(incident_id, 10, 0)) == 2


def test_context_limits_and_representative_evidence(scanned: tuple[Path, str]) -> None:
    db, incident_id = scanned
    manager = IncidentManager(db)
    incident = manager.get(incident_id)
    context = ContextBuilder(manager, ContextLimits(
        occurrences=4, evidence=3, stack_chars=180, context_bytes=3300,
    )).build(incident)
    assert 2 <= len(context.occurrences) <= 3
    assert {item.timestamp.second for item in context.occurrences} >= {0, 5}
    stacks = [item.stack_trace for item in context.occurrences if item.stack_trace]
    assert len(stacks) == 1 and len(stacks[0]) <= 180
    assert len(context.model_dump_json().encode()) <= 3300
    assert "fixture-password" not in context.model_dump_json()
    different_sources = {item.source_file for item in ContextBuilder(manager, ContextLimits()).build(incident).occurrences}
    assert different_sources == {"service.jsonl", "worker.jsonl"}
    assert context.project_context is None


def test_missing_and_empty_incident(scanned: tuple[Path, str]) -> None:
    db, incident_id = scanned
    manager = IncidentManager(db)
    manager.create(manager.get(incident_id).model_copy(update={
        "id": "INC-empty", "fingerprint": "empty", "occurrence_count": 0,
    }))
    transport = httpx.MockTransport(lambda _: pytest.fail("不应调用模型"))
    for item_id, expected in [("INC-missing", "找不到故障"), ("INC-empty", "没有发生记录")]:
        run = execute(db, item_id, settings_loader=config, transport=transport)
        assert isinstance(run, DiagnosisRun)
        assert run.status == DiagnosisStatus.FAILED and expected in (run.error_message or "")
        assert DiagnosisRepository(db).get(run.diagnosis_id) == run


@pytest.mark.parametrize(("mode", "expected", "expected_calls"), [
    ("bad-evidence", "证据编号", 1),
    ("bad-target", "未核实", 2),
    ("format", "JSON 结构", 2),
    ("planning-error", "限流", 2),
    ("uncertain-changes", "只能建议调查", 2),
])
def test_rejected_outputs_are_recorded(
    scanned: tuple[Path, str], mode: str, expected: str, expected_calls: int,
) -> None:
    db, incident_id = scanned
    calls = 0

    def simulated(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        data = payload(request)
        if mode == "format":
            return output({})
        if mode == "bad-evidence":
            return output(draft(["编造的证据编号"]))
        if "diagnosis" in data:
            if mode == "bad-target":
                return output(repair() | {"target_files": ["不存在.py"]})
            if mode == "planning-error":
                return httpx.Response(429)
            return output(repair())
        if mode == "uncertain-changes":
            return output(draft([]) | {"root_cause": None, "confidence": 0})
        return respond(request)

    run = execute(db, incident_id, settings_loader=config, transport=httpx.MockTransport(simulated))
    assert isinstance(run, DiagnosisRun)
    assert run.status == DiagnosisStatus.FAILED and expected in (run.error_message or "")
    assert calls == expected_calls
    assert DiagnosisRepository(db).get(run.diagnosis_id) == run


def test_uncertain_diagnosis_can_complete(scanned: tuple[Path, str]) -> None:
    db, incident_id = scanned

    def uncertain(request: httpx.Request) -> httpx.Response:
        if "diagnosis" in payload(request):
            return output(repair() | {"suggested_changes": []})
        return output(draft([]) | {"root_cause": None, "root_cause_category": None, "confidence": 0})

    report = execute(db, incident_id, settings_loader=config, transport=httpx.MockTransport(uncertain))
    assert isinstance(report, DiagnosisReport)
    assert report.result.root_cause is None and report.evidence == []
    assert report.plan.suggested_changes == []


def test_database_failure_rolls_back(scanned: tuple[Path, str]) -> None:
    db, incident_id = scanned
    DiagnosisRepository(db)
    with connect(db) as connection:
        connection.executescript("""
            CREATE TRIGGER reject_plan BEFORE INSERT ON repair_plans
            BEGIN SELECT RAISE(ABORT, '测试回滚'); END;
        """)
    run = execute(db, incident_id, settings_loader=config, transport=httpx.MockTransport(respond))
    assert isinstance(run, DiagnosisRun) and run.status == DiagnosisStatus.FAILED
    assert "数据库读写失败" in (run.error_message or "")
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM diagnosis_results").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM repair_plans").fetchone()[0] == 0
        assert connection.execute("SELECT status FROM diagnosis_runs").fetchone()[0] == "FAILED"


def test_schemas() -> None:
    with pytest.raises(ValidationError):
        DiagnosisDraft.model_validate(draft(["有效"]) | {"confidence": 1.01})
    with pytest.raises(ValidationError):
        DiagnosisDraft.model_validate(draft([]))
    with pytest.raises(ValidationError):
        DiagnosisDraft.model_validate({})
    with pytest.raises(ValidationError):
        RepairDraft.model_validate(repair() | {"risk_level": "无风险"})


def test_cli_and_separate_process(
    scanned: tuple[Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, incident_id = scanned
    monkeypatch.setenv("DLE_DATA_DIR", str(db.parent))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    runner = CliRunner()
    monkeypatch.setattr(
        "autoloop.application.services.diagnosis.execute",
        lambda database, key: execute(
            database, key, settings_loader=config, transport=httpx.MockTransport(respond),
        ),
    )
    result = runner.invoke(app, ["diagnose", incident_id])
    assert result.exit_code == 0, (result.exception, result.output)
    assert "根因假设" in result.output
    diagnosis_id = DiagnosisRepository(db).history(incident_id, 20, 0)[0].diagnosis_id
    for args, expected in [
        (["diagnosis", "show", diagnosis_id], "支持证据"),
        (["diagnosis", "plan", diagnosis_id], "测试策略"),
        (["diagnosis", "history", incident_id], diagnosis_id),
    ]:
        completed = subprocess.run(
            [sys.executable, "-c", "from autoloop.cli.discovery import app; app()", *args],
            capture_output=True, encoding="utf-8", timeout=20, check=True,
        )
        assert expected in completed.stdout


def test_cli_missing_key_is_safe(
    scanned: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, incident_id = scanned
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DLE_DATA_DIR", str(db.parent))
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.setenv("LLM_MODEL", "测试模型")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["diagnose", incident_id])
    assert result.exit_code == 1
    assert "LLM_API_KEY" in result.output and "Traceback" not in result.output
    assert DiagnosisRepository(db).history(incident_id, 20, 0)[0].completed_at <= datetime.now(UTC)
