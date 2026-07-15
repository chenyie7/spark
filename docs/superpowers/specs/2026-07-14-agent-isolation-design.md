# Agent 隔离规则与输出路径修正

## 概述

当前 PM/Coder/Reviewer 三个 Agent 的读取范围没有明确定义，导致：
1. PM 读取了 spark 项目自己的 `docs/`（输出目录），造成循环干扰
2. PM 的 spec/plan 输出到了 spark 项目根目录，而非目标项目的 `docs/` 下
3. Coder 和 Reviewer 可能读取到不该读的内容，产生干扰

本次修改为三个 Agent 定义严格的读取范围，并修正 PM 的输出路径。

## 读取范围总览

| 内容 | PM | Coder | Reviewer |
|------|:--:|:-----:|:--------:|
| `CLAUDE.md` | ✅ | ❌ | ❌ |
| `agents/pm/` | ✅ | ❌ | ❌ |
| `agents/coder/README.md`（概览） | ✅ | ✅（全部） | ❌ |
| `agents/coder/` 具体规范 | ❌ | ✅（全部） | ❌ |
| `agents/reviewer/` | ❌ | ❌ | ✅ |
| `agents/scheduler/` | ❌ | ❌ | ❌ |
| spark 项目 `docs/` | ❌ | ❌ | ❌ |
| 目标项目 `docs/specs/` | ✅（已有设计） | ✅（PM 产出） | ✅（验证业务逻辑） |
| 目标项目 `docs/plans/` | ✅（已有计划） | ✅（PM 产出） | ❌（含实现步骤，会偏差审查） |
| 目标项目 `src/main/java/` + `pom.xml` | ✅（了解现有结构） | ✅（修改代码） | ✅（审查代码） |

### 关键设计决策

**Reviewer 不读 plan**：plan 包含具体的实现步骤（确切文件路径、代码块、命令），如果 Reviewer 读了 plan，就等同于拿到"标准答案"，会失去审查独立性——它只会对照 plan 检查 coder 有没有照做，而不是从需求和规范的角度独立判断代码是否正确。Reviewer 只读 spec（设计文档）来验证业务逻辑。

## PM 输出路径修正

### 当前（错误）

```
docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md    ← spark 项目根
docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md      ← spark 项目根
```

### 修正后

```
{base_path}/{project_name}/docs/specs/YYYY-MM-DD-<topic>-design.md
{base_path}/{project_name}/docs/plans/YYYY-MM-DD-<topic>-plan.md
```

`output_dir` 由 `build.skill.md` Phase 1 在启动时确定，值为 `{base_path}/{project_name}/`。

## 文件修改清单

### 1. `agents/pm/pm.skill.md`

**删除**（第 58-59 行）：
```
- 检查 `docs/superpowers/specs/` 下是否已有相关设计文档
- 检查 `docs/superpowers/plans/` 下是否已有相关实现计划
```

**替换为**（第一步「探索项目上下文」末尾新增）：
```markdown
## 读取范围

**允许读取：**
- `CLAUDE.md`（项目全局规范说明）
- `agents/pm/pm.skill.md`（自身）
- `agents/coder/README.md`（架构约束概览，用于 spec 中引用编码规范）
- 目标项目 `{output_dir}/docs/` 下已有设计文档（specs/ 和 plans/）
- 目标项目现有代码结构（`{output_dir}/src/main/java/`）

**禁止读取：**
- spark 项目 `docs/` 下任何内容
- `agents/coder/` 下具体规范文件（README.md 除外）
- `agents/reviewer/`、`agents/scheduler/` 下任何内容
```

**修改**（第 118 行 spec 输出路径）：
```
将确认后的设计写入 `{output_dir}/docs/specs/YYYY-MM-DD-<topic>-design.md`。
```

**修改**（第 161 行 plan 输出路径）：
```
spec 确认后，写入 `{output_dir}/docs/plans/YYYY-MM-DD-<topic>-plan.md`。
```

### 2. `agents/coder/coder.skill.md`

在「边界约束」章节前新增「读取范围」章节：

```markdown
## 读取范围

**允许读取：**
- `agents/coder/` 下所有规范文件（按 Phase 0-1 流程按需加载）
- 目标项目 `{output_dir}/docs/specs/` 和 `{output_dir}/docs/plans/`（PM 产出的设计和计划）
- 目标项目 `{output_dir}/src/main/java/` 和 `{output_dir}/pom.xml`（待修改的代码）

**禁止读取：**
- spark 项目 `docs/` 下任何内容
- `agents/pm/`、`agents/reviewer/`、`agents/scheduler/` 下任何内容
- `CLAUDE.md`
```

### 3. `agents/reviewer/review.skill.md`

在「执行流程」前新增「读取范围」章节：

```markdown
## 读取范围

**允许读取：**
- `agents/reviewer/` 下所有文件（审查规范、checklist、check_system）
- 目标项目 `docs/specs/`（对照设计文档验证业务逻辑正确性）
- 目标项目 `src/main/java/` 下所有 Java 文件

**禁止读取：**
- 目标项目 `docs/plans/`（含具体实现步骤，会造成审查偏差）
- spark 项目 `docs/` 下任何内容
- `agents/coder/`、`agents/pm/`、`agents/scheduler/` 下任何内容
- `CLAUDE.md`
```

**修改 Step 2 输入**，增加目标项目 spec：

```markdown
**输入：**
- 目标项目 `docs/specs/` 下的设计文档（验证业务逻辑是否符合需求）
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单
- `review-output/{run_id}/quality.json` — 静态分析结果（如存在）
- `{path}` 下的 Java 源文件
```

### 4. `agents/scheduler/pipeline.yaml`

**Coder prompt_template**（第 41 行），删除模糊约束：
```
3. 禁止读取修改 ./docs 下的所有内容除非用户指定了你能读取和修改的内容路径
```

替换为明确的隔离声明：
```
3. 严格遵守 `agents/coder/coder.skill.md` 中「读取范围」定义的允许和禁止读取列表。
```

同时将禁止修改列表改为引用：
```
2. 禁止修改 agents/ 或 hooks/ 目录下的任何文件。
```

**Reviewer prompt_template**（第 57 行起），在开头新增：
```
严格遵守 `agents/reviewer/review.skill.md` 中「读取范围」定义的允许和禁止读取列表。
```

### 5. `agents/scheduler/build.skill.md`

**Phase 1 第 4 步**（第 78-82 行），更新 spec 和 plan 输出路径的说明：
```
- 输出 spec: `{output_dir}/docs/specs/YYYY-MM-DD-<topic>-design.md`
- 输出 plan: `{output_dir}/docs/plans/YYYY-MM-DD-<topic>-plan.md`
```

## 受影响但不需修改的文件

| 文件 | 原因 |
|------|------|
| `agents/coder/README.md` | 规范索引，职责不变。如需引用隔离规则，指向 `coder.skill.md` |
| `agents/reviewer/README.md` | 说明文档，给人看。规则在 `review.skill.md` 中 |
| `pipeline_engine/` | 调度逻辑不变，`{output_dir}` 模板变量已由 `build.skill.md` 传入 |
| `agents/reviewer/check_system/` | 审查系统代码不受影响，Reviewer Agent 的提示词约束即可 |
