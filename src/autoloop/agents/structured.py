"""统一 Agent 的结构化请求和有限格式重试。"""

import json
from typing import TypeVar

from pydantic import BaseModel

from autoloop.runtime.llm import LLMClient, Messages, ModelResponse, ResponseFormatError
from autoloop.schemas.diagnosis import ModelCall

T = TypeVar("T", bound=BaseModel)


def request(
    client: LLMClient, prompt: str, payload: dict[str, object], schema: type[T],
) -> tuple[T, ModelCall]:
    messages: Messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]
    response: ModelResponse[T]
    try:
        response = client.generate(messages, response_schema=schema)
    except ResponseFormatError as exc:
        messages.append({
            "role": "user",
            "content": "上次回答无法通过结构校验。请重新生成符合字段和类型约束的 JSON 对象。",
        })
        response = client.generate(messages, response_schema=schema)
        if exc.metadata is not None:
            first, second = exc.metadata, response.metadata
            counts = {}
            for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
                before, after = getattr(first, name), getattr(second, name)
                counts[name] = before + after if before is not None and after is not None else None
            return response.value, ModelCall(
                attempts=first.attempts + second.attempts,
                duration_seconds=first.duration_seconds + second.duration_seconds,
                **counts,
            )
    return response.value, response.metadata
