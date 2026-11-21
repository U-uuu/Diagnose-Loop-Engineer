"""命令行入口。"""

import typer

from autoloop.cli.commands import scan

app = typer.Typer(help="在本地项目中查找诊断文件。")


@app.callback()
def main() -> None:
    """诊断本地软件项目。"""


app.command()(scan)
