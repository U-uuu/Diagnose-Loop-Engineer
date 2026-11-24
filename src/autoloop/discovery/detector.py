"""从标准化日志提取故障事件。"""

import re

from autoloop.discovery.classifier import KNOWN_TYPES, classify
from autoloop.discovery.fingerprint import fingerprint
from autoloop.schemas.incident import Category, ErrorEvent, LogEntry, Severity

_EXCEPTION = re.compile(r"(?<!\w)([A-Z]\w*(?:Exception|Error))(?=\s*(?::|$|\b))", re.MULTILINE)


def detect(entry: LogEntry, project_id: str, event_id: str) -> ErrorEvent | None:
    level = entry.level.upper()
    message = entry.exception_message or entry.message
    error_type = (entry.exception_type or "").rsplit(".", 1)[-1]
    if not error_type:
        matches = list(_EXCEPTION.finditer(entry.stacktrace or ""))
        if not matches:
            matches = list(_EXCEPTION.finditer(message))
        if matches:
            match = matches[-1]
            if match.group(1) in KNOWN_TYPES or entry.stacktrace or level in {"ERROR", "CRITICAL", "FATAL"}:
                error_type = match.group(1)
                if not entry.exception_message and match.string == message:
                    message = message[match.end():].lstrip(": ") or message
    error_type = error_type or "UNKNOWN"
    category = classify(error_type, message)
    if (
        level not in {"ERROR", "CRITICAL", "FATAL"}
        and error_type == "UNKNOWN"
        and category == Category.UNKNOWN
    ):
        return None
    return ErrorEvent(
        event_id=event_id, project_id=project_id, timestamp=entry.timestamp,
        service=entry.service, error_type=error_type, error_message=message,
        error_category=category,
        severity=Severity.CRITICAL if level in {"CRITICAL", "FATAL"} else Severity.ERROR,
        stacktrace=entry.stacktrace,
        fingerprint=fingerprint(project_id, entry.service, error_type, message, entry.stacktrace),
        source_file=entry.source_file, source_line=entry.source_line, source_offset=entry.source_offset,
    )
