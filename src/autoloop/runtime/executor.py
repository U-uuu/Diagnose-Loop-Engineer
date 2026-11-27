"""管理模型连接和诊断任务的开始、成功与失败。"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from langsmith import tracing_context

from autoloop.agents.prompts import PROMPT_VERSION
from autoloop.application.services.incidents import IncidentManager
from autoloop.config.settings import ContextLimits, LLMSettings, llm_settings
from autoloop.graph.nodes import DiagnosisNodes
from autoloop.graph.workflow import run_workflow
from autoloop.runtime.context import ContextBuilder
from autoloop.runtime.llm import OpenAICompatibleClient
from autoloop.runtime.redaction import redact
from autoloop.schemas.diagnosis import DiagnosisRun, DiagnosisStatus
from autoloop.schemas.report import DiagnosisReport
from autoloop.storage.diagnosis_repository import DiagnosisRepository


def execute(
    database: Path, incident_id: str, *, settings_loader: Callable[[], LLMSettings] = llm_settings,
    transport: httpx.BaseTransport | None = None,
) -> DiagnosisRun | DiagnosisReport:
    repository = DiagnosisRepository(database)
    run = DiagnosisRun(
        diagnosis_id=f"DIAG-{uuid4().hex}", incident_id=incident_id, prompt_version=PROMPT_VERSION,
        started_at=datetime.now(UTC),
    )
    repository.start(run)
    try:
        settings = settings_loader()
    except OSError:
        run.error_message = "无法读取本地模型配置"
    except ValueError as exc:
        run.error_message = str(exc)
    else:
        secret = settings.api_key.get_secret_value()
        run.model_provider = settings.provider
        run.model_name = redact(settings.model, secret)
        incidents = IncidentManager(database)
        with tracing_context(enabled=False), httpx.Client(transport=transport) as http:
            nodes = DiagnosisNodes(
                incidents.get, ContextBuilder(incidents, ContextLimits(), secret),
                OpenAICompatibleClient(settings, http), repository.save,
            )
            state = run_workflow(nodes, {
                "incident_id": incident_id, "run": run, "status": DiagnosisStatus.RUNNING,
            })
        if "report" in state:
            return state["report"]
        run = state["run"]
        run.error_message = redact("；".join(state.get("errors", ["诊断未生成报告"])), secret)
        run.retryable = state.get("retryable", False)
        run.model_calls = state.get("execution_metadata", {})

    run.status = DiagnosisStatus.FAILED
    run.completed_at = datetime.now(UTC)
    repository.fail(run)
    return run
