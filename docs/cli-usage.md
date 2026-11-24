# 命令行使用

```powershell
uv sync
uv run autoloop scan ./examples/demo-project
uv run dle scan ./examples/demo-logs
uv run dle scan ./examples/demo-logs --logs ./examples/demo-logs --recursive --format json
uv run dle incidents list --status OPEN --category DATABASE --severity ERROR --limit 20 --offset 0
uv run dle incidents show <故障编号>
uv run dle incidents occurrences <故障编号> --limit 20 --offset 0
uv run dle incidents resolve <故障编号>
uv run dle incidents status <故障编号> IN_PROGRESS
uv run dle incidents reopen <故障编号>
uv run dle incidents stats
uv run dle scan history
uv run dle scan issues <扫描编号>
uv run pytest
```

将占位编号换成列表里实际输出的编号。`dle scan <项目路径>` 扫描项目根目录或约定的 `logs/`；`--logs` 指向项目内的日志目录。`dle scan run --help` 显示扫描参数。正常结束返回 0，扫描失败返回 1，部分完成返回 2。命令行参数错误也由 Typer 返回 2。示例含两行故意损坏的日志，因此示例扫描预期返回 2，正常日志中的故障依然可以查询。

JSON 格式在标准输出写入单个摘要对象。文字格式的进度写入标准错误，统计写入标准输出。可通过环境变量 `DLE_DATA_DIR` 为不同运行指定独立数据库目录。
