"""根据异常类型和明确的故障关键词分类。"""

import re

from autoloop.schemas.incident import Category

RULES = (
    (Category.NULL_POINTER, {"NullPointerException", "AttributeError"}, None),
    (Category.DATABASE, {"SQLException"}, r"数据库连接|\bdatabase connection\b|\bsqlstate\b"),
    (Category.TIMEOUT, {"TimeoutException", "TimeoutError"}, r"\btimed out\b|\bconnection timeout\b|连接超时"),
    (Category.NETWORK, {"ConnectionError", "ConnectionRefusedError"}, r"\bconnection refused\b|\bconnection reset\b|连接被拒绝"),
    (Category.FILE_IO, {"IOException", "FileNotFoundError", "PermissionError"}, None),
    (Category.MEMORY, {"OutOfMemoryError", "MemoryError"}, None),
    (Category.TYPE_ERROR, {"TypeError", "ClassCastException"}, None),
    (Category.VALIDATION, {"IllegalArgumentException", "ValueError"}, None),
)

KNOWN_TYPES = frozenset({"IllegalStateException", "KeyError"} | {
    name for _, names, _ in RULES for name in names
})


def classify(error_type: str, message: str) -> Category:
    for category, names, _ in RULES:
        if error_type in names:
            return category
    for category, _, pattern in RULES:
        if pattern and re.search(pattern, message, re.IGNORECASE):
            return category
    return Category.UNKNOWN
