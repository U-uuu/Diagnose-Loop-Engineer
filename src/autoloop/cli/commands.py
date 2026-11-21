"""应用用例的命令行入口。"""

from pathlib import Path

import typer
from rich.console import Console
from rich.text import Text

from autoloop.application.services.scan import ScanError, scan_project


def scan(path: Path) -> None:
    """在项目目录中查找候选日志文件。"""
    try:
        result = scan_project(path)
    except ScanError as exc:
        Console(stderr=True).print(Text(f"错误：{exc}", style="red"))
        raise typer.Exit(1) from exc

    console = Console()
    console.print(Text(f"项目目录：{result.project_root}"))
    console.print(f"候选日志文件数：{len(result.log_files)}")
    for log_file in result.log_files:
        console.print(Text(f"  {log_file.as_posix()}"))
