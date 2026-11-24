import json
from pathlib import Path

import pytest

from autoloop.discovery.classifier import classify
from autoloop.discovery.detector import detect
from autoloop.discovery.fingerprint import fingerprint
from autoloop.discovery.log_parser import parse_line
from autoloop.discovery.log_scanner import MAX_LINE_BYTES, LogLine, find_logs, read_lines
from autoloop.schemas.incident import Category


def log_line(**changes: object) -> LogLine:
    data = {
        "timestamp": "2026-01-01T08:00:00+08:00",
        "service": "订单服务", "level": "INFO", "message": "服务已启动",
    }
    raw = json.dumps(data | changes, ensure_ascii=False).encode()
    return LogLine("app.jsonl", 2, 5, raw, "identity", 5 + len(raw))


def test_parser_normalizes_time_and_preserves_source() -> None:
    entry = parse_line(log_line(trace_id=None, stacktrace=None, source_line=100))
    assert entry.timestamp.isoformat() == "2026-01-01T00:00:00+00:00"
    assert entry.source_line == 2 and entry.source_offset == 5
    assert entry.message == "服务已启动"
    assert entry.trace_id is None and entry.stacktrace is None


@pytest.mark.parametrize("raw", [
    b"{", b"[]", b"{}", b"\xff",
    b'{"timestamp":"invalid","level":"INFO","service":"a","message":"b"}',
    b'{"timestamp":"2026-01-01T00:00:00","level":"INFO","service":"a","message":"b"}',
])
def test_parser_rejects_invalid_lines(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_line(LogLine("app.jsonl", 1, 0, raw, "identity", len(raw)))


@pytest.mark.parametrize(("changes", "category", "error_type"), [
    ({"message": "java.lang.NullPointerException: 找不到订单"}, Category.NULL_POINTER, "NullPointerException"),
    ({"stacktrace": "Traceback:\nAttributeError: 属性缺失"}, Category.NULL_POINTER, "AttributeError"),
    ({"level": "ERROR", "message": "内部故障"}, Category.UNKNOWN, "UNKNOWN"),
    ({"level": "ERROR", "message": "CustomException: 内部故障"}, Category.UNKNOWN, "CustomException"),
    ({"level": "WARN", "message": "Connection refused"}, Category.NETWORK, "UNKNOWN"),
])
def test_detector(changes: dict[str, str], category: Category, error_type: str) -> None:
    event = detect(parse_line(log_line(**changes)), "项目", "事件")
    assert event is not None
    assert event.error_category == category and event.error_type == error_type


@pytest.mark.parametrize("level", ["INFO", "WARN"])
def test_normal_log_is_not_an_error(level: str) -> None:
    assert detect(parse_line(log_line(level=level)), "项目", "事件") is None


@pytest.mark.parametrize(("error_type", "message", "category"), [
    ("SQLException", "", Category.DATABASE), ("UNKNOWN", "数据库连接失败", Category.DATABASE),
    ("ConnectionError", "", Category.NETWORK), ("TimeoutException", "", Category.TIMEOUT),
    ("PermissionError", "", Category.FILE_IO), ("MemoryError", "", Category.MEMORY),
    ("ClassCastException", "", Category.TYPE_ERROR), ("ValueError", "", Category.VALIDATION),
    ("KeyError", "", Category.UNKNOWN),
])
def test_classifier(error_type: str, message: str, category: Category) -> None:
    assert classify(error_type, message) == category


def test_fingerprint_is_conservative() -> None:
    frame = 'File "orders.py", line 5, in find'
    expected = fingerprint("项目", "服务", "ValueError", "User 1001 not found", frame)
    assert expected == fingerprint("项目", "服务", "ValueError", "User 1002 not found", frame)
    assert expected != fingerprint("项目", "服务", "KeyError", "User 1002 not found", frame)
    assert expected != fingerprint("项目", "服务", "ValueError", "User 1002 not found", frame.replace("5", "6"))
    assert expected != fingerprint("项目", "服务", "ValueError", "User 1002 found", frame)
    assert fingerprint("项目", "服务", "ValueError", "HTTP 404", frame) != fingerprint(
        "项目", "服务", "ValueError", "HTTP 500", frame,
    )


def test_scanner_empty_invalid_and_multiple(tmp_path: Path) -> None:
    assert not find_logs(tmp_path)
    with pytest.raises(FileNotFoundError):
        find_logs(tmp_path / "missing")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.jsonl").touch()
    (tmp_path / "b.jsonl").touch()
    assert find_logs(tmp_path, recursive=False) == (Path("b.jsonl"),)
    assert find_logs(tmp_path) == (Path("b.jsonl"), Path("nested/a.jsonl"))


def test_streaming_scan_bounds_line_size(tmp_path: Path) -> None:
    file = tmp_path / "app.jsonl"
    with file.open("wb") as stream:
        stream.write(b"{}\n")
        for _ in range(32):
            stream.write(b"a" * (MAX_LINE_BYTES // 8))
        stream.write(b"\n{}\n")
    scan = read_lines(tmp_path, Path(file.name))
    assert next(scan).raw == b"{}\n"
    large = next(scan)
    assert large.oversized and not large.raw
    final = next(scan)
    assert final.number == 3 and final.offset == 4 * MAX_LINE_BYTES + 4
    with pytest.raises(StopIteration):
        next(scan)


def test_file_open_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        next(read_lines(tmp_path, Path("gone.jsonl")))
