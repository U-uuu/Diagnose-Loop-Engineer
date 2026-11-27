"""连接上下文、模型角色和报告仓储。"""

from collections.abc import Callable
from datetime import UTC, datetime
import logging
import sqlite3
import traceback

from pydantic import ValidationError

from autoloop.agents.diagnosis import diagnose, validate_diagnosis
from autoloop.agents.planning import plan_repair, validate_plan
from autoloop.graph.state import DiagnosisState
from autoloop.runtime.context import ContextBuilder
from autoloop.runtime.llm import LLMClient, ModelError
from autoloop.schemas.diagnosis import DiagnosisStatus
from autoloop.schemas.incident import Incident
from autoloop.schemas.report import DiagnosisReport

logger = logging.getLogger(__name__)
Node = Callable[[DiagnosisState], DiagnosisState]


def guarded(node: Node) -> Node:
    def run_node(state: DiagnosisState) -> DiagnosisState:
        try:
            return node(state)
        except (OSError, ValueError, sqlite3.Error) as exc:
            logger.debug(
                "诊断 %s 在 %s 失败（%s）\n%s",
                state["run"].diagnosis_id, node.__name__, type(exc).__name__,
                "".join(traceback.format_tb(exc.__traceback__)),
            )
            if isinstance(exc, sqlite3.Error):
                reason = "诊断数据库读写失败"
            elif isinstance(exc, OSError):
                reason = "无法读取诊断所需的本地数据"
            elif isinstance(exc, ValidationError):
                reason = "诊断数据无法通过结构校验"
            else:
                reason = str(exc)
            return {
                "status": DiagnosisStatus.FAILED,
                "errors": [f"{node.__name__}：{reason}"],
                "retryable": (
                    exc.retryable if isinstance(exc, ModelError)
                    else isinstance(exc, (OSError, sqlite3.OperationalError))
                ),
            }

    return run_node


class DiagnosisNodes:
    def __init__(
        self, read_incident: Callable[[str], Incident], builder: ContextBuilder, client: LLMClient,
        save_report: Callable[[DiagnosisReport], None],
    ) -> None:
        self.read_incident = read_incident
        self.builder = builder
        self.client = client
        self.save_report = save_report

    def load_incident(self, state: DiagnosisState) -> DiagnosisState:
        return {"incident": self.read_incident(state["incident_id"])}

    def build_context(self, state: DiagnosisState) -> DiagnosisState:
        context = self.builder.build(state["incident"])
        run = state["run"].model_copy(update={
            "input_summary": {
                "occurrences": len(context.occurrences), "evidence": len(context.evidence),
                "bytes": len(context.model_dump_json().encode("utf-8")),
            },
        })
        return {"context": context, "run": run}

    def diagnose(self, state: DiagnosisState) -> DiagnosisState:
        run = state["run"]
        result, metadata = diagnose(self.client, state["context"], run.diagnosis_id, run.model_name or "")
        return {"diagnosis": result, "execution_metadata": {"diagnose": metadata}}

    def validate_diagnosis(self, state: DiagnosisState) -> DiagnosisState:
        validate_diagnosis(state["context"], state["diagnosis"])
        return {}

    def plan_repair(self, state: DiagnosisState) -> DiagnosisState:
        plan, metadata = plan_repair(self.client, state["context"], state["diagnosis"])
        return {
            "repair_plan": plan,
            "execution_metadata": state["execution_metadata"] | {"plan_repair": metadata},
        }

    def validate_plan(self, state: DiagnosisState) -> DiagnosisState:
        validate_plan(state["diagnosis"], state["repair_plan"])
        return {}

    def save_result(self, state: DiagnosisState) -> DiagnosisState:
        result = state["diagnosis"]
        report = DiagnosisReport(
            run=state["run"].model_copy(update={
                "status": DiagnosisStatus.COMPLETED, "completed_at": datetime.now(UTC),
                "model_calls": state["execution_metadata"],
            }),
            result=result, plan=state["repair_plan"],
            evidence=[item for item in state["context"].evidence if item.evidence_id in result.evidence],
        )
        self.save_report(report)
        return {"status": DiagnosisStatus.COMPLETED, "report": report}
