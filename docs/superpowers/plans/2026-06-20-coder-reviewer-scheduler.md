# Coder-Reviewer 调度器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `/build` 斜杠命令，自动化 coder → reviewer → fix 循环。

**Architecture:** Skill 驱动，单会话多子 Agent。`build.skill.md` 作为调度 Agent 指令，读取 `pipeline.yaml` 获取 DAG 定义，通过 `Agent` 工具按序创建 coder/reviewer 子 Agent，循环直到 P0 清零或达到最大轮次。

**Tech Stack:** Claude Code Skill + YAML + Agent tool。无 Python 代码，调度逻辑由 Skill 指令 + AI 执行。

---

### Task 1: 创建 pipeline.yaml 调度模板

**Files:**
- Create: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 写入 pipeline.yaml**

```yaml
# pipeline.yaml
# Coder-Reviewer 流水线 DAG 配置
# 调度 Agent 读取本文件获取节点和边的定义，按拓扑顺序执行。

name: coder-reviewer-pipeline
version: "1.0"
description: "标准 coder → reviewer 代码生成流水线，含 P0 修复循环"

# ── 全局默认值 ──
# 调度 Agent 在启动每个节点时使用这些默认值，节点可覆盖。
defaults:
  timeout: 600s          # 单节点默认超时（秒）
  max_retries: 3         # reviewer → coder 最大循环轮次
  block_on: [P0]         # 触发回退的严重级别列表

# ── DAG 节点 ──
# 每个节点对应一个 Agent。调度 Agent 按 edges 定义的顺序逐个执行。
nodes:
  - id: coder
    type: agent
    agent: coder
    description: "根据需求生成 Spring Boot 3 Java 代码，遵守 agents/coder/ 下的所有规范"
    prompt_template: |
      你需要根据用户需求生成 Java 代码。

      用户需求：
      {requirement}

      你必须遵守以下规范（读取 agents/coder/README.md 获取完整索引）：
      - 包结构：controller → service/impl → mapper → entity/dto/vo
      - 返回值：统一 Result<T>
      - 注入：构造注入 @RequiredArgsConstructor，不用 @Autowired 字段注入
      - 日志：@Slf4j，不打敏感信息
      - 异常：抛 BusinessException，不写自由文本
      - SQL：简单查 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 @Select
      - 参数：>3 个收敛到 DTO
      - URL：RESTful 复数名词，CRUD 不用动词

      {review_context}

      将生成的 Java 代码写入 src/main/java 对应包路径下。
    inputs:
      - requirement: "${user_input}"
      - review_context: "review-output/ 目录下的审查结果（仅修复轮次时存在）"
    outputs:
      - target_dir: "src/main/java"
    timeout: 900s

  - id: reviewer
    type: agent
    agent: reviewer
    description: "对 coder 产出的代码执行双层审查：Layer 1 Python CLI 预检 + Layer 2 AI 语义检查"
    prompt_template: |
      对 {coder_output} 目录下的 Java 代码执行双层代码审查。

      Layer 1 — 程序预检（零 AI Token）：
      1. 进入 agents/reviewer/check_system 目录
      2. 执行 python3 -m code_check.cli scan {coder_output}
      3. exit 0 → 继续 Layer 2
      4. exit 1 → 输出阻断报告 review-output/pre-check-report.md

      Layer 2 — AI 语义检查：
      1. 读取 agents/reviewer/check_system/rules/ai-checklist.yaml（17 项语义规则）
      2. 读取 review-output/pre-check-result.json 获取预检线索
      3. 逐项检查并输出 review-result.json

      合并报告：
      执行 python3 -m code_check.cli report \
        --pre review-output/pre-check-result.json \
        --ai review-output/review-result.json \
        --output review-output/final-review-report.md
    inputs:
      - coder_output: "${coder.outputs.target_dir}"
    outputs:
      - pre_check: "review-output/pre-check-result.json"
      - ai_review: "review-output/review-result.json"
      - final_report: "review-output/final-review-report.md"
    timeout: 600s

# ── DAG 边 ──
# 调度 Agent 按以下规则决定流转：
#   1. coder 成功后 → reviewer
#   2. reviewer 完成后 → 读取 pre-check-result.json 的 P0 数量
#   3. P0 > 0 且未达 max_retries → 回到 coder（修复模式）
#   4. P0 = 0 或达到 max_retries → DONE
edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: "coder 生成代码后，进入 reviewer 审查"

  - from: reviewer
    to: coder
    trigger: on_condition
    condition:
      field: "${reviewer.outputs.pre_check}.summary.p0_count"
      operator: gt
      value: 0
    description: "存在 P0 问题，回到 coder 修复。调度 Agent 需额外检查 round < max_retries"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      field: "${reviewer.outputs.pre_check}.summary.p0_count"
      operator: eq
      value: 0
    description: "P0 清零，流水线成功结束。调度 Agent 展示 final-review-report.md"
```

- [ ] **Step 2: 提交**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "feat: add pipeline.yaml DAG config for coder-reviewer scheduler"
```

---

### Task 2: 创建 build.skill.md 调度 Skill

**Files:**
- Create: `agents/scheduler/build.skill.md`

这是调度 Agent 的指令文件。它详细描述 `/build` 命令的执行流程、循环逻辑和错误处理。

- [ ] **Step 1: 写入 build.skill.md**

````markdown
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
| python3 不可用 | 停止流水线，提示「需要 Python 3」 |
| pre-check-result.json 缺失 | 降级为 Layer 2 only |
| review-result.json 缺失 | 降级展示 pre-check 结果，停止循环 |
| coder 超时 (900s) | 停止，提示超时 |
| reviewer 超时 (600s) | 停止，保留产物 |
| max_retries 耗尽 | 展示最终报告，提示用户手动介入 |
| 用户 Ctrl+C | 保留产物，展示已完成轮次 |
````

- [ ] **Step 2: 提交**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: add /build skill — coder-reviewer pipeline scheduler"
```

---

### Task 3: 更新 CLAUDE.md 入口

**Files:**
- Modify: `CLAUDE.md:54-56`

在 CLAUDE.md 的「如何使用」章节的 `阶段 1（coder）` 之前添加调度器入口。

- [ ] **Step 1: 读取 CLAUDE.md 确认当前内容**

```bash
# 确认第 20-35 行附近的「开发流程」部分
```

- [ ] **Step 2: 在开发流程章节顶部添加调度器入口**

当前 CLAUDE.md 的「开发流程」部分：

```
### 开发流程

阶段 1（coder）：按设计文档 + 架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 2（check_system）：双层校验 — 代码写完后的第一道防线
  ...
```

修改为：

```
### 开发流程

🚀 一键流程：/build <需求描述>  — 自动执行 阶段1→阶段2→修复循环
  入口：agents/scheduler/build.skill.md

阶段 1（coder）：按设计文档 + 架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 2（check_system）：双层校验 — 代码写完后的第一道防线
  ...
```

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: add /build scheduler entry to CLAUDE.md"
```

---

### Task 4: 验证端到端

**Files:**
- 无新建文件（验证任务）

- [ ] **Step 1: 验证 pipeline.yaml 能被读取**

```bash
cat agents/scheduler/pipeline.yaml
```
预期：YAML 内容正常显示，格式正确。

- [ ] **Step 2: 验证 build.skill.md 能被 Skill 系统识别**

```bash
head -6 agents/scheduler/build.skill.md
```
预期：frontmatter 包含 `name: build` 和 `description: ...`。

- [ ] **Step 3: 验证 reviewer CLI 可用**

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli --help
```
预期：显示 CLI 帮助信息，`scan` 和 `report` 子命令可用。

- [ ] **Step 4: 确认文件结构正确**

```bash
find agents/scheduler -type f
```
预期输出：
```
agents/scheduler/build.skill.md
agents/scheduler/pipeline.yaml
```

- [ ] **Step 5: 提交（如有修改）**

```bash
git status
# 如果验证过程中有修改，提交
```
````

---

## 自审清单

**1. Spec 覆盖检查：**

| Spec 章节 | 对应 Task |
|-----------|----------|
| 三、YAML 调度模板 Schema | Task 1 (pipeline.yaml) |
| 二、架构方案 — Skill 驱动 | Task 2 (build.skill.md) |
| 二、运行模型 — 单会话多子 Agent | Task 2 (Agent 工具调用说明) |
| 五、错误处理全部场景 | Task 2 (错误处理速查表) |
| 四、文件结构 | Task 1, 2, 3 |
| 六、测试策略 | Task 4 (验证步骤) |

**2. Placeholder 扫描：** ✅ 无 TBD/TODO。所有代码和命令均为完整内容。

**3. 类型一致性：**
- YAML 中的字段名 (`p0_count`, `pre-check-result.json`) 在 Skill 文件中保持一致 ✅
- 文件路径 (`agents/scheduler/`, `review-output/`, `src/main/java`) 跨 Task 一致 ✅
- `round` 计数器命名在 Skill 文件中统一 ✅
````
