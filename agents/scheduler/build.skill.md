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

1. 读取 `agents/scheduler/pipeline.yaml`，解析 `nodes`（获取 coder/reviewer 的 prompt 模板和超时配置）和 `defaults`（获取 max_retries、block_on 等全局参数）。
2. 从 YAML 中提取 `defaults.max_retries`（默认 3）和 `defaults.block_on`（默认 [P0]）。
3. 初始化 `round = 0`。
4. 如果用户输入为空或不明确（如「做个系统」），追问澄清后再启动。

向用户报告：
```
🚀 启动流水线：coder → reviewer
最大修复轮次：{max_retries}  |  阻断级别：{block_on}
需求：{user_input}
```

### Phase 1: coder — 代码生成

1. 通过 `Agent` 工具启动 coder 子 Agent，subagent_type 使用 `general-purpose`。
2. prompt 使用 `pipeline.yaml` 中 `coder.prompt_template`，`{requirement}` 替换为用户需求。首轮 `{review_context}` 为空字符串。
3. 等待 coder 完成。
4. → 进入 Phase 2

**异常处理：**
- coder 未生成任何 `.java` 文件 → 告知用户「未生成代码文件，流水线终止」，停止。
- coder 超时（参考 pipeline.yaml 中 coder 节点的 timeout: 900s） → 告知用户「代码生成超时」，停止。

### Phase 2: review — 双层审查

1. 通过 `Agent` 工具启动 review 子 Agent，subagent_type 使用 `general-purpose`。
2. prompt 使用 `pipeline.yaml` 中 `reviewer.prompt_template`。
3. review Agent 内部会调用 `Skill("review")` 执行：
   - Step 1: Bash CLI 程序预检（强制执行，exit 1 则阻断）
   - Step 2: AI 语义检查（预检通过后才执行）
   - Step 3: 合并报告
4. 等待 review Agent 返回，其最终回复必须是以下三种之一：
   - `REVIEW_PASSED`
   - `REVIEW_FAILED`
   - `REVIEW_ERROR`
5. → 进入 Phase 3

**异常处理：**
- review Agent 超时（参考 pipeline.yaml 中 reviewer 节点的 timeout: 600s） → 告知用户「审查超时」，停止。

### Phase 3: 主控判定

根据 review Agent 的返回结果：

**REVIEW_PASSED：**
- ✅ 流水线成功！读取 `review-output/final-review-report.md` 并展示内容给用户。
- 报告：「流水线完成，经过 {round} 轮。」

**REVIEW_FAILED 且 round < max_retries：**
- round++，报告：「第 {round}/{max_retries} 轮：审查发现问题，回到 coder 修复…」
- 进入 Phase 4（coder 修复模式）。

**REVIEW_FAILED 且 round >= max_retries：**
- ❌ 超出最大轮次。读取 `review-output/final-review-report.md` 并展示内容。
- 报告：「已达最大轮次 {max_retries}，请手动介入修复。」

**REVIEW_ERROR：**
- 🛑 告知用户审查异常（环境/工具问题），停止流水线。不进入修复循环。

### Phase 4（修复轮）: coder 修复

1. 通过 `Agent` 工具启动 coder 子 Agent，subagent_type 使用 `general-purpose`。
2. 修复轮的 prompt 不同于首轮：

```
{原始需求}

⚠️ 这是第 {round}/{max_retries} 轮修复。

请先读取以下文件，了解上一轮审查发现的问题：
1. review-output/pre-check-result.json — 程序预检结果（文件路径、行号、规则、级别、描述）
2. review-output/review-result.json — AI 语义检查结果（如存在）
3. review-output/pre-check-report.md — 预检报告（可读格式）

然后逐个修复所有阻断级问题（P0 必须修，P1 和 AI-FAIL 也尽量修），一次性全部解决。

修复原则（重要！）：
- 同一轮中修复所有级别的问题，不要分批。P0/P1/AI-FAIL 能修的一起修，避免多轮修复
- 只修改有问题的文件和行，不动其他代码
- 修复后必须符合 agents/coder/ 下的所有规范
- 同一文件有多个问题，一次性全部修复
- 不确定的改动，加注释说明原因

⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml（如需添加依赖）。禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。
```

3. 等待 coder 完成修复。
4. 回到 Phase 2（重新审查）。

**异常处理：**
- coder 修复后 P0 数量不降反增 → 不自动终止，让循环继续。
- coder 修复后 P0 不变 → 继续循环，不特殊处理。

---

## 进度报告格式

每轮结束后，主控向用户报告：

```
📊 第 {round}/{max_retries} 轮完成
   review 结果：{PASSED / FAILED / ERROR}
   ➡️ {下一步动作：修复 / 完成 / 超限 / 停止}
```

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 提示「请输入需求描述，如：/build 实现用户登录功能」 |
| 需求模糊 | 追问 1-2 个澄清问题 |
| coder 未生成文件 | 停止流水线，提示「未生成 Java 文件」 |
| coder 超时 (900s) | 停止，提示超时 |
| review 返回 REVIEW_ERROR | 停止，告知用户审查异常 |
| review 超时 (600s) | 停止，保留产物 |
| max_retries 耗尽 | 展示最终报告，提示用户手动介入 |
| 用户 Ctrl+C | 保留产物，展示已完成轮次 |
