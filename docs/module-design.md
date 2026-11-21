# 模块设计

| 模块 | 输入 | 输出或职责 |
| --- | --- | --- |
| `cli/main.py` | 命令行参数 | Typer 命令注册和入口 |
| `cli/commands.py` | 项目路径 | Rich 扫描结果或退出码 1 |
| `application/services/scan.py` | Path | ScanResult 或 ScanError |
| `discovery/log_scanner.py` | 已验证的绝对目录 | 相对路径形式的常规日志文件 |
| `schemas/scan.py` | 根目录和候选文件 | Pydantic 扫描结果 |

候选扩展名为 .log 和 .jsonl，匹配忽略大小写。扫描只枚举文件元数据，跳过符号链接、Windows junction 和常见版本控制、依赖及缓存目录。遇到访问错误时，扫描返回明确的失败结果。
