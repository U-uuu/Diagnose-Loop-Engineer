# AutoLoop Engineer

本地项目诊断 CLI。M1 提供日志候选列表，M2 从本地 JSONL 日志发现和管理故障。

```powershell
uv sync
uv run autoloop --help
uv run autoloop scan ./examples/demo-project
uv run pytest
```

扫描识别 `.log` 和 `.jsonl` 文件，跳过链接以及常见版本控制、依赖和缓存目录。空结果会正常退出。路径无效或扫描遇到访问错误时，命令返回退出码 1。

## 第二阶段

```powershell
uv run dle scan ./examples/demo-logs
uv run dle incidents list
uv run dle scan history
```

示例含故意损坏的日志行，扫描状态为部分完成。可用故障列表中的编号查询详情和原始记录，也可以将故障标记为已解决。持久化使用本地 SQLite，可通过 `DLE_DATA_DIR` 设置数据目录。

详见[命令行使用](docs/cli-usage.md)、[故障发现](docs/discovery-design.md)、[故障事件管理](docs/incident-design.md)和[数据库设计](docs/database-design.md)。

架构与后续里程碑见 [总体架构](docs/architecture.md)、[模块设计](docs/module-design.md)、[工作流设计](docs/workflow-design.md)和[工程约束](docs/coding-standards.md)。

## 第三阶段

按[模型配置](docs/llm-configuration.md)设置连接后，从故障列表复制实际编号。将下列占位符替换为故障编号或诊断编号。

```powershell
uv run dle diagnose <故障编号>
uv run dle diagnosis history <故障编号>
uv run dle diagnosis show <诊断编号>
uv run dle diagnosis plan <诊断编号>
```

诊断读取并脱敏本地证据，输出根因假设和待审查的修复建议。SQLite 保留每次诊断的状态、结果和计划。详见[诊断工作流](docs/diagnosis-workflow.md)。

运行 `uv run pytest` 可使用 HTTP 模拟验证完整流程。配置真实模型后，可单独运行 `uv run pytest -m live_llm`。
