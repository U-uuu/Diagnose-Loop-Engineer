# 工作流设计

M1 的扫描流程为解析参数 → 校验根目录 → 遍历候选 → 展示结果。

后续 LangGraph 主链为 Discovery → Incident → Diagnosis → Planning → Coding → Review → Testing → Human Gate → Report。M2 已将本地日志解析为可查询的 Incident。M3 将通过统一模型客户端输出结构化诊断和计划。

M4 在验证 Git 状态后使用独立修复分支，记录修改和 diff，并由独立角色给出审查结论。M5 从实际命令退出码和输出构建测试结果。高风险操作前需要审批。审查失败、测试失败或人工拒绝均应生成带对应状态的报告。
