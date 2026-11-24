"""校验单行 JSONL 并补充可信的文件位置。"""

import json

from pydantic import ValidationError

from autoloop.discovery.log_scanner import LogLine
from autoloop.schemas.incident import LogEntry


def parse_line(line: LogLine) -> LogEntry:
    try:
        record = json.loads(line.raw.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("JSON 嵌套层级过深") from exc
    if not isinstance(record, dict):
        raise ValueError("日志必须是 JSON 对象")
    try:
        return LogEntry.model_validate({
            **record,
            "source_file": line.source_file,
            "source_line": line.number,
            "source_offset": line.offset,
        })
    except ValidationError as exc:
        fields = "、".join(str(issue["loc"][0]) for issue in exc.errors(include_input=False))
        raise ValueError(f"日志字段缺失或格式错误：{fields}") from exc
