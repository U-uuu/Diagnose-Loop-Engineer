"""协调全量扫描、故障聚合及事务边界。"""

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from autoloop.discovery.detector import detect
from autoloop.discovery.fingerprint import digest
from autoloop.discovery.incident import aggregate
from autoloop.discovery.log_parser import parse_line
from autoloop.discovery.log_scanner import find_logs, read_lines
from autoloop.schemas.incident import ScanIssue, ScanOutcome, ScanRun, ScanStatus
from autoloop.storage.execution_store import connect
from autoloop.storage.incident_repository import IncidentRepository
from autoloop.storage.scan_repository import ScanRepository

MAX_ISSUE_SAMPLES = 100


def _issue(scans: ScanRepository, run: ScanRun, source: str, reason: str, line: int | None = None,
           offset: int | None = None) -> None:
    issue = ScanIssue(source_file=source, source_line=line, source_offset=offset, reason=reason)
    scans.save_issue(run.id, issue)
    if len(run.issues) < MAX_ISSUE_SAMPLES:
        run.issues.append(issue)


def _log_root(root: Path, logs: Path | None) -> Path:
    if not root.is_dir():
        raise ValueError("指定路径不是项目目录")
    if logs is None:
        candidate = root / "logs"
        logs = candidate if candidate.exists() or candidate.is_symlink() else root
    elif not logs.is_absolute():
        from_cwd = logs.resolve()
        logs = from_cwd if from_cwd.is_relative_to(root) and from_cwd.is_dir() else root / logs
    resolved = logs.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        raise ValueError("日志目录必须位于指定项目目录内")
    return resolved


def _scan_files(
    db: sqlite3.Connection, outcome: ScanOutcome, root: Path, log_root: Path,
    recursive: bool, progress: Callable[[int, int], None] | None,
) -> None:
    run = outcome.run
    scans = ScanRepository(db)
    discovery_issues: list[OSError] = []
    paths = find_logs(log_root, recursive=recursive, suffixes={".jsonl"}, issues=discovery_issues)
    for exc in discovery_issues:
        run.file_errors += 1
        _issue(scans, run, exc.filename or str(log_root), f"无法枚举日志目录：{exc}")
    incidents = IncidentRepository(db)
    created_ids: set[str] = set()
    updated_ids: set[str] = set()
    for index, path in enumerate(paths, 1):
        relative = (log_root / path).relative_to(root)
        source = relative.as_posix()
        position: tuple[str, int] | None = None
        file_actions: dict[str, bool] = {}
        db.execute("SAVEPOINT scan_file")
        saved_parse_errors = run.parse_errors
        saved_issues = len(run.issues)
        try:
            for line in read_lines(root, relative):
                run.scanned_lines += 1
                position = (line.file_identity, line.end_offset)
                try:
                    if line.oversized:
                        raise ValueError("单行日志超过大小限制")
                    entry = parse_line(line)
                except ValueError as exc:
                    run.parse_errors += 1
                    _issue(scans, run, source, f"无法解析日志：{exc}", line.number, line.offset)
                    continue
                run.parsed_entries += 1
                event_id = digest(
                    run.project_id, line.file_identity, line.offset,
                    hashlib.sha256(line.raw).hexdigest(),
                )
                event = detect(entry, run.project_id, event_id)
                if event is None:
                    continue
                run.detected_errors += 1
                action = aggregate(incidents, event, line.raw.decode("utf-8"))
                if action is None:
                    run.skipped_entries += 1
                else:
                    incident_id, created = action
                    file_actions[incident_id] = file_actions.get(incident_id, False) or created
        except OSError as exc:
            db.execute("ROLLBACK TO scan_file")
            run.parse_errors = saved_parse_errors
            del run.issues[saved_issues:]
            run.file_errors += 1
            _issue(scans, run, source, f"未保存该文件的故障记录：{exc}")
            scans.invalidate_offset(run.project_id, source)
        else:
            run.scanned_files += 1
            for incident_id, created in file_actions.items():
                (created_ids if created else updated_ids).add(incident_id)
            if position is not None:
                scans.save_offset(run.project_id, source, *position)
            else:
                scans.invalidate_offset(run.project_id, source)
        db.execute("RELEASE scan_file")
        if progress is not None:
            progress(index, len(paths))
    outcome.created = sorted(created_ids)
    outcome.updated = sorted(updated_ids - created_ids)
    run.new_incidents = len(outcome.created)
    run.updated_incidents = len(outcome.updated)
    if run.file_errors and not run.scanned_files:
        run.status = ScanStatus.FAILED
        run.error_message = "所有候选日志均无法完整扫描"
    elif run.file_errors or run.parse_errors:
        run.status = ScanStatus.PARTIAL
    else:
        run.status = ScanStatus.COMPLETED


def scan_discovery(
    database: Path, project: Path, *, logs: Path | None = None, recursive: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> ScanOutcome:
    root = project.resolve()
    outcome = ScanOutcome(run=ScanRun(
        id=f"SCAN-{uuid4().hex}", project_id=digest(str(root)), project_path=str(root),
        started_at=datetime.now(UTC),
    ))
    run = outcome.run
    with connect(database) as db:
        runs = ScanRepository(db)
        with db:
            runs.save(run)
        try:
            log_root = _log_root(root, logs)
            with db:
                db.execute("BEGIN IMMEDIATE")
                _scan_files(db, outcome, root, log_root, recursive, progress)
                run.finished_at = datetime.now(UTC)
                runs.save(run)
        except (OSError, ValueError, sqlite3.Error) as exc:
            run.status = ScanStatus.FAILED
            run.error_message = f"扫描失败：{exc}"
            run.finished_at = datetime.now(UTC)
            outcome.created.clear()
            outcome.updated.clear()
            run.new_incidents = run.updated_incidents = 0
            with db:
                runs.save(run)
    return outcome


def scan_history(database: Path, limit: int, offset: int) -> list[ScanRun]:
    with connect(database) as db:
        return ScanRepository(db).history(limit, offset)


def scan_issues(database: Path, scan_id: str, limit: int, offset: int) -> list[ScanIssue]:
    with connect(database) as db:
        return ScanRepository(db).issues(scan_id, limit, offset)
