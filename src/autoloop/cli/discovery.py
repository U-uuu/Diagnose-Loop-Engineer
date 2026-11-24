"""故障发现与管理的命令行入口。"""

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
import sqlite3
from typing import Annotated

from rich.console import Console
from rich.text import Text
import typer
from typer.core import TyperGroup

from autoloop.application.services.discovery import scan_discovery, scan_history, scan_issues
from autoloop.application.services.incidents import IncidentManager
from autoloop.config.settings import database_path
from autoloop.schemas.incident import Category, IncidentStatus, ScanStatus, Severity


class ScanGroup(TyperGroup):
    """让路径形式与扫描历史共用一个命令入口。"""

    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        if args and args[0] not in {"history", "issues", "run", "--help", "-h"}:
            args = ["run", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(help="扫描日志并管理本地故障。", no_args_is_help=True)
scan_app = typer.Typer(cls=ScanGroup, help="扫描日志或查询扫描历史。", no_args_is_help=True)
incidents = typer.Typer(help="查询故障与更新状态。", no_args_is_help=True)
app.add_typer(scan_app, name="scan")
app.add_typer(incidents, name="incidents")

Limit = Annotated[int, typer.Option(min=1, max=1000, help="返回记录上限。")]
Offset = Annotated[int, typer.Option(min=0, help="跳过的记录数。")]

STATUS_LABELS = {
    ScanStatus.RUNNING: "执行中", ScanStatus.COMPLETED: "已完成",
    ScanStatus.PARTIAL: "部分完成", ScanStatus.FAILED: "失败",
}


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


def _print(message: str) -> None:
    Console().print(Text(message))


@contextmanager
def _handle_errors() -> Iterator[None]:
    try:
        yield
    except (OSError, sqlite3.Error, ValueError) as exc:
        Console(stderr=True).print(Text(f"操作失败：{exc}", style="red"))
        raise typer.Exit(1) from exc


@scan_app.command("run")
def scan(
    path: Annotated[Path, typer.Argument(help="待扫描的项目目录。")],
    logs: Annotated[Path | None, typer.Option(help="指定项目内的日志目录。")] = None,
    recursive: Annotated[bool, typer.Option("--recursive", help="递归遍历子目录。")] = False,
    output_format: Annotated[OutputFormat, typer.Option("--format", help="输出格式。")] = OutputFormat.TEXT,
) -> None:
    """扫描项目中的 JSONL 日志。"""
    progress_console = Console(stderr=True)

    def progress(done: int, total: int) -> None:
        progress_console.print(f"已处理日志文件 {done}/{total}")

    with _handle_errors():
        outcome = scan_discovery(
            database_path(), path, logs=logs, recursive=recursive,
            progress=progress if output_format == OutputFormat.TEXT else None,
        )
    run = outcome.run
    if output_format == OutputFormat.JSON:
        typer.echo(outcome.model_dump_json())
    else:
        _print(
            f"扫描编号：{run.id}  状态：{STATUS_LABELS[run.status]}\n"
            f"文件：{run.scanned_files}  行数：{run.scanned_lines}  解析成功：{run.parsed_entries}  "
            f"解析失败：{run.parse_errors}  文件错误：{run.file_errors}\n"
            f"发现故障：{run.detected_errors}  重复记录：{run.skipped_entries}"
        )
        _print(f"新建故障（{run.new_incidents}）：{'、'.join(outcome.created) or '无'}")
        _print(f"更新故障（{run.updated_incidents}）：{'、'.join(outcome.updated) or '无'}")
        if run.error_message:
            _print(run.error_message)
        for issue in run.issues:
            position = f"第 {issue.source_line} 行" if issue.source_line else ""
            _print(f"{issue.source_file} {position} {issue.reason}")
        if run.parse_errors + run.file_errors > len(run.issues):
            _print(f"查看其余问题请运行：dle scan issues {run.id}")
    if run.status in {ScanStatus.FAILED, ScanStatus.PARTIAL}:
        raise typer.Exit(1 if run.status == ScanStatus.FAILED else 2)


@scan_app.command()
def history(limit: Limit = 20, offset: Offset = 0) -> None:
    """查看扫描历史。"""
    with _handle_errors():
        runs = scan_history(database_path(), limit, offset)
    for run in runs:
        _print(
            f"{run.id}  {STATUS_LABELS[run.status]}  {run.started_at.isoformat()}  "
            f"文件 {run.scanned_files}  行 {run.scanned_lines}  故障 {run.detected_errors}  "
            f"解析失败 {run.parse_errors}  文件错误 {run.file_errors}  "
            f"新建 {run.new_incidents}  更新 {run.updated_incidents}  重复 {run.skipped_entries}"
        )
    if not runs:
        _print("暂无扫描历史。")


@scan_app.command()
def issues(scan_id: str, limit: Limit = 20, offset: Offset = 0) -> None:
    """分页查看扫描问题及其文件位置。"""
    with _handle_errors():
        records = scan_issues(database_path(), scan_id, limit, offset)
    for item in records:
        position = f"第 {item.source_line} 行，字节偏移 {item.source_offset}" if item.source_line else ""
        _print(f"{item.source_file} {position} {item.reason}")
    if not records:
        _print("该扫描没有对应的问题记录。")


@incidents.command("list")
def list_incidents(
    status: Annotated[IncidentStatus | None, typer.Option(help="按故障状态筛选。")] = None,
    category: Annotated[Category | None, typer.Option(help="按故障分类筛选。")] = None,
    severity: Annotated[Severity | None, typer.Option(help="按严重程度筛选。")] = None,
    limit: Limit = 20, offset: Offset = 0,
) -> None:
    """按条件分页查看故障。"""
    with _handle_errors():
        records = IncidentManager(database_path()).list(status, category, severity, limit, offset)
    for incident in records:
        _print(
            f"{incident.id}  {incident.status}  {incident.category}  "
            f"{incident.severity}  {incident.occurrence_count} 次  {incident.title}"
        )
    if not records:
        _print("没有符合条件的故障。")


@incidents.command()
def show(incident_id: str) -> None:
    """查看故障详情。"""
    with _handle_errors():
        item = IncidentManager(database_path()).get(incident_id)
    _print(
        f"故障编号：{item.id}\n标题：{item.title}\n分类：{item.category}\n异常类型：{item.error_type}\n"
        f"故障描述：{item.error_message}\n首次发生：{item.first_seen.isoformat()}\n"
        f"最近发生：{item.last_seen.isoformat()}\n发生次数：{item.occurrence_count}\n"
        f"状态：{item.status}\n严重级别：{item.severity}\n指纹：{item.fingerprint}"
    )


@incidents.command()
def occurrences(incident_id: str, limit: Limit = 20, offset: Offset = 0) -> None:
    """按时间分页查看故障的原始发生记录。"""
    with _handle_errors():
        records = IncidentManager(database_path()).occurrences(incident_id, limit, offset)
    for item in records:
        _print(
            f"{item.timestamp.isoformat()}  {item.source_file} 第 {item.source_line} 行 "
            f"（字节偏移 {item.source_offset}）\n{item.raw_log.rstrip()}"
        )
    if not records:
        _print("暂无发生记录。")


@incidents.command()
def status(incident_id: str, new_status: IncidentStatus) -> None:
    """设置故障状态。"""
    with _handle_errors():
        item = IncidentManager(database_path()).set_status(incident_id, new_status)
    _print(f"故障 {item.id} 的状态已更新为 {item.status}")


@incidents.command()
def resolve(incident_id: str) -> None:
    """将故障标记为已解决。"""
    status(incident_id, IncidentStatus.RESOLVED)


@incidents.command()
def reopen(incident_id: str) -> None:
    """重新打开故障。"""
    status(incident_id, IncidentStatus.OPEN)


@incidents.command()
def stats() -> None:
    """统计故障总数和发生次数。"""
    with _handle_errors():
        incident_count, occurrence_count = IncidentManager(database_path()).totals()
    _print(f"故障总数：{incident_count}  总发生次数：{occurrence_count}")
