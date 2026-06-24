---
name: build
description: 自动化代码生成流水线 — coder 生成 → reviewer 审查 → 自动修复循环
---

# /build — 自动化代码生成流水线

用法：`/build <需求描述> [--target-dir <目录>]`
续接：`/build --continue`

通过 `pipeline_engine` CLI 解析 `pipeline.yaml` 中的 DAG 定义，步进执行。

---

## 执行流程

### Phase 0: 初始化

1. 如果用户使用了 `--continue`：
   - 检测 `review-output/pipeline-state.json` 是否存在
   - 存在 → 直接进入 Phase 1 循环
   - 不存在 → 提示「没有可续接的流水线，请使用 /build <需求> 开始新的构建」
2. 解析用户输入中的 `--target-dir` 参数：
   - 如果用户指定了 `--target-dir <值>`，直接使用该值
   - 如果未指定，询问用户一次：
     「是否需要自定义代码输出目录？（当前默认: 项目根目录 src/main/java）
       输入模块目录名或直接回车跳过：」
     ├─ 用户输入了目录 → 使用该目录
     └─ 用户直接回车/说"不"/"否" → 使用默认值 "."
3. 调用：
   ```bash
   python3 -m pipeline_engine.cli start \
     --pipeline agents/scheduler/pipeline.yaml \
     --state-file review-output/pipeline-state.json \
     --target-dir "<目标目录>" \
     --requirement "{用户需求}"
   ```
4. 向用户报告启动信息（pipeline 名称、目标目录、max_retries 等）

### Phase 1: 执行循环

```
loop:
  1. 调用:
     python3 -m pipeline_engine.cli next \
       --pipeline agents/scheduler/pipeline.yaml \
       --state-file review-output/pipeline-state.json

  2. 解析返回 JSON:
     ┌──────────────────────────────────────────────────────┐
     │ action=="done"  → 退出循环，展示完成信息               │
     │ action=="error" → 退出循环，展示错误信息               │
     │ action=="execute" → 对 nodes 中的每个节点:            │
     │   a. 通过 Agent 工具启动子 Agent（subagent_type 使用  │
     │      节点返回的 agent_type）                          │
     │   b. prompt 使用节点返回的已渲染 prompt               │
     │   c. 超时参考节点返回的 timeout 字段                   │
     │   d. 等待子 Agent 完成，提取其最终回复                 │
     │   e. 判断 verdict（如回复中含 REVIEW_PASSED /          │
     │      REVIEW_FAILED / REVIEW_ERROR）                   │
     │   f. python3 -m pipeline_engine.cli report \         │
     │        --pipeline agents/scheduler/pipeline.yaml \   │
     │        --state-file review-output/pipeline-state.json\│
     │        --node {node_id} \                            │
     │        --status {success|failed|error} \              │
     │        --summary "{简要描述}" \                       │
     │        --verdict {REVIEW_PASSED|REVIEW_FAILED|REVIEW_ERROR|空} │
     │   g. 如果有多个 node → 可以并行启动（Agent 工具并发）   │
     └──────────────────────────────────────────────────────┘
  3. 回到步骤 1
```

### 终止条件

- `next` 返回 `action=="done"` → 从 `start` 命令返回的 `run_id` 构造路径，读取 `review-output/{run_id}/final-review-report.md` 展示结果
- `next` 返回 `action=="error"` → 展示错误信息，提示用户介入

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 提示「请输入需求描述，如：/build 实现用户登录功能」 |
| 需求模糊 | 追问 1-2 个澄清问题 |
| 调度器命令失败 | 检查 python3 和 PyYAML 是否可用，展示 stderr |
| `next` 返回 error | 展示 message，询问是否 reset 重来 |
| 用户 Ctrl+C | 状态文件保留，使用 `/build --continue` 续接 |
| 子 Agent 超时 | report status=error，让调度器决定下一步 |
| 子 Agent 未生成文件 | report status=failed（非 error），进入修复循环 |
