"""项目扫描的结果模型。"""

from pathlib import Path

from pydantic import BaseModel


class ScanResult(BaseModel):
    project_root: Path
    log_files: tuple[Path, ...]
