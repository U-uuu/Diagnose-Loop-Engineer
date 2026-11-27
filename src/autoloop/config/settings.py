"""解析本地数据库的数据目录。"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, HttpUrl, SecretStr, ValidationError, field_validator


def database_path() -> Path:
    default = Path.home() / ".autoloop" / "data"
    directory = Path(os.environ.get("DLE_DATA_DIR", str(default))).expanduser()
    return directory.resolve() / "incidents.sqlite3"


class LLMSettings(BaseModel):
    provider: Literal["deepseek", "openai", "compatible"]
    model: str = Field(min_length=1, max_length=200)
    base_url: HttpUrl
    api_key: SecretStr = Field(repr=False)
    timeout: float = Field(default=60, gt=0, le=300)
    max_retries: int = Field(default=3, ge=0, le=5)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=128, le=8192)
    output_mode: Literal["auto", "json_schema", "json_object", "text"] = "auto"

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, key: SecretStr) -> SecretStr:
        value = key.get_secret_value()
        if not value or not value.isascii() or not value.isprintable() or any(c.isspace() for c in value):
            raise ValueError("需要有效的模型密钥")
        return key

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, url: HttpUrl) -> HttpUrl:
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("模型地址不能包含凭证、查询参数或片段")
        if url.scheme != "https" and url.host not in {"localhost", "127.0.0.1", "[::1]"}:
            raise ValueError("模型地址应使用 HTTPS，本地测试可使用 HTTP")
        return url


def llm_settings() -> LLMSettings:
    names = {name: f"LLM_{name.upper()}" for name in LLMSettings.model_fields}
    file_values = dotenv_values(Path.cwd() / ".env", interpolate=False)
    values = {
        name: value.strip()
        for name, key in names.items()
        if (value := os.environ.get(key, file_values.get(key))) is not None
    }
    try:
        return LLMSettings.model_validate(values)
    except ValidationError as exc:
        fields = "、".join(names[str(item["loc"][0])] for item in exc.errors(include_input=False))
        raise ValueError(f"模型配置缺失或无效，请检查 {fields}") from None


class ContextLimits(BaseModel):
    occurrences: int = Field(default=6, ge=2, le=20)
    evidence: int = Field(default=8, ge=2, le=20)
    sample_size: int = Field(default=60, ge=2, le=200)
    stack_chars: int = Field(default=1400, ge=100, le=8000)
    text_chars: int = Field(default=420, ge=50, le=1500)
    context_bytes: int = Field(default=12000, ge=2400, le=48000)
