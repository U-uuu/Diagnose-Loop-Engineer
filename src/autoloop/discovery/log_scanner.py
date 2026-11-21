"""以只读方式查找候选日志文件。"""

from os import scandir
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISDIR, S_ISREG

LOG_SUFFIXES = {".log", ".jsonl"}
IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache",
}


def find_logs(root: Path) -> tuple[Path, ...]:
    pending = [root]
    logs = []
    while pending:
        directory = pending.pop()
        with scandir(directory) as entries:
            for entry in entries:
                metadata = entry.stat(follow_symlinks=False)
                if getattr(metadata, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                path = Path(entry.path)
                if S_ISDIR(metadata.st_mode) and entry.name.lower() not in IGNORED_DIRECTORIES:
                    pending.append(path)
                elif S_ISREG(metadata.st_mode) and path.suffix.lower() in LOG_SUFFIXES:
                    logs.append(path.relative_to(root))
    return tuple(sorted(logs, key=Path.as_posix))
