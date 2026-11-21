from pathlib import Path

import pytest

from autoloop.application.services.scan import ScanError, scan_project


def test_scan_finds_sorted_relative_candidates(tmp_path: Path) -> None:
    for name in ("z.LOG", "logs/app.jsonl", "readme.txt", ".git/history.log"):
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()

    result = scan_project(tmp_path)

    assert result.project_root == tmp_path.resolve()
    assert result.log_files == (Path("logs/app.jsonl"), Path("z.LOG"))


def test_empty_directory(tmp_path: Path) -> None:
    assert scan_project(tmp_path).log_files == ()


def test_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ScanError, match="找不到路径"):
        scan_project(tmp_path / "missing")


def test_rejects_regular_file(tmp_path: Path) -> None:
    file = tmp_path / "app.log"
    file.touch()
    with pytest.raises(ScanError, match="指定路径不是项目目录"):
        scan_project(file)
