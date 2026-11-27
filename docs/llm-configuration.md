# 模型配置

模型配置只在执行 `dle diagnose` 时读取。进程环境变量优先于当前工作目录的 `.env`。可以复制 [配置模板](../.env.example) 后填写本地配置，并用 `git status` 确认真实凭证文件未被跟踪。

| 环境变量 | 含义 |
| --- | --- |
| `LLM_PROVIDER` | `deepseek`、`openai` 或 `compatible` |
| `LLM_MODEL` | 服务商接受的模型标识 |
| `LLM_BASE_URL` | API 基础地址，客户端追加 `/chat/completions` |
| `LLM_API_KEY` | 仅供鉴权请求头使用的密钥 |
| `LLM_TIMEOUT` | 每次调用的 HTTP 超时秒数，默认 60 |
| `LLM_MAX_RETRIES` | 临时错误的额外尝试次数，默认 3，上限 5 |
| `LLM_TEMPERATURE` | 采样温度，默认 0.1 |
| `LLM_MAX_TOKENS` | 输出 Token 上限，默认 2000 |
| `LLM_OUTPUT_MODE` | `auto`、`json_schema`、`json_object` 或 `text` |

DeepSeek 示例使用 `LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-chat`、`LLM_BASE_URL=https://api.deepseek.com`。切换到 OpenAI 时，将提供方改为 `openai`，地址改为 `https://api.openai.com/v1`，模型改为账户有权限的 Chat Completions 模型，并替换密钥。其他兼容服务使用 `compatible`。远程地址需要 HTTPS，本地回环模拟服务可用 HTTP。

自动模式下 OpenAI 优先使用 JSON Schema，其他提供方请求 JSON 对象。兼容服务明确拒绝格式参数时，自动模式可重试一次不带格式参数的请求，也可设置 `LLM_OUTPUT_MODE=text`。所有模式都执行本地 JSON 解析和 Pydantic 校验。若模型不支持当前请求所用的采样或输出参数，请使用接受这些参数的模型。

认证错误优先检查密钥和模型权限。限流、网络故障和部分服务端错误按有限次数退避。输出被截断时可以提高 `LLM_MAX_TOKENS`。使用 `dle diagnose <故障编号> --debug` 可查看失败节点、调用重试和堆栈位置，诊断日志只记录已知的安全细节。

运行 `uv run pytest -m live_llm` 单独验证已配置的真实模型。该测试发送固定的简短 JSON 请求，不读取项目日志。默认测试使用 HTTP 模拟并排除它。实际诊断会将脱敏后的证据发送到所配置的服务，建议先确认日志内容适合传递给该服务。
