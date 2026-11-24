"""生成保守、稳定的故障指纹。"""

import hashlib
import json
import re

_ENTITY_ID = re.compile(r"\b(user|order|request|用户|订单|请求)([ \t]+(?:id[=: ]+)?)[0-9]+\b", re.IGNORECASE)
_PYTHON_FRAME = re.compile(r'^\s*File "[^"]+", line \d+, in .+$', re.MULTILINE)
_JAVA_FRAME = re.compile(r"^\s*at\s+[\w.$]+\([^\n]+\)", re.MULTILINE)


def digest(*parts: str | int) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()


def fingerprint(
    project_id: str, service: str, error_type: str, message: str, stacktrace: str | None,
) -> str:
    normalized = _ENTITY_ID.sub(r"\1\2<编号>", message.strip())
    stack = stacktrace or ""
    frame = _PYTHON_FRAME.findall(stack)
    java = _JAVA_FRAME.search(stack)
    location = frame[-1].strip() if frame else java.group().strip() if java else stack.strip()
    return digest(project_id, service, error_type, normalized, location)
