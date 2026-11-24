"""解析本地数据库的数据目录。"""

import os
from pathlib import Path


def database_path() -> Path:
    default = Path.home() / ".autoloop" / "data"
    directory = Path(os.environ.get("DLE_DATA_DIR", str(default))).expanduser()
    return directory.resolve() / "incidents.sqlite3"
