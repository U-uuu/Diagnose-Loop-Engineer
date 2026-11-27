# 模块设计

| 模块 | 输入 | 输出或职责 |
| --- | --- | --- |
| `cli/main.py` | 命令行参数 | Typer 命令注册和入口 |
| `cli/commands.py` | 项目路径 | Rich 扫描结果或退出码 1 |
| `application/services/scan.py` | Path | ScanResult 或 ScanError |
| `discovery/log_scanner.py` | 已验证的绝对目录 | 相对路径形式的常规日志文件 |
| `schemas/scan.py` | 根目录和候选文件 | Pydantic 扫描结果 |

候选扩展名为 .log 和 .jsonl，匹配忽略大小写。扫描只枚举文件元数据，跳过符号链接、Windows junction 和常见版本控制、依赖及缓存目录。遇到访问错误时，扫描返回明确的失败结果。

| 诊断模块 | 输入与职责 |
| --- | --- |
| `runtime/context.py` | 读取并选择发生记录，构建脱敏的 DiagnosticContext |
| `runtime/llm.py` | OpenAI 兼容 HTTP 请求、结构化解码、重试和调用统计 |
| `agents/diagnosis.py`、`agents/planning.py` | 两个独立模型角色，通过统一客户端生成诊断和计划 |
| `graph/` | 流程节点、校验路由及状态 |
| `storage/diagnosis_repository.py` | 持久化任务、证据、诊断、计划及历史查询 |
| `cli/diagnosis.py` | 组织诊断与查询命令的输出 |
