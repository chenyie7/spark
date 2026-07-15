---
name: build
description: 自动化代码生成流水线 — PM 需求沟通 → coder 生成 → reviewer 审查 → 自动修复循环
---

# /build — 自动化代码生成流水线

用法：`/build <需求描述> [--base-path <目录>] [--project-name <名称>]`
恢复开发：`/build --resume <run_id>`
恢复需求对话：`/build --pm <run_id>`

PM 阶段（需求对话）在主线运行，用户交互完成后自动衔接 pipeline_engine 管理的 coder → reviewer 阶段。

---

## 入口判断

```
/build 调用
  │
  ├── --resume <run_id>  → 跳过 PM，进入「Phase 2: Coder/Reviewer 自动流水线」
  │
  ├── --pm <run_id>      → 恢复 PM 需求对话（继续未完成的 PM 阶段）
  │
  ├── 有需求描述          → 「Phase 1: PM 需求对话」
  │     └── PM 完成 → 提示用户运行 --resume → Phase 2
  │
  └── 无参数              → 提示用户描述需求
        └── 用户回复需求 → 「Phase 1: PM 需求对话」
              └── PM 完成 → 提示用户运行 --resume → Phase 2
```

---

## Phase 1: PM 需求对话

**触发条件:** `/build "需求"` 或 `/build`（无参数，用户后续输入需求后自动触发）

1. 调用 pipeline-engine start 获取 run_id（唯一生成入口）：

   ```bash
   result=$(PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
   python3 -m pipeline_engine.cli start \
     --pipeline agents/scheduler/pipeline.yaml \
     --state-file review-output/.pipeline-state.tmp \
     --base-path "{base_path}" \
     --project-name "{project_name}" \
     --requirement "placeholder")

   run_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
   ```

   然后将临时状态文件移至最终位置：

   ```bash
   mkdir -p "review-output/${run_id}"
   mv review-output/.pipeline-state.tmp "review-output/${run_id}/pipeline-state.json"
   ```

2. 写入 `review-output/{run_id}/pm-context.json`：
   ```json
   {
     "run_id": "{run_id}",
     "status": "in_progress",
     "base_path": "{base_path}",
     "project_name": "{project_name}",
     "output_dir": "{base_path}/{project_name}/",
     "requirement": "{用户原始需求}",
     "spec_file": "",
     "plan_file": ""
   }
   ```
4. 加载 PM Agent 流程（参考 agents/pm/pm.skill.md），以用户需求为起点进行对话：
   - 探索项目上下文（现有代码、CLAUDE.md、agents/coder/ 规范、已有设计文档）
   - 逐轮澄清需求（一次只问一个问题、优先多选、YAGNI）
   - 提出 2-3 种方案对比
   - 逐节确认设计（架构 → 数据模型 → API → 数据流 → 错误处理 → 测试）
   - 输出 spec: `{output_dir}/docs/specs/YYYY-MM-DD-<topic>-design.md`
   - spec 自检（placeholder、矛盾、歧义、范围）
   - 用户 review spec → 修改或确认
   - 输出 plan: `{output_dir}/docs/plans/YYYY-MM-DD-<topic>-plan.md`
   - plan 自检（spec 覆盖、placeholder、类型一致性）
5. 更新 `pm-context.json`：status → "done"，记录 spec_file 和 plan_file 绝对路径
6. **简明提示当前阶段完成，下一阶段需要的命令：**

   ```
   需求梳理完毕。
   spec: {output_dir}/docs/specs/<文件名>.md
   plan: {output_dir}/docs/plans/<文件名>.md
   
   运行 /build --resume {run_id} 开始开发
   ```

7. 等待用户输入恢复命令

---

## Phase 2: Coder / Reviewer 自动流水线

**触发条件:** `/build --resume <run_id>`

### 步骤 2.1: 准备

从 `review-output/{run_id}/pm-context.json` 读取 spec_file、plan_file、base_path、project_name、output_dir、原始需求。

### 步骤 2.2: 激活流水线保护

确认状态文件存在：

```bash
if [ ! -f "review-output/{run_id}/pipeline-state.json" ]; then
    echo "错误: 未找到流水线状态文件。请先运行 /build <需求> 完成 Phase 1。"
    exit 1
fi
```

在进入执行循环前，创建标记文件和上下文文件：

```bash
# 激活 hook（PreToolUse/PostToolUse/Stop 开始生效）
touch .pipeline-active

# 写入当前 run 上下文，Agent 启动时读取
cat > review-output/.current-run <<EOF
{
  "run_id": "{run_id}",
  "base_path": "{base_path}",
  "project_name": "{project_name}",
  "output_dir": "{base_path}/{project_name}/",
  "scan_path": "{base_path}/{project_name}/src/main/java",
  "review_dir": "{base_path}/review-output/{project_name}/{run_id}/"
}
EOF
```

### 步骤 2.3: 立即进入执行循环

**以下步骤必须连续执行，直到 `next` 返回 `done` 或 `error`：**

**第 1 步：获取下一个任务**

运行 pipeline_engine next：

```bash
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli next \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/{run_id}/pipeline-state.json
```

**第 2 步：根据返回 JSON 的 `action` 字段分流**

- `action == "done"` → 读取 `review-output/{run_id}/final-review-report.md` 展示结果。流水线完成。
- `action == "error"` → 展示 `message` 内容，提示用户介入。
- `action == "execute"` → **继续执行第 3 步。**

**第 3 步：启动子 Agent（对 `nodes` 数组中的每个节点）**

对返回 JSON 中 `nodes` 数组的每一项，执行以下子步骤：

a. 使用 Agent 工具启动子 Agent：
   - `subagent_type` 使用节点返回的 `agent_type`
   - `prompt` 使用节点返回的已渲染 `prompt`
   - `mode` 使用节点返回的 `mode` 值
   - 超时参考节点返回的 `timeout`

b. 等待子 Agent 完成，提取最终回复

c. 判断 verdict：
   - 回复含 `REVIEW_PASSED` / `REVIEW_FAILED` / `REVIEW_ERROR` → 提取为 verdict
   - 非 reviewer 节点 → verdict 留空

d. 向 pipeline_engine 报告结果：

```bash
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli report \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/{run_id}/pipeline-state.json \
  --node {node_id} \
  --status {success|failed|error} \
  --summary "{简要描述}" \
  --verdict {REVIEW_PASSED|REVIEW_FAILED|REVIEW_ERROR|空}
```

**如果有多个 node → 并行启动（Agent 工具并发调用）**

**第 4 步：回到第 1 步**

循环直到 `action` 为 `done` 或 `error`。

---

## Phase 0: 参数解析

`--base-path` 参数解析：
- 如果用户指定了 `--base-path <值>`，直接使用该值
- 如果未指定，使用 pipeline.yaml defaults 中的 base_path（默认 "."）

`--project-name` 参数解析：
- 如果用户指定了 `--project-name <值>`，直接使用该值
- 如果未指定 → **必须交互询问用户**（不可跳过）：
  - 「请输入项目名称：」
  - 用户输入为空 → 再次询问，不允许跳过

拼接确认：
- 展示所有路径给用户确认后才进入 PM 阶段：
  「确认：
    - 项目位置：{base_path}/
    - 项目名称：{project_name}
    - 代码输出：{base_path}/{project_name}/src/main/java/
    - 审查数据：{base_path}/review-output/{project_name}/
    
    是否继续？」
  - 用户否定 → 重新输入参数

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 「请描述你要构建的需求，我会和你讨论具体内容后开始开发。」 |
| PM 阶段用户中断 | pm-context.json 保留，`/build --pm <run_id>` 恢复 |
| `/build --resume` 无状态 | 「没有可续接的流水线，请使用 /build <需求> 开始新的构建」 |
| pipeline_engine 命令失败 | 检查 python3 和 PyYAML 是否可用，展示 stderr |
| `next` 返回 error | 展示 message，询问是否 reset 重来 |
| 子 Agent 超时 | report status=error，让调度器决定下一步 |
| 子 Agent 未生成文件 | report status=failed（非 error），进入修复循环 |
