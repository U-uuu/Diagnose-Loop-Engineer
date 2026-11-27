"""执行诊断并查询已保存的报告。"""

from collections.abc import Iterator
from contextlib import contextmanager
import logging
import sqlite3
from typing import Annotated

from rich.console import Console
from rich.text import Text
import typer

from autoloop.application.services.diagnosis import diagnosis_history, get_diagnosis, run_diagnosis
from autoloop.config.settings import database_path
from autoloop.schemas.diagnosis import DiagnosisRun
from autoloop.schemas.repair import RepairPlan
from autoloop.schemas.report import DiagnosisReport

app = typer.Typer(help="查看诊断结果、历史和修复建议。", no_args_is_help=True)


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except (sqlite3.Error, OSError):
        typer.echo("诊断数据库无法读写，请检查数据目录、可用空间和访问权限。", err=True)
        raise typer.Exit(1) from None
    except ValueError as exc:
        typer.echo(f"操作失败：{exc}", err=True)
        raise typer.Exit(1) from None


@contextmanager
def _debug(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    logger = logging.getLogger("autoloop")
    handler = logging.StreamHandler()
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()


def _print(message: str) -> None:
    Console().print(Text(message))


def _items(values: list[str]) -> str:
    return "\n".join(f"  - {value}" for value in values) or "  无"


def _print_run(run: DiagnosisRun) -> None:
    _print(f"故障编号：{run.incident_id}\n诊断编号：{run.diagnosis_id}\n状态：{run.status}")
    if run.error_message:
        _print(run.error_message)
        _print("可稍后重新执行诊断。" if run.retryable else "请处理上述原因后重新执行诊断。")


def _print_plan(plan: RepairPlan) -> None:
    _print(
        f"计划编号：{plan.plan_id}\n修复目标：{plan.objective}\n调查与验证步骤\n{_items(plan.steps)}\n"
        f"建议修改\n{_items(plan.suggested_changes)}\n目标文件\n{_items(plan.target_files)}\n"
        f"预期行为：{plan.expected_behavior}\n测试策略\n{_items(plan.test_strategy)}\n"
        f"风险等级：{plan.risk_level}\n人工审查：{'需要' if plan.requires_human_review else '无需'}"
    )


def _print_report(report: DiagnosisReport) -> None:
    _print_run(report.run)
    result, run = report.result, report.run
    elapsed = (run.completed_at - run.started_at).total_seconds() if run.completed_at else 0
    evidence = [f"{item.evidence_id} {item.source} {item.message}" for item in report.evidence]
    _print(
        f"故障摘要：{result.summary}\n根因假设：{result.root_cause or '暂无法确定'}\n"
        f"根因分类：{result.root_cause_category or '待确认'}\n置信度：{result.confidence:.2f}\n"
        f"支持证据\n{_items(evidence)}\n受影响组件\n{_items(result.affected_components)}\n"
        f"待补充信息\n{_items(result.missing_information)}\n备选原因\n{_items(result.alternative_causes)}\n"
        f"模型：{result.model_name}\n执行耗时：{elapsed:.2f} 秒"
    )
    _print_plan(report.plan)


def diagnose(
    incident_id: Annotated[str, typer.Argument(help="要诊断的故障编号。")],
    debug: Annotated[bool, typer.Option("--debug", help="显示诊断节点和安全堆栈位置。")] = False,
) -> None:
    """分析本地故障证据并保存修复建议。"""
    with _errors(), _debug(debug):
        outcome = run_diagnosis(database_path(), incident_id)
    if isinstance(outcome, DiagnosisRun):
        _print_run(outcome)
        raise typer.Exit(1)
    _print_report(outcome)


@app.command()
def show(diagnosis_id: str) -> None:
    """查看指定诊断的报告或失败状态。"""
    with _errors():
        outcome = get_diagnosis(database_path(), diagnosis_id)
    if isinstance(outcome, DiagnosisRun):
        _print_run(outcome)
    else:
        _print_report(outcome)


@app.command()
def history(
    incident_id: str, limit: Annotated[int, typer.Option(min=1, max=1000)] = 20,
    offset: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """分页查看指定故障的诊断历史。"""
    with _errors():
        records = diagnosis_history(database_path(), incident_id, limit, offset)
    for run in records:
        _print(f"{run.diagnosis_id}  {run.status}  {run.started_at.isoformat()}  {run.model_name or '未调用模型'}")
    if not records:
        _print("暂无诊断历史。")


@app.command()
def plan(diagnosis_id: str) -> None:
    """查看指定诊断的修复建议。"""
    with _errors():
        outcome = get_diagnosis(database_path(), diagnosis_id)
    if isinstance(outcome, DiagnosisRun):
        _print_run(outcome)
        _print("该诊断尚无修复计划。")
        raise typer.Exit(1)
    _print_plan(outcome.plan)
