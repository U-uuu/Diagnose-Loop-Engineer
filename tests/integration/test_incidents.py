import json
from pathlib import Path
import sqlite3

import pytest
from typer.testing import CliRunner

from autoloop.application.services.discovery import scan_discovery, scan_history, scan_issues
from autoloop.application.services.incidents import IncidentManager
from autoloop.cli.discovery import app
from autoloop.schemas.incident import Category, IncidentStatus, ScanStatus, Severity
from autoloop.storage.execution_store import connect
from autoloop.storage.incident_repository import IncidentRepository

runner = CliRunner()


def write_log(path: Path, number: int, second: int, *, append: bool = False) -> None:
    with path.open("a" if append else "w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "timestamp": f"2026-01-01T00:00:{second:02d}Z",
            "level": "ERROR", "service": "订单服务", "message": f"用户 {number} 不存在",
            "exception_type": "NullPointerException",
        }, ensure_ascii=False) + "\n")


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    write_log(root / "a.jsonl", 1001, 1)
    write_log(root / "b.jsonl", 1002, 2)
    return root, tmp_path / "data" / "incidents.sqlite3"


def test_aggregation_deduplication_rotation_and_status(project: tuple[Path, Path]) -> None:
    root, db = project
    outcome = scan_discovery(db, root)
    manager = IncidentManager(db)
    assert outcome.run.scanned_files == 2 and outcome.run.new_incidents == 1
    incident_id, = outcome.created
    first = manager.get(incident_id)
    assert first.occurrence_count == 2 and first.last_seen.second == 2
    assert manager.by_fingerprint(first.fingerprint) == first
    manager.set_status(incident_id, IncidentStatus.RESOLVED)
    repeated = scan_discovery(db, root)
    assert repeated.run.skipped_entries == 2 and not repeated.updated
    assert manager.get(incident_id).status == IncidentStatus.RESOLVED
    write_log(root / "b.jsonl", 1003, 3, append=True)
    assert scan_discovery(db, root).updated == [incident_id]
    updated = manager.get(incident_id)
    assert updated.status == IncidentStatus.OPEN
    assert updated.first_seen == first.first_seen
    assert updated.last_seen.second == 3 and updated.occurrence_count == 3
    (root / "a.jsonl").rename(root / "rotated.jsonl")
    write_log(root / "a.jsonl", 1001, 1)
    assert scan_discovery(db, root).updated == [incident_id]
    assert IncidentManager(db).get(incident_id).occurrence_count == 4
    assert manager.totals() == (1, 4)


def test_repository_filter_pagination_and_unique_constraint(project: tuple[Path, Path]) -> None:
    root, db = project
    item_id, = scan_discovery(db, root).created
    manager = IncidentManager(db)
    item = manager.get(item_id)
    assert manager.list(IncidentStatus.OPEN, Category.NULL_POINTER, Severity.ERROR, 1, 0) == [item]
    assert not manager.list(IncidentStatus.OPEN, Category.DATABASE, Severity.ERROR, 1, 0)
    assert not manager.list(IncidentStatus.OPEN, Category.NULL_POINTER, Severity.ERROR, 1, 1)
    assert manager.occurrences(item_id, 1, 1)[0].source_file == "a.jsonl"
    with pytest.raises(sqlite3.IntegrityError):
        manager.create(item.model_copy(update={"id": "另一个编号"}))
    assert manager.totals() == (1, 2)


def test_database_failure_rolls_back_all_incidents(
    project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = project
    original = IncidentRepository.add_occurrence

    def fail_on_second(self, occurrence):
        if occurrence.source_file == "b.jsonl":
            raise sqlite3.OperationalError("模拟写入故障")
        original(self, occurrence)

    monkeypatch.setattr(IncidentRepository, "add_occurrence", fail_on_second)
    failed = scan_discovery(db, root)
    assert failed.run.status == ScanStatus.FAILED
    assert not failed.created and not failed.updated
    assert IncidentManager(db).totals() == (0, 0)
    assert scan_history(db, 10, 0)[0].status == ScanStatus.FAILED
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM file_offsets").fetchone()[0] == 0


def test_partial_parse_and_invalid_paths(project: tuple[Path, Path]) -> None:
    root, db = project
    (root / "broken.jsonl").write_bytes(b"bad\n\xff\n")
    (root / "empty.jsonl").touch()
    partial = scan_discovery(db, root)
    assert partial.run.status == ScanStatus.PARTIAL
    assert partial.run.scanned_files == 4 and partial.run.parse_errors == 2
    assert [issue.source_offset for issue in partial.run.issues] == [0, 4]
    assert scan_issues(db, partial.run.id, 1, 1)[0].source_line == 2
    assert scan_discovery(db, root / "missing").run.status == ScanStatus.FAILED
    assert scan_discovery(db, root, logs=root / "missing").run.status == ScanStatus.FAILED
    assert scan_discovery(db, root, logs=root.parent).run.status == ScanStatus.FAILED


def test_scan_rolls_back_file_modified_mid_read(
    project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autoloop.application.services import discovery

    root, db = project
    original = discovery.read_lines

    def read_with_change(project_root: Path, relative: Path):
        for line in original(project_root, relative):
            if relative.name == "a.jsonl":
                write_log(root / "a.jsonl", 1004, 4, append=True)
            yield line

    monkeypatch.setattr(discovery, "read_lines", read_with_change)
    outcome = scan_discovery(db, root)
    assert outcome.run.status == ScanStatus.PARTIAL and outcome.run.file_errors == 1
    assert IncidentManager(db).totals() == (1, 1)


def test_cli_lifecycle(project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    root, db = project
    monkeypatch.setenv("DLE_DATA_DIR", str(db.parent))

    def invoke(*args: str):
        result = runner.invoke(app, list(args))
        assert result.exit_code == 0, (result.output, result.exception)
        return result.stdout

    result = json.loads(invoke("scan", str(root), "--logs", str(root), "--recursive", "--format", "json"))
    incident_id, = result["created"]
    assert result["run"]["detected_errors"] == 2
    assert incident_id in invoke("incidents", "list", "--status", "OPEN", "--category", "NULL_POINTER",
                                 "--severity", "ERROR", "--limit", "1", "--offset", "0")
    assert "发生次数：2" in invoke("incidents", "show", incident_id)
    assert "b.jsonl" in invoke("incidents", "occurrences", incident_id, "--limit", "1")
    assert "RESOLVED" in invoke("incidents", "resolve", incident_id)
    assert "IN_PROGRESS" in invoke("incidents", "status", incident_id, "IN_PROGRESS")
    assert "OPEN" in invoke("incidents", "reopen", incident_id)
    assert result["run"]["id"] in invoke("scan", "history")
    assert "总发生次数：2" in invoke("incidents", "stats")
    assert runner.invoke(app, ["incidents", "show", "不存在"]).exit_code == 1
    assert runner.invoke(app, ["scan", str(root / "missing")]).exit_code == 1


def test_all_parse_error_locations_are_saved(project: tuple[Path, Path]) -> None:
    root, db = project
    (root / "broken.jsonl").write_bytes(b"bad\n" * 110)
    result = scan_discovery(db, root)
    assert result.run.parse_errors == 110
    assert len(result.run.issues) == 100
    last = scan_issues(db, result.run.id, 1, 109)[0]
    assert last.source_line == 110 and last.source_offset == 436


def test_default_logs_directory_and_recursion(project: tuple[Path, Path]) -> None:
    root, db = project
    logs = root / "logs"
    (logs / "nested").mkdir(parents=True)
    assert scan_discovery(db, root).run.scanned_files == 0
    write_log(logs / "nested" / "app.jsonl", 1001, 1)
    outcome = scan_discovery(db, root, recursive=True)
    assert outcome.run.scanned_files == 1
    assert IncidentManager(db).occurrences(outcome.created[0], 1, 0)[0].source_file == "logs/nested/app.jsonl"


def test_unreadable_file_does_not_stop_other_files(
    project: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = project
    original = Path.open

    def open_with_error(self: Path, *args, **kwargs):
        if self == root / "b.jsonl":
            raise PermissionError("模拟文件权限不足")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_with_error)
    outcome = scan_discovery(db, root)
    assert outcome.run.status == ScanStatus.PARTIAL
    assert outcome.run.file_errors == 1 and outcome.run.scanned_files == 1
    assert IncidentManager(db).totals() == (1, 1)
