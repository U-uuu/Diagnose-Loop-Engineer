# 总体架构

M1 的调用链为 CLI → Application → Discovery。CLI 解析路径、负责 Rich 输出并将业务错误转换为退出码。Application 校验扫描根目录并组织扫描。Discovery 枚举日志候选。Schemas 持有各层共享的数据契约。

未来由 Application 组装 LangGraph 工作流、统一模型客户端和持久化适配器。Graph 协调角色和确定性节点。Agent 依赖注入的模型接口与数据契约。工具负责文件、Git 和测试执行，持久化由基础设施实现。

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

M1 的实现位于 `cli/`、`application/services/`、`discovery/` 和 `schemas/`。M2 将在 Discovery 中加入日志解析与 Incident 归类，在 Storage 和 Infrastructure 中加入持久化。M3 在 Agents、Graph、Runtime 和 Config 中加入模型角色及编排。Tools 留给 M4–M5 的文件、Git 与测试执行。

第四节列出的后续模块已建立文件骨架，目前以模块文档字符串说明职责，具体行为随各阶段实现。执行产物位于 `data/executions/`，由 Git 忽略。
