# AutoLoop Engineer

本地项目诊断 CLI。M1 提供递归扫描和日志候选列表。

```powershell
uv sync
uv run autoloop --help
uv run autoloop scan ./examples/demo-project
uv run pytest
```

扫描识别 `.log` 和 `.jsonl` 文件，跳过链接以及常见版本控制、依赖和缓存目录。空结果会正常退出。路径无效或扫描遇到访问错误时，命令返回退出码 1。

架构与后续里程碑见 [总体架构](docs/architecture.md)、[模块设计](docs/module-design.md)、[工作流设计](docs/workflow-design.md)和[工程约束](docs/coding-standards.md)。
