"""统一模型接口与 OpenAI 兼容的同步 HTTP 适配器。"""

from collections.abc import Sequence
from dataclasses import dataclass
import json
import logging
import time
from typing import Generic, Literal, Protocol, TypedDict, TypeVar, overload

import httpx
from pydantic import BaseModel

from autoloop.config.settings import LLMSettings
from autoloop.runtime.redaction import redact
from autoloop.schemas.diagnosis import ModelCall

logger = logging.getLogger(__name__)
T = TypeVar("T")


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


Messages = list[Message]


class ModelError(ValueError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ResponseFormatError(ModelError):
    """模型内容无法通过结构检查。"""

    def __init__(self, message: str, metadata: ModelCall | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata


@dataclass(frozen=True)
class ModelResponse(Generic[T]):
    value: T
    metadata: ModelCall


class LLMClient(Protocol):
    @overload
    def generate(
        self, messages: Sequence[Message], *, response_schema: type[T],
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> ModelResponse[T]: ...

    @overload
    def generate(
        self, messages: Sequence[Message], *, response_schema: None = None,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> ModelResponse[str]: ...


def _scrub(value: object, secret: str) -> object:
    if isinstance(value, str):
        return redact(value, secret)
    if isinstance(value, list):
        return [_scrub(item, secret) for item in value]
    if isinstance(value, dict):
        return {name: _scrub(item, secret) for name, item in value.items()}
    return value


class OpenAICompatibleClient:
    def __init__(self, settings: LLMSettings, http: httpx.Client) -> None:
        self.settings = settings
        self.http = http

    def _send(self, body: dict[str, object]) -> tuple[httpx.Response, int]:
        settings = self.settings
        url = str(settings.base_url).rstrip("/") + "/chat/completions"
        for attempt in range(settings.max_retries + 1):
            try:
                response = self.http.post(
                    url, json=body,
                    headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
                    timeout=settings.timeout, follow_redirects=False,
                )
            except httpx.TimeoutException:
                error = ModelError("模型请求超时", retryable=True)
            except httpx.TransportError:
                error = ModelError("无法连接模型服务", retryable=True)
            else:
                status = response.status_code
                if status not in {408, 429, 500, 502, 503, 504}:
                    return response, attempt + 1
                reason = "模型服务限流" if status == 429 else f"模型服务暂时不可用（HTTP {status}）"
                error = ModelError(reason, retryable=True)
            if attempt >= settings.max_retries:
                raise error from None
            logger.debug("模型调用将重试，第 %s 次请求失败：%s", attempt + 1, error)
            time.sleep(min(0.25 * 2**attempt, 2))
        raise AssertionError("模型请求次数超出配置范围")

    @overload
    def generate(
        self, messages: Sequence[Message], *, response_schema: type[T],
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> ModelResponse[T]: ...

    @overload
    def generate(
        self, messages: Sequence[Message], *, response_schema: None = None,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> ModelResponse[str]: ...

    def generate(
        self, messages: Sequence[Message], *, response_schema: type[BaseModel] | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> ModelResponse[BaseModel | str]:
        settings = self.settings
        started = time.monotonic()
        body: dict[str, object] = {
            "model": settings.model, "messages": list(messages),
            "temperature": settings.temperature if temperature is None else temperature,
            "max_tokens": settings.max_tokens if max_tokens is None else max_tokens,
        }
        mode = settings.output_mode
        if mode == "auto":
            mode = "json_schema" if settings.provider == "openai" else "json_object"
        if response_schema is not None:
            schema = response_schema.model_json_schema()
            body["messages"] = [
                {"role": "system", "content": "仅返回符合此 JSON Schema 的 JSON 对象：" + json.dumps(schema, ensure_ascii=False)},
                *messages,
            ]
            if mode == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": response_schema.__name__, "schema": schema},
                }
            elif mode == "json_object":
                body["response_format"] = {"type": "json_object"}

        response, attempts = self._send(body)
        if (
            settings.output_mode == "auto" and "response_format" in body
            and response.status_code in {400, 422}
            and "response_format" in response.text[:4000].lower()
        ):
            del body["response_format"]
            response, fallback_attempts = self._send(body)
            attempts += fallback_attempts
        if response.status_code in {401, 403}:
            raise ModelError("模型授权失败，请检查 API Key 和模型权限")
        if not response.is_success:
            raise ModelError(f"模型服务拒绝请求（HTTP {response.status_code}），请检查模型和地址配置")
        metadata = ModelCall(attempts=attempts, duration_seconds=time.monotonic() - started)
        try:
            payload = response.json()
            usage = payload.get("usage")
            if isinstance(usage, dict):
                for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    count = usage.get(field)
                    if type(count) is int and count >= 0:
                        setattr(metadata, field, count)
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise ResponseFormatError("模型输出被截断，可提高 LLM_MAX_TOKENS", metadata)
            if not isinstance(content, str) or not content.strip():
                raise ResponseFormatError("模型返回内容为空或格式不受支持", metadata)
            key = settings.api_key.get_secret_value()
            if response_schema is not None:
                parsed = json.loads(content)
                result = response_schema.model_validate(_scrub(parsed, key))
            else:
                result = redact(content, key)
        except ResponseFormatError:
            raise
        except (KeyError, IndexError, TypeError, AttributeError, ValueError, RecursionError):
            raise ResponseFormatError("模型响应不符合预期的 JSON 结构", metadata) from None
        return ModelResponse(result, metadata)
