"""项目扫描应用服务。"""

from pathlib import Path
from stat import S_ISDIR

from autoloop.discovery.log_scanner import find_logs
from autoloop.schemas.scan import ScanResult


class ScanError(Exception):
    """项目目录扫描失败。"""


def scan_project(path: Path) -> ScanResult:
    try:
        root = path.resolve(strict=True)
        if not S_ISDIR(root.stat().st_mode):
            raise ScanError(f"指定路径不是项目目录：{path}")
        logs = find_logs(root)
    except FileNotFoundError as exc:
        raise ScanError(f"扫描时找不到路径：{exc.filename or path}") from exc
    except (OSError, RuntimeError) as exc:
        raise ScanError(f"无法扫描 {path}。详细原因：{exc}") from exc

    return ScanResult(project_root=root, log_files=logs)
