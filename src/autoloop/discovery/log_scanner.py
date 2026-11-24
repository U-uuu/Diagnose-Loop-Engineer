"""以只读方式查找候选日志文件。"""

from collections.abc import Iterator
from dataclasses import dataclass
from os import fstat, scandir
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISDIR, S_ISREG

LOG_SUFFIXES = {".log", ".jsonl"}
IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache",
}


def find_logs(
    root: Path, *, recursive: bool = True,
    suffixes: set[str] = LOG_SUFFIXES, issues: list[OSError] | None = None,
) -> tuple[Path, ...]:
    pending = [root]
    logs = []
    while pending:
        directory = pending.pop()
        try:
            if directory.resolve(strict=True) != directory:
                raise OSError("目录链接已变更", None, str(directory))
            with scandir(directory) as entries:
                for entry in entries:
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        if issues is None:
                            raise
                        issues.append(exc)
                        continue
                    if getattr(metadata, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                        continue
                    path = Path(entry.path)
                    if recursive and S_ISDIR(metadata.st_mode) and entry.name.lower() not in IGNORED_DIRECTORIES:
                        pending.append(path)
                    elif S_ISREG(metadata.st_mode) and path.suffix.lower() in suffixes:
                        logs.append(path.relative_to(root))
        except OSError as exc:
            if issues is None:
                raise
            issues.append(exc)
    return tuple(sorted(logs, key=Path.as_posix))


MAX_LINE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class LogLine:
    source_file: str
    number: int
    offset: int
    raw: bytes
    file_identity: str
    end_offset: int
    oversized: bool = False


def read_lines(root: Path, relative: Path) -> Iterator[LogLine]:
    path = root / relative
    if path.resolve(strict=True) != path or not path.is_file():
        raise OSError("日志路径已变更", None, str(path))
    expected = path.stat()
    with path.open("rb") as stream:
        initial = fstat(stream.fileno())
        if (initial.st_dev, initial.st_ino) != (expected.st_dev, expected.st_ino):
            raise OSError("打开日志时文件身份已变更", None, str(path))
        identity = (
            f"{initial.st_dev}:{initial.st_ino}:{getattr(initial, 'st_birthtime_ns', 0)}"
            if initial.st_ino else relative.as_posix()
        )
        number = 0
        while (offset := stream.tell()) < initial.st_size:
            raw = stream.readline(min(MAX_LINE_BYTES + 1, initial.st_size - offset))
            if not raw:
                break
            number += 1
            oversized = len(raw) > MAX_LINE_BYTES
            tail = raw
            while not tail.endswith(b"\n") and stream.tell() < initial.st_size:
                tail = stream.readline(min(MAX_LINE_BYTES + 1, initial.st_size - stream.tell()))
                if not tail:
                    break
            yield LogLine(
                relative.as_posix(), number, offset, b"" if oversized else raw,
                identity, stream.tell(), oversized,
            )
        current = path.stat()
        if (
            path.resolve(strict=True) != path or current.st_ino != initial.st_ino
            or current.st_dev != initial.st_dev or current.st_size != initial.st_size
            or current.st_mtime_ns != initial.st_mtime_ns
        ):
            raise OSError("扫描期间日志发生变更，请重新扫描", None, str(path))
