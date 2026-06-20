# Build-Review 流水线修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使 `/build` 流水线的程序预检成为确定性硬闸门——预检失败立即阻断并回到 coder 修复，直到 P0 清零或达到最大轮次。

**Architecture:** `/build` 主控 Agent 通过 `Agent("review")` 启动 review 子进程（内部调 `Skill("review")` 强制执行 Bash CLI），根据子进程返回的 PASS/FAIL/ERROR 决定下一步。Coder 修复轮自己读取 `review-output/` 产物。

**Tech Stack:** Claude Code Skill + Agent 工具，Python CLI（已有，不改），Bash 脚本（已有，不改）

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `agents/reviewer/review.skill.md` | `/review` 技能定义：Step 1 Bash CLI → Step 2 AI 检查 → Step 3 合并报告 | 简化，移除 :on/:off |
| `agents/scheduler/pipeline.yaml` | 流水线 DAG 配置：coder/reviewer 节点定义和边 | 更新 reviewer prompt |
| `agents/scheduler/build.skill.md` | `/build` 技能定义：编排 coder → review → 修复循环 | 重构 Phase 2/3/4 |

---

### Task 1: 简化 `review.skill.md`

**Files:**
- Modify: `agents/reviewer/review.skill.md`（全量重写）

**目标：** 将 `/review` 精简为纯三步技能，移除 `/review:on` 和 `/review:off` 功能说明。保留 `settings.template.json` 文件不动。

- [ ] **Step 1: 重写 `review.skill.md`**

将文件内容替换为：

```markdown
---
name: review
description: 双层代码审查 —— 程序预检阻断 + AI 语义检查，输出完整审查报告
---

# /review — 双层代码审查

用法：`/review <path>`，`path` 是要扫描的 Java 代码路径，默认 `src/main/java`。

---

## 执行流程

### Step 1: 程序预检（硬阻断）

执行 Bash 脚本进行确定性规则检查。exit 1 时立即停止，不执行 Step 2。

```bash
bash agents/reviewer/hooks/review-pre-hook.sh {path}
```

- `exit 0`：预检通过，`review-output/pre-check-result.json` 已生成 → 继续 Step 2
- `exit 1`：预检未通过，`review-output/pre-check-result.json` + `review-output/pre-check-report.md` 已生成 → **停止。** 返回 `REVIEW_FAILED`，不执行后续步骤

### Step 2: AI 语义检查

读取 `agents/reviewer/check_system/rules/review-prompt.md`，严格按照其中的指令执行。

核心输入：
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 语义规则清单（17 项）
- `review-output/pre-check-result.json` — 程序预检的线索和上下文
- `{path}` 下的 Java 源文件

输出：`review-output/review-result.json`

### Step 3: 合并最终报告

```bash
bash agents/reviewer/hooks/review-post-hook.sh
```

将生成的 `review-output/final-review-report.md` 内容展示给用户。

---

## 返回协议

执行完成后，返回以下三种结果之一：

| 返回值 | 含义 |
|--------|------|
| `REVIEW_PASSED` | 预检通过，AI 检查完成，产物完整 |
| `REVIEW_FAILED` | 预检阻断（P0>0），或 AI 检查有 FAIL |
| `REVIEW_ERROR` | 环境/工具异常（python3 不可用、CLI 崩溃等） |
```

- [ ] **Step 2: 验证文件内容正确**

```bash
grep -c "REVIEW_PASSED\|REVIEW_FAILED\|REVIEW_ERROR" agents/reviewer/review.skill.md
```
Expected: 返回 3（三条返回协议都在文件中）

- [ ] **Step 3: 确认 `review:on` / `review:off` 已移除**

```bash
grep "review:on\|review:off" agents/reviewer/review.skill.md
```
Expected: 无输出（已移除）

- [ ] **Step 4: 确认 `settings.template.json` 未被修改**

```bash
git diff --name-only
```
Expected: 不包含 `agents/reviewer/hooks/settings.template.json`

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/review.skill.md
git commit -m "refactor: simplify /review skill — remove :on/:off, add return protocol

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 更新 `pipeline.yaml` 的 reviewer 节点

**Files:**
- Modify: `agents/scheduler/pipeline.yaml:49-78`（reviewer 节点的 prompt_template）

**目标：** reviewer 节点的 prompt_template 改为引导 review Agent 内部调用 `Skill("review")`，移除之前「建议跑 CLI」的模糊指令。

- [ ] **Step 1: 替换 reviewer 节点的 prompt_template**

定位到 `agents/scheduler/pipeline.yaml` 中的 `- id: reviewer` 节点（第 49-78 行），将其 `prompt_template` 替换为：

```yaml
    prompt_template: |
      你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。

      调用 Skill("review", args="src/main/java") 执行双层代码审查。

      /review 技能内部会：
      - Step 1: 强制执行 Bash CLI 程序预检（python3 -m code_check.cli scan）
      - Step 2: AI 语义检查（读取 ai-checklist.yaml，17 项规则）
      - Step 3: 合并报告（python3 -m code_check.cli report）

      执行完成后，你必须根据结果返回以下三种状态之一：

      REVIEW_PASSED — 预检通过 + AI 检查完成，所有产物已生成
      REVIEW_FAILED — 预检被阻断（P0>0），产物在 review-output/ 中
      REVIEW_ERROR  — 环境/工具异常（python3 不可用、CLI 崩溃等）

      你的最终回复必须且只能是这三种状态之一，不要返回其他内容。
```

完整的 reviewer 节点替换后为：

```yaml
  - id: reviewer
    type: agent
    agent: reviewer
    description: "对 coder 产出的代码执行双层审查：通过 Skill(review) 强制执行 Layer 1 Python CLI 预检 + Layer 2 AI 语义检查"
    prompt_template: |
      你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。

      调用 Skill("review", args="src/main/java") 执行双层代码审查。

      /review 技能内部会：
      - Step 1: 强制执行 Bash CLI 程序预检（python3 -m code_check.cli scan）
      - Step 2: AI 语义检查（读取 ai-checklist.yaml，17 项规则）
      - Step 3: 合并报告（python3 -m code_check.cli report）

      执行完成后，你必须根据结果返回以下三种状态之一：

      REVIEW_PASSED — 预检通过 + AI 检查完成，所有产物已生成
      REVIEW_FAILED — 预检被阻断（P0>0），产物在 review-output/ 中
      REVIEW_ERROR  — 环境/工具异常（python3 不可用、CLI 崩溃等）

      你的最终回复必须且只能是这三种状态之一，不要返回其他内容。
    inputs:
      - coder_output: "${coder.outputs.target_dir}"
    outputs:
      - pre_check: "review-output/pre-check-result.json"
      - ai_review: "review-output/review-result.json"
      - final_report: "review-output/final-review-report.md"
    timeout: 600s
```

- [ ] **Step 2: 验证 YAML 语法正确**

```bash
python3 -c "import yaml; yaml.safe_load(open('agents/scheduler/pipeline.yaml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 3: 验证 prompt_template 中不含 '请执行' 类的建议性措辞**

```bash
grep "请执行\|请运行\|请确保" agents/scheduler/pipeline.yaml
```
Expected: 无输出（指令是命令式，不是建议式）

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "refactor: update reviewer node prompt — review Agent 内部调 Skill(review)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 重构 `build.skill.md` — Phase 2/3/4

**Files:**
- Modify: `agents/scheduler/build.skill.md`（全量重写）

**目标：** 将 `/build` 流水线改为：Agent("coder") → Agent("review") → 根据 PASS/FAIL/ERROR 判定 → 修复循环。主控不读 JSON、不构造问题、不验证产物。

- [ ] **Step 1: 备份当前版本（保留参考）**

```bash
cp agents/scheduler/build.skill.md agents/scheduler/build.skill.md.bak
```

- [ ] **Step 2: 重写 `build.skill.md`**

将文件内容替换为：

```markdown
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
2. prompt 使用 `pipeline.yaml` 中 `coder.prompt_template`，`{requirement}` 替换为用户需求。首轮无 `{review_context}`。
3. 等待 coder 完成。

**异常处理：**
- coder 未生成任何 `.java` 文件 → 告知用户「未生成代码文件，流水线终止」，停止。
- coder 超时 → 告知用户「代码生成超时」，停止。

### Phase 2: review — 双层审查

1. 通过 `Agent` 工具启动 review 子 Agent，subagent_type 使用 `general-purpose`。
2. prompt 使用 `pipeline.yaml` 中 `reviewer.prompt_template`。
3. review Agent 内部调用 `Skill("review")` 执行：
   - Step 1: Bash CLI 程序预检（强制执行）
   - Step 2: AI 语义检查（预检通过后才执行）
   - Step 3: 合并报告
4. 等待 review Agent 返回，其最终回复必须是以下三种之一：
   - `REVIEW_PASSED`
   - `REVIEW_FAILED`
   - `REVIEW_ERROR`

**异常处理：**
- review Agent 超时 → 告知用户「审查超时」，停止。

### Phase 3: 主控判定

根据 review Agent 的返回结果：

**REVIEW_PASSED：**
- ✅ 流水线成功！展示 `review-output/final-review-report.md` 内容给用户。
- 报告：「流水线完成，经过 {round} 轮。」

**REVIEW_FAILED 且 round < max_retries：**
- round++，报告：「第 {round}/{max_retries} 轮：审查发现问题，回到 coder 修复…」
- 进入 Phase 4（coder 修复模式）。

**REVIEW_FAILED 且 round >= max_retries：**
- ❌ 超出最大轮次。展示 `review-output/final-review-report.md`。
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

然后逐个修复所有 P0 问题。修复原则：
- 只修改有问题的文件和行，不动其他代码
- 修复后必须符合 agents/coder/ 下的所有规范
- 同一文件有多个问题，一次性全部修复
- 不确定的改动，加注释说明原因
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
```

- [ ] **Step 3: 验证 Phase 2 使用 Agent("review") 而非直接 Skill("review")**

```bash
grep "Agent.*review" agents/scheduler/build.skill.md | head -3
```
Expected: 输出中包含 `Agent` 工具启动 review 子 Agent 的说明

- [ ] **Step 4: 验证主控不读 JSON、不构造问题**

```bash
grep -i "pre-check-result.json\|review-result.json\|pre-check-report.md" agents/scheduler/build.skill.md
```
Expected: 仅在 Phase 4 的 coder prompt 中出现（引导 coder 自己去读），不在主控判定 Phase 3 中出现

- [ ] **Step 5: 验证三种返回协议都在 Phase 3 中有处理**

```bash
grep "REVIEW_PASSED\|REVIEW_FAILED\|REVIEW_ERROR" agents/scheduler/build.skill.md | wc -l
```
Expected: 至少 4 行（每种状态都有对应的处理分支）

- [ ] **Step 6: 清理备份文件**

```bash
rm agents/scheduler/build.skill.md.bak
```

- [ ] **Step 7: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "refactor: /build pipeline — Agent(review)+Skill(review) 组合, 主控薄层判定

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 端到端流程验证

**Files:**
- 只读，不修改任何文件

**目标：** 从文件层面验证整个流水线的逻辑完整性，确认三个文件之间的一致性。

- [ ] **Step 1: 验证 `/review` 和 `pipeline.yaml` 的 reviewer prompt 协议一致**

```bash
echo "=== review.skill.md 返回协议 ===" && grep -A4 "返回协议" agents/reviewer/review.skill.md && echo "" && echo "=== pipeline.yaml reviewer prompt 返回协议 ===" && grep -A4 "REVIEW_PASSED\|REVIEW_FAILED\|REVIEW_ERROR" agents/scheduler/pipeline.yaml
```
Expected: 两边都包含 REVIEW_PASSED、REVIEW_FAILED、REVIEW_ERROR 三种状态

- [ ] **Step 2: 验证 `/build` 和 `pipeline.yaml` 的 coder prompt 模板一致**

```bash
echo "=== pipeline.yaml coder prompt_template ===" && grep -A20 "prompt_template:" agents/scheduler/pipeline.yaml | head -25 && echo "" && echo "=== build.skill.md coder prompt ===" && grep -A15 "Phase 1: coder" agents/scheduler/build.skill.md | head -20
```
Expected: build.skill.md Phase 1 引用了 pipeline.yaml 的 coder.prompt_template

- [ ] **Step 3: 验证修复循环完整闭环**

```bash
echo "=== 检查 build.skill.md 中修复循环的关键连接点 ===" && echo "1. Phase 3 REVIEW_FAILED → Phase 4:" && grep -n "Phase 4\|进入 Phase 4\|coder 修复模式" agents/scheduler/build.skill.md && echo "2. Phase 4 回到 Phase 2:" && grep -n "回到 Phase 2" agents/scheduler/build.skill.md
```
Expected:
- Phase 3 的输出中有进入 Phase 4 的语句
- Phase 4 的末行有回到 Phase 2 的语句

- [ ] **Step 4: 验证 review-pre-hook.sh 仍然可执行**

```bash
bash -n agents/reviewer/hooks/review-pre-hook.sh && echo "Bash syntax OK"
```
Expected: `Bash syntax OK`

- [ ] **Step 5: 验证 review-post-hook.sh 仍然可执行**

```bash
bash -n agents/reviewer/hooks/review-post-hook.sh && echo "Bash syntax OK"
```
Expected: `Bash syntax OK`

- [ ] **Step 6: 验证 Python CLI 可正常导入**

```bash
cd agents/reviewer/check_system && python3 -c "from code_check.cli import main; print('CLI import OK')"
```
Expected: `CLI import OK`

- [ ] **Step 7: Commit（如有修改）**

如果以上验证步骤触发了任何修改：
```bash
git add -A
git commit -m "chore: end-to-end verification of build-review pipeline

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
否则：
```bash
echo "验证通过，无需修改"
```
