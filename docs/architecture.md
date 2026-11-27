# 总体架构

M1 的调用链为 CLI → Application → Discovery。CLI 解析路径、负责 Rich 输出并将业务错误转换为退出码。Application 校验扫描根目录并组织扫描。Discovery 枚举日志候选。Schemas 持有各层共享的数据契约。

M3 由应用层调用 Runtime，Runtime 组装 LangGraph、统一模型客户端及仓储。Graph 协调上下文构建、诊断、规划、验证与持久化。Agent 依赖注入的模型接口和共享数据契约。

## 目录结构

```text
.
├── docs/
├── src/autoloop/
│   ├── cli/
│   ├── application/services/
│   ├── agents/
│   ├── graph/
│   ├── runtime/
│   ├── tools/
│   ├── discovery/
│   ├── storage/
│   ├── schemas/
│   ├── infrastructure/persistence/
│   └── config/
├── tests/
│   ├── unit/
│   └── integration/
├── examples/demo-project/
└── data/executions/
```

M1 的实现位于 `cli/`、`application/services/`、`discovery/` 和 `schemas/`。M2 在发现层实现日志解析、故障分类与聚合，在 `storage/` 实现 SQLite 持久化，由应用层统一协调事务。M3 复用同一数据库保存诊断历史、证据快照和修复建议。Tools 留给 M4–M5 的文件、Git 与测试执行。

M4 及以后预留的模块以文档字符串说明职责。M2 和 M3 的运行数据使用配置目录下的同一 SQLite 数据库。
