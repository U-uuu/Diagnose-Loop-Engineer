"""验证模型适配器、配置和故障分类。"""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from autoloop.config.settings import LLMSettings, llm_settings
from autoloop.runtime.llm import ModelError, OpenAICompatibleClient, ResponseFormatError


class Answer(BaseModel):
    summary: str


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> LLMSettings:
    monkeypatch.setattr("autoloop.runtime.llm.time.sleep", lambda _: None)
    return LLMSettings(
        provider="openai", model="测试模型", base_url="https://llm.example/v1",
        api_key="fixture-key", max_retries=2,
    )


def reply(content: str | None) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
    })


def test_structured_model_request(settings: LLMSettings) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fixture-key"
        data = json.loads(request.content)
        assert data["response_format"]["type"] == "json_schema"
        assert data["temperature"] == 0
        assert data["max_tokens"] == 128
        return reply('{"summary":"fixture-key 数据库连接异常"}')

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result = OpenAICompatibleClient(settings, http).generate(
            [], response_schema=Answer, temperature=0, max_tokens=128,
        )
    assert result.value.summary == "[已脱敏] 数据库连接异常"
    assert result.metadata.total_tokens == 16 and result.metadata.attempts == 1


@pytest.mark.parametrize(("status", "expected_attempts", "retryable"), [
    (401, 1, False), (403, 1, False), (404, 1, False), (429, 3, True), (500, 3, True),
])
def test_model_retry_bound(
    settings: LLMSettings, status: int, expected_attempts: int, retryable: bool,
) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": {"message": "fixture-key"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ModelError) as caught:
            OpenAICompatibleClient(settings, http).generate([])
    assert caught.value.retryable is retryable
    assert "fixture-key" not in str(caught.value)
    assert calls == expected_attempts


@pytest.mark.parametrize(("error", "message"), [
    (httpx.ReadTimeout, "超时"), (httpx.ConnectError, "无法连接"),
])
def test_network_failure(
    settings: LLMSettings, error: type[httpx.TransportError], message: str,
) -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        raise error("fixture-key")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ModelError, match=message) as caught:
            OpenAICompatibleClient(settings, http).generate([])
    assert caught.value.retryable


@pytest.mark.parametrize("content", [None, "", "非 JSON", "{}", '{"summary":42}'])
def test_invalid_response(settings: LLMSettings, content: str | None) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: reply(content))) as http:
        with pytest.raises(ResponseFormatError):
            OpenAICompatibleClient(settings, http).generate([], response_schema=Answer)


def test_response_format_fallback(settings: LLMSettings) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if "response_format" in json.loads(request.content):
            return httpx.Response(400, json={"error": {"param": "response_format"}})
        return reply('{"summary":"已完成"}')

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result = OpenAICompatibleClient(settings, http).generate([], response_schema=Answer)
    assert result.value.summary == "已完成"
    assert result.metadata.attempts == 2


def test_configuration_missing_key_and_env_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.setenv("LLM_MODEL", "测试模型")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        llm_settings()
    (tmp_path / ".env").write_text("LLM_API_KEY=fixture-key\nLLM_MODEL=本地模型\n", encoding="utf-8")
    assert llm_settings().model == "测试模型"
    assert "fixture-key" not in repr(llm_settings())


@pytest.mark.live_llm
def test_configured_live_model() -> None:
    settings = llm_settings()
    with httpx.Client() as http:
        response = OpenAICompatibleClient(settings, http).generate(
            [{"role": "user", "content": "请返回一个含 summary 字段的 JSON 对象。"}],
            response_schema=Answer,
        )
    assert response.value.summary.strip()
