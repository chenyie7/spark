---
name: build
description: 自动化代码生成流水线 — coder 生成 → reviewer 审查 → 自动修复循环
---

# /build — 自动化代码生成流水线

用法：`/build <需求描述>`

读取 `agents/scheduler/pipeline.yaml` 获取 DAG 定义，按 coder → reviewer → fix 循环执行，直到 P0 清零或达到最大轮次。

---

## 执行流程

### Phase 0: 初始化

1. 读取 `agents/scheduler/pipeline.yaml`，解析 `nodes` 和 `edges`。
2. 从 YAML 中提取 `defaults.max_retries`（默认 3）和 `defaults.block_on`（默认 [P0]）。
3. 初始化 `round = 0`，`review_context = ""`（首轮无审查上下文）。
4. 如果用户输入为空或不明确（如「做个系统」），追问澄清后再启动。

向用户报告：
```
🚀 启动流水线：coder → reviewer
最大修复轮次：{max_retries}  |  阻断级别：{block_on}
需求：{user_input}
```

### Phase 1: coder — 代码生成

1. 构造 coder Agent 的 prompt：将 `pipeline.yaml` 中 `coder.prompt_template` 的 `{requirement}` 替换为用户需求，`{review_context}` 替换为当前轮的审查上下文。
   - 首轮（round=0）：`review_context` 为空字符串。
   - 修复轮（round≥1）：`review_context` = 「以下是上一轮审查发现的问题，请逐个修复：」+ `review-output/review-result.json` 的内容摘要 + `review-output/pre-check-report.md` 的内容。
2. 通过 `Agent` 工具启动 coder 子 Agent，subagent_type 使用 `general-purpose`。
3. 等待 coder 完成。

**异常处理：**
- coder 未生成任何 `.java` 文件 → 告知用户「未生成代码文件，流水线终止」，停止。
- coder 超时（defaults.timeout 或节点 timeout） → 告知用户「代码生成超时」，停止。

### Phase 2: reviewer — 双层审查

1. 构造 reviewer Agent 的 prompt：使用 `pipeline.yaml` 中 `reviewer.prompt_template`，`{coder_output}` 替换为 `src/main/java`。
2. 通过 `Agent` 工具启动 reviewer 子 Agent，subagent_type 使用 `general-purpose`。
3. reviewer Agent 需执行：
   - **Layer 1**：`cd agents/reviewer/check_system && python3 -m code_check.cli scan ../../../src/main/java`
     - exit 1 → 预检未通过，输出 `review-output/pre-check-report.md`
     - exit 0 → 预检通过，继续 Layer 2
   - **Layer 2**：读取 `ai-checklist.yaml` 和 `pre-check-result.json`，逐项检查，输出 `review-output/review-result.json`
   - **合并报告**：`python3 -m code_check.cli report --pre ... --ai ... --output review-output/final-review-report.md`

**异常处理：**
- `python3` 命令不可用 → 告知用户「需要 Python 3 环境」，停止。
- `pre-check-result.json` 未生成 → 降级：跳过 Layer 1 结果，只执行 Layer 2 AI 检查。
- `review-result.json` 未生成 → 降级：展示 pre-check 结果，无法进入修复循环，停止。
- reviewer 超时 → 保留上一轮产物，告知用户「审查超时」，停止。

### Phase 3: 判定 — 检查 P0 数量

读取 `review-output/pre-check-result.json`，提取 P0 数量：

```json
// pre-check-result.json 的结构
{
  "summary": {
    "p0_count": <int>,
    "p1_count": <int>,
    "p2_count": <int>
  }
}
```

**判定逻辑：**

1. 如果 `p0_count == 0`：
   - ✅ 流水线成功！展示 `review-output/final-review-report.md` 内容给用户。
   - 报告：「流水线完成，P0=0。经过 {round} 轮修复。」

2. 如果 `p0_count > 0` 且 `round < max_retries`：
   - round++，报告：「第 {round}/{max_retries} 轮：P0={p0_count}, P1={p1_count}，回到 coder 修复…」
   - 构造 review_context（格式化 P0 问题列表 + 文件位置）。
   - 回到 Phase 1（coder 修复模式）。

3. 如果 `p0_count > 0` 且 `round >= max_retries`：
   - ❌ 超出最大轮次。展示 `review-output/final-review-report.md`。
   - 报告：「已达最大轮次 {max_retries}，剩余 P0={p0_count}, P1={p1_count}，请手动介入修复。」

### Phase 4（仅修复轮次）: coder 修复

修复轮的 coder prompt 不同：除了用户需求，还包括上一轮的 P0 问题详情。coder Agent 需要：
1. 读取 `review-output/review-result.json` 获取每个问题的文件路径、行号、规则编码、描述
2. 逐个修复 P0 问题
3. 不修改与问题无关的代码
4. 修复后重新写入对应文件

**异常处理：**
- coder 修复后 P0 数量不降反增 → 不自动终止，让循环继续。可能下一轮会降下来。
- coder 修复后 P0 不变 → 继续循环，不特殊处理。

---

## 与 coder / reviewer 的集成

### 启动 coder 子 Agent

```
Agent(
  subagent_type: "general-purpose",
  description: "coder — 生成/修复 Java 代码",
  prompt: <构造好的 coder prompt，包含用户需求和可选的审查上下文>
)
```

coder 子 Agent 会自动读取 `agents/coder/README.md` 获取规范索引。

### 启动 reviewer 子 Agent

```
Agent(
  subagent_type: "general-purpose",
  description: "reviewer — 双层代码审查",
  prompt: <构造好的 reviewer prompt，指定扫描 src/main/java>
)
```

reviewer 子 Agent 会按 `agents/reviewer/review.skill.md` 的流程执行审查。

---

## 进度报告格式

每轮结束后，调度 Agent 向用户报告：

```
📊 第 {round}/{max_retries} 轮完成
   P0: {p0_count}  P1: {p1_count}  P2: {p2_count}
   ➡️ {下一步动作：修复 / 完成 / 超限}
```

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 提示「请输入需求描述，如：/build 实现用户登录功能」 |
| 需求模糊 | 追问 1-2 个澄清问题 |
| coder 未生成文件 | 停止流水线，提示「未生成 Java 文件」 |
| coder 生成不可编译代码 | 不阻断，推进到 reviewer。结构性问题通过循环回边修复 |
| python3 不可用 | 停止流水线，提示「需要 Python 3」 |
| pre-check-result.json 缺失 | 降级为 Layer 2 only |
| review-result.json 缺失 | 降级展示 pre-check 结果，停止循环 |
| coder 超时 (900s) | 停止，提示超时 |
| reviewer 超时 (600s) | 停止，保留产物 |
| max_retries 耗尽 | 展示最终报告，提示用户手动介入 |
| 用户 Ctrl+C | 保留产物，展示已完成轮次 |
