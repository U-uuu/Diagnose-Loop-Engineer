from pathlib import Path

from typer.testing import CliRunner

from autoloop.cli.main import app

runner = CliRunner()


def test_help_lists_scan() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.stdout


def test_scan_displays_candidates(tmp_path: Path) -> None:
    (tmp_path / "app.log").touch()
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "候选日志文件数：1" in result.stdout
    assert "app.log" in result.stdout


def test_scan_reports_invalid_path(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "找不到路径" in result.stderr
