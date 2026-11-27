"""遮盖模型输入与输出中常见的凭证。"""

import re

_PATTERNS = (
    (re.compile(r"(?i)(\bauthorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic)\s+)[^\s,\"';]+"), r"\1[已脱敏]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]{8,}"), r"\1 [已脱敏]"),
    (re.compile(r"""(?i)(["']?(?:[a-z0-9_-]*api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|client[_ -]?secret|secret|password|passwd|pwd|authorization|connection[_ -]?string|密码|密钥|令牌)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)"""), r"\1[已脱敏]"),
    (re.compile(r"(?i)\b(?:jdbc:)?[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@[^\s,;\"']+"), "[已脱敏的连接地址]"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{12,}|AKIA[A-Z0-9]{16})\b"), "[已脱敏]"),
)


def redact(text: str, secret: str = "") -> str:
    if secret:
        text = text.replace(secret, "[已脱敏]")
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
