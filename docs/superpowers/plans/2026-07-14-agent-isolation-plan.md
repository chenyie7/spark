# Agent 隔离规则与输出路径修正 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 PM/Coder/Reviewer 三个 Agent 定义严格的读取范围隔离规则，修正 PM 输出路径从 spark 项目根目录到目标项目的 `{output_dir}/docs/` 下

**Architecture:** 纯文档修改 — 5 个 Markdown/YAML 文件的精确编辑。在每个 Agent 的 skill 入口文件中新增「读取范围」章节定义允许/禁止读取列表，修改 PM 的 spec/plan 输出路径，更新 pipeline.yaml 和 build.skill.md 中的引用

**Tech Stack:** 无（文档编辑）

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `agents/pm/pm.skill.md` | PM Agent 入口 — 新增读取范围 + 修正输出路径 |
| `agents/coder/coder.skill.md` | Coder Agent 入口 — 新增读取范围 |
| `agents/reviewer/review.skill.md` | Reviewer Agent 入口 — 新增读取范围 + Step 2 增加 spec 输入 |
| `agents/scheduler/pipeline.yaml` | 流水线配置 — 更新 coder/reviewer prompt 引用隔离规则 |
| `agents/scheduler/build.skill.md` | 调度入口 — 更新 Phase 1 输出路径说明 |
| （不改）`agents/coder/README.md` | 规范索引，职责不变 |
| （不改）`agents/reviewer/README.md` | 说明文档，给人看 |
| （不改）`agents/scheduler/pipeline_engine/` | 调度逻辑不变 |

---

### Task 1: PM Agent — 删除 docs/ 误读 + 新增读取范围 + 修正输出路径

**Files:**
- Modify: `agents/pm/pm.skill.md`

- [ ] **Step 1: 删除「探索项目上下文」中对 spark docs/ 的误读**

定位到第 56-59 行的「第一步: 探索项目上下文」列表，删除最后两条（第 58-59 行），保留第 55-57 行。

当前内容（第 55-59 行）：
```markdown
- 检查现有代码结构（项目根目录下的 src/main/java 包路径）
- 读取 `CLAUDE.md` 了解项目规范和 Agent 体系
- 读取 `agents/coder/README.md` 了解架构约束（包结构、分层、注入、异常、SQL 等规范）
- 检查 `docs/superpowers/specs/` 下是否已有相关设计文档
- 检查 `docs/superpowers/plans/` 下是否已有相关实现计划
```

替换为：
```markdown
- 读取 `CLAUDE.md` 了解项目规范和 Agent 体系
- 读取 `agents/coder/README.md` 了解架构约束（包结构、分层、注入、异常、SQL 等规范）
- 从 `review-output/{run_id}/pm-context.json` 获取 `output_dir`（目标项目路径）
- 检查目标项目 `{output_dir}/docs/specs/` 下是否已有相关设计文档
- 检查目标项目 `{output_dir}/docs/plans/` 下是否已有相关实现计划
- 检查目标项目 `{output_dir}/src/main/java/` 下现有代码结构
```

- [ ] **Step 2: 在第一步末尾新增「读取范围」章节**

在「向用户简要报告探索结果…」这一行（第 61 行）之后，第二步之前，插入以下章节：

```markdown

---

## 读取范围

**允许读取：**
- `CLAUDE.md`（项目全局规范说明）
- `agents/pm/pm.skill.md`（自身）
- `agents/coder/README.md`（架构约束概览，用于 spec 中引用编码规范）
- 目标项目 `{output_dir}/docs/` 下已有设计文档（specs/ 和 plans/）
- 目标项目现有代码结构（`{output_dir}/src/main/java/`）
- `review-output/{run_id}/pm-context.json`（获取上下文参数）

**禁止读取：**
- spark 项目 `docs/` 下任何内容
- `agents/coder/` 下具体规范文件（README.md 除外）
- `agents/reviewer/`、`agents/scheduler/` 下任何内容
```

- [ ] **Step 3: 修正 spec 输出路径（第 118 行）**

当前：
```markdown
将确认后的设计写入 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`。
```

替换为：
```markdown
将确认后的设计写入 `{output_dir}/docs/specs/YYYY-MM-DD-<topic>-design.md`（`output_dir` 从 pm-context.json 获取）。
```

- [ ] **Step 4: 修正 plan 输出路径（第 161 行）**

当前：
```markdown
spec 确认后，写入 `docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md`。
```

替换为：
```markdown
spec 确认后，写入 `{output_dir}/docs/plans/YYYY-MM-DD-<topic>-plan.md`（`output_dir` 从 pm-context.json 获取）。
```

- [ ] **Step 5: 验证 pm.skill.md 修改正确**

```bash
grep -n "docs/superpowers" /Users/chenyi/ai-project/spark/agents/pm/pm.skill.md
```
Expected: 无输出（所有 spark 项目的 docs/superpowers 引用已清除）

```bash
grep -n "output_dir" /Users/chenyi/ai-project/spark/agents/pm/pm.skill.md
```
Expected: 显示 3-4 处引用（探索上下文 + 读取范围 + spec 路径 + plan 路径）

- [ ] **Step 6: Commit**

```bash
git add agents/pm/pm.skill.md
git commit -m "fix(pm): 新增读取范围隔离规则，修正 spec/plan 输出到目标项目 docs/

- 删除对 spark 项目 docs/superpowers/ 的误读
- 新增「读取范围」章节，定义 PM 的允许/禁止读取列表
- spec 和 plan 输出路径改为 {output_dir}/docs/specs|plans/
- 探索上下文改为读取目标项目的代码结构和已有文档"
```

---

### Task 2: Coder Agent — 新增读取范围

**Files:**
- Modify: `agents/coder/coder.skill.md`

- [ ] **Step 1: 在「边界约束」章节前新增「读取范围」**

定位到第 75-76 行（全局规则的 URL 行结束），和第 77 行「## 边界约束」之间。

在第 77 行 `## 边界约束` 之前插入：

```markdown

---

## 读取范围

**允许读取：**
- `agents/coder/` 下所有规范文件（按 Phase 0-1 流程按需加载，不一次性全读）
- 目标项目 `{output_dir}/docs/specs/` 和 `{output_dir}/docs/plans/`（PM 产出的设计和实现计划）
- 目标项目 `{output_dir}/src/main/java/` 和 `{output_dir}/pom.xml`（待修改的代码）
- `review-output/.current-run`（获取 output_dir 和 scan_path）

**禁止读取：**
- spark 项目 `docs/` 下任何内容
- `agents/pm/`、`agents/reviewer/`、`agents/scheduler/` 下任何内容
- `CLAUDE.md`
```

- [ ] **Step 2: 验证 coder.skill.md 修改正确**

```bash
grep -A 15 "## 读取范围" /Users/chenyi/ai-project/spark/agents/coder/coder.skill.md
```
Expected: 显示完整的读取范围章节，包含允许和禁止两个列表

- [ ] **Step 3: Commit**

```bash
git add agents/coder/coder.skill.md
git commit -m "fix(coder): 新增读取范围隔离规则

- 明确允许读取 agents/coder/、目标项目代码和 PM 产出
- 明确禁止读取 spark docs/、其他 Agent 目录、CLAUDE.md"
```

---

### Task 3: Reviewer Agent — 新增读取范围 + Step 2 增加 spec 输入

**Files:**
- Modify: `agents/reviewer/review.skill.md`

- [ ] **Step 1: 在「执行流程」前新增「读取范围」章节**

定位到第 9-10 行的 `---` 分隔线和第 12 行 `## 执行流程` 之间。

在第 12 行 `## 执行流程` 之前插入：

```markdown

---

## 读取范围

**允许读取：**
- `agents/reviewer/` 下所有文件（审查规范、checklist、check_system）
- 目标项目 `docs/specs/`（对照设计文档验证业务逻辑正确性）
- 目标项目 `src/main/java/` 下所有 Java 文件
- `review-output/.current-run`（获取 output_dir 和 scan_path）
- `review-output/{run_id}/quality.json`（Layer 1 静态分析结果）

**禁止读取：**
- 目标项目 `docs/plans/`（含具体实现步骤，会造成审查偏差，失去审查独立性）
- spark 项目 `docs/` 下任何内容
- `agents/coder/`、`agents/pm/`、`agents/scheduler/` 下任何内容
- `CLAUDE.md`
```

- [ ] **Step 2: 修改 Step 2「AI 统一审查」的输入列表**

定位到第 29-32 行的 Step 2 输入列表。

当前（第 28-32 行）：
```markdown
**输入：**
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（涵盖结构、质量、认证、基础设施等多维度）
- `review-output/{run_id}/quality.json` — 静态分析结果（如存在）
- `{path}` 下的 Java 源文件
```

替换为：
```markdown
**输入：**
- 目标项目 `docs/specs/` 下的设计文档（验证业务逻辑是否符合需求设计）
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（涵盖结构、质量、认证、基础设施等多维度）
- `review-output/{run_id}/quality.json` — 静态分析结果（如存在）
- `{path}` 下的 Java 源文件
```

- [ ] **Step 3: 验证 review.skill.md 修改正确**

```bash
grep -A 15 "## 读取范围" /Users/chenyi/ai-project/spark/agents/reviewer/review.skill.md
```
Expected: 显示完整的读取范围章节

```bash
grep -B 2 "docs/specs" /Users/chenyi/ai-project/spark/agents/reviewer/review.skill.md
```
Expected: 两处引用 — 读取范围中 + Step 2 输入列表中

- [ ] **Step 4: Commit**

```bash
git add agents/reviewer/review.skill.md
git commit -m "fix(reviewer): 新增读取范围隔离规则，审查增加 spec 对照

- 新增「读取范围」章节，明确允许/禁止读取列表
- Step 2 AI 审查输入增加目标项目 docs/specs/，对照需求验证业务逻辑
- 明确禁止读取 docs/plans/（含实现步骤，避免审查偏差）
- 明确禁止读取其他 Agent 目录和 CLAUDE.md"
```

---

### Task 4: Pipeline 配置 — 更新 Coder/Reviewer prompt

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 更新 Coder prompt_template 中的隔离声明**

定位到第 38-41 行的 Coder prompt_template `边界约束` 部分。

当前（第 38-41 行）：
```yaml
      边界约束：
      1. 你只能修改 {output_dir}/src/main/java/ 目录下的 Java 文件和 {output_dir}/pom.xml（如需添加依赖）。
      2. 禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。
      3. 禁止读取修改 ./docs 下的所有内容除非用户指定了你能读取和修改的内容路径
```

替换为：
```yaml
      边界约束：
      1. 你只能修改 {output_dir}/src/main/java/ 目录下的 Java 文件和 {output_dir}/pom.xml（如需添加依赖）。
      2. 禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。
      3. 严格遵守 `agents/coder/coder.skill.md` 中「读取范围」定义的允许和禁止读取列表。
```

- [ ] **Step 2: 更新 Reviewer prompt_template 增加隔离声明**

定位到第 57-59 行的 Reviewer prompt_template 开头。

当前（第 57-59 行）：
```yaml
    prompt_template: |
      开始工作前，先读取 review-output/.current-run 获取 output_dir 和 scan_path。

      你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。
```

替换为：
```yaml
    prompt_template: |
      开始工作前，先读取 review-output/.current-run 获取 output_dir 和 scan_path。
      严格遵守 `agents/reviewer/review.skill.md` 中「读取范围」定义的允许和禁止读取列表。

      你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。
```

- [ ] **Step 3: 验证 pipeline.yaml 修改正确**

```bash
grep -n "读取范围" /Users/chenyi/ai-project/spark/agents/scheduler/pipeline.yaml
```
Expected: 两处引用（coder 边界约束第 3 条 + reviewer 开头）

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "fix(pipeline): 更新 coder/reviewer prompt 引用 skill 中的隔离规则

- coder 边界约束第 3 条改为引用 coder.skill.md 读取范围
- reviewer prompt 开头增加引用 review.skill.md 读取范围
- 替换模糊的 './docs 禁止读取' 为明确的隔离规则引用"
```

---

### Task 5: Build 调度入口 — 更新 Phase 1 输出路径说明

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 修正 Phase 1 第 4 步中的 spec/plan 输出路径**

定位到第 78-82 行的 Phase 1 第 4 步子列表。

当前（第 78-82 行）：
```markdown
   - 输出 spec: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
   - spec 自检（placeholder、矛盾、歧义、范围）
   - 用户 review spec → 修改或确认
   - 输出 plan: `docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md`
   - plan 自检（spec 覆盖、placeholder、类型一致性）
```

替换为：
```markdown
   - 输出 spec: `{output_dir}/docs/specs/YYYY-MM-DD-<topic>-design.md`
   - spec 自检（placeholder、矛盾、歧义、范围）
   - 用户 review spec → 修改或确认
   - 输出 plan: `{output_dir}/docs/plans/YYYY-MM-DD-<topic>-plan.md`
   - plan 自检（spec 覆盖、placeholder、类型一致性）
```

- [ ] **Step 2: 验证 build.skill.md 修改正确**

```bash
grep -n "docs/superpowers" /Users/chenyi/ai-project/spark/agents/scheduler/build.skill.md
```
Expected: 无输出（所有 spark 项目的 docs/superpowers 引用已清除）

```bash
grep -n "output_dir.*docs" /Users/chenyi/ai-project/spark/agents/scheduler/build.skill.md
```
Expected: 显示 2 处（spec 路径 + plan 路径，均在 Phase 1 第 4 步中）

- [ ] **Step 5: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "fix(build): Phase 1 spec/plan 输出路径改为目标项目的 docs/

- spec: {output_dir}/docs/specs/...
- plan: {output_dir}/docs/plans/...
- 与 pm.skill.md 的输出路径保持一致"
```

---

### Task 6: 全局一致性验证

- [ ] **Step 1: 确认 spark 项目中无残留 docs/superpowers 引用（排除本次设计文档自身和 plan）**

```bash
grep -rn "docs/superpowers" /Users/chenyi/ai-project/spark/agents/ /Users/chenyi/ai-project/spark/CLAUDE.md 2>/dev/null
```
Expected: 无输出

- [ ] **Step 2: 确认每个 Agent skill 文件都有「读取范围」章节**

```bash
for f in agents/pm/pm.skill.md agents/coder/coder.skill.md agents/reviewer/review.skill.md; do
  echo "=== $f ==="
  grep -c "读取范围" "$f"
done
```
Expected: 每个文件至少 1 处

- [ ] **Step 3: 确认 pipeline.yaml 有两处「读取范围」引用**

```bash
grep -c "读取范围" /Users/chenyi/ai-project/spark/agents/scheduler/pipeline.yaml
```
Expected: 2

- [ ] **Step 4: 确认禁止项覆盖完整**

```bash
echo "=== PM 禁止项 ===" && grep -A 10 "禁止读取" agents/pm/pm.skill.md | head -6
echo "=== Coder 禁止项 ===" && grep -A 10 "禁止读取" agents/coder/coder.skill.md | head -7
echo "=== Reviewer 禁止项 ===" && grep -A 10 "禁止读取" agents/reviewer/review.skill.md | head -7
```
Expected: 三者均列出完整的禁止列表

- [ ] **Step 5: Commit**

```bash
git add -A
git diff --cached --stat
git commit -m "chore: 全局一致性验证通过

所有 Agent skill 文件均包含「读取范围」章节
pipeline.yaml 引用隔离规则
spark docs/superpowers 引用已清除"
```
