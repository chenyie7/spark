# PM Agent 实现计划

> **目标:** 在 `/build` 流水线中集成 PM Agent，实现「需求对话 → spec → plan → coder → reviewer」完整链路

**架构方案:** PM 阶段在 pipeline_engine 启动之前由 build skill 主线处理（用户交互），完成后产出 spec+plan，再通过 pipeline_engine 启动 coder/reviewer。pipeline_engine 和 pipeline.yaml 完全不改动。

**涉及文件（5 个）:**

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `agents/pm/pm.skill.md` | PM Agent 核心定义，约 120 行 |
| 新增 | `.claude/skills/pm/SKILL.md` | symlink → PM Agent |
| 修改 | `agents/scheduler/build.skill.md` | 入口逻辑：增加 PM 阶段 |
| 修改 | `hooks/block-agents-write.sh` | 白名单放行 agents/pm/ |
| 修改 | `CLAUDE.md` | 流水线描述更新为 PM → Coder → Reviewer |

---

### 任务 1: 创建 PM Agent 技能文件

**文件:**
- 创建: `agents/pm/pm.skill.md`

**说明:** 从 superpowers brainstorming + writing-plans 抽取核心逻辑，去除 visual-companion、subagent-driven、executing-plans 等依赖。PM Agent 负责需求沟通、方案对比、设计确认、文档输出。

- [ ] **步骤 1: 写入 pm.skill.md**

```markdown
---
name: pm
description: 需求沟通 Agent — 和用户对话澄清需求，产出 spec 设计文档和 plan 实现计划
---

# PM — 需求沟通与文档化

## 角色

你是 PM Agent，负责和用户沟通需求，将模糊的想法转化为结构化的设计文档和实现计划。你的产出是 coder 和 reviewer 的输入。

## 核心原则

- **一次只问一个问题** — 不要一次抛出多个问题
- **优先多选** — 提供 2-4 个选项比开放式更高效
- **YAGNI 严格** — 移除不必要的功能
- **逐节确认** — 每部分设计都等用户确认再继续
- **独立运行** — 不依赖 superpowers 插件

## 流程

### 第一步: 探索项目上下文
- 检查现有代码结构（src/main/java 下的包路径）
- 读取 CLAUDE.md 了解项目规范
- 读取 agents/coder/README.md 了解架构约束
- 检查 docs/superpowers/specs/ 下已有设计文档

### 第二步: 逐轮澄清需求（一次一问）
- 覆盖：目的、用户角色、核心功能、非功能需求、约束条件
- 对于多子系统项目，帮助用户拆分为独立的子项目
- 每个子项目走独立的 spec → plan 周期

### 第三步: 提出 2-3 种方案对比
- 各有优缺点 + 推荐理由
- 用户选择后进入设计确认

### 第四步: 逐节确认设计（每节等用户确认）
- 架构概览（项目结构、模块划分、技术选型）
- 数据模型（表设计、实体关系）
- API 设计（接口清单、URL 规范）
- 数据流（关键业务流程）
- 错误处理策略
- 测试策略

### 第五步: 写入 spec 设计文档
- 路径: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- 包含：概述、技术栈、功能范围、表设计、API 接口、项目结构、架构约束、数据流、不做范围

### 第六步: spec 自检
- 扫描 "TBD"、"TODO"、不完整的章节 → 修复
- 检查内部一致性（架构是否匹配功能描述）
- 检查范围是否合理
- 检查歧义 → 明确化

### 第七步: 用户 review spec
- 展示 spec 路径，等待用户确认或修改

### 第八步: 写入 plan 实现计划
- 路径: `docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md`
- 包含：目标、架构、技术栈、文件结构、bite-size 任务、代码示例、测试命令

### 第九步: plan 自检
- spec 覆盖：每个 spec 要求是否有对应任务
- placeholder 扫描：无 "TBD"、"TODO"、"implement later"
- 类型一致性：后续任务引用的类型在前序任务中已定义

### 第十步: 衔接流水线
- 更新 `review-output/{run_id}/pm-context.json`（标记 PM 完成）
- 输出产物路径
- 提示用户：**「需求梳理完毕，运行 /build --resume {run_id} 开始开发」**
    - 在消息中直接给出可执行的完整命令，用户只需回车
```

- [ ] **步骤 2: 验证文件**

```bash
wc -l agents/pm/pm.skill.md
```

预期: 约 80-100 行

- [ ] **步骤 3: 提交**

```bash
git add agents/pm/pm.skill.md
git commit -m "feat: 新增 PM Agent 技能文件 — 需求沟通 → spec → plan"
```

---

### 任务 2: 创建技能 symlink

**文件:**
- 创建: `.claude/skills/pm/SKILL.md`

- [ ] **步骤 1: 创建目录和 symlink**

```bash
mkdir -p .claude/skills/pm
ln -sf ../../agents/pm/pm.skill.md .claude/skills/pm/SKILL.md
```

- [ ] **步骤 2: 验证 symlink 可解析**

```bash
head -5 .claude/skills/pm/SKILL.md
```

预期: 显示 pm.skill.md 的 frontmatter

- [ ] **步骤 3: 提交**

```bash
git add .claude/skills/pm/SKILL.md
git commit -m "feat: 添加 /pm 技能 symlink 指向 PM Agent"
```

---

### 任务 3: 更新 build skill 入口逻辑

**文件:**
- 修改: `agents/scheduler/build.skill.md`

**说明:** 将 PM 阶段集成到 build skill 入口。在 pipeline_engine 启动之前判断是否需要 PM 需求对话。`--resume` 跳过 PM，`--pm` 恢复 PM。

- [ ] **步骤 1: 读取当前 build.skill.md 完整内容**

```bash
cat agents/scheduler/build.skill.md
```

- [ ] **步骤 2: 使用 Edit 替换完整文件内容**

新内容如下（注意这是对现有 build.skill.md 的全部替换，不是新增文件）：

```markdown
---
name: build
description: 自动化代码生成流水线 — PM 需求沟通 → coder 生成 → reviewer 审查 → 自动修复循环
---

# /build — 自动化代码生成流水线

用法：`/build <需求描述> [--target-dir <目录>]`
恢复：`/build --resume <run_id>`
恢复 PM：`/build --pm <run_id>`

通过 `pipeline_engine` CLI 管理 coder → reviewer 阶段的 DAG 调度。PM 阶段在 pipeline_engine 之前处理。

---

## 入口判断

```
/build 调用
  │
  ├── --resume <run_id>  → 跳过 PM，进入 Phase 2: coder/reviewer
  │
  ├── --pm <run_id>      → 恢复 PM 需求对话（继续未完成的 PM 阶段）
  │
  ├── 有需求描述          → Phase 1: PM 需求对话
  │     └── PM 完成 → 提示用户运行 --resume → Phase 2
  │
  └── 无需求描述          → 提示用户描述需求
        └── 用户回复 → Phase 1: PM 需求对话
              └── PM 完成 → 提示用户运行 --resume → Phase 2
```

---

## Phase 1: PM 需求对话

**触发条件:** `/build "需求"` 或 `/build`（无参数，用户后续输入需求后自动触发）

**流程:**

1. 生成 run_id
2. 创建 `review-output/{run_id}/` 目录
3. 写入 `review-output/{run_id}/pm-context.json`
4. 加载 PM Agent 流程（参考 agents/pm/pm.skill.md），以用户需求为起点进行对话：
   - 探索项目上下文
   - 逐轮澄清需求（一次一问）
   - 提出方案对比
   - 逐节确认设计
   - 输出 spec: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
   - 输出 plan: `docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md`
   - spec/plan 自检
5. 更新 `pm-context.json`：status → "done"，记录 spec_file 和 plan_file 绝对路径
6. **输出：需求梳理完毕，运行以下命令开始开发：**

   ```
   /build --resume {run_id}
   ```

7. 等待用户输入恢复命令

**pm-context.json 格式:**

```json
{
  "run_id": "20260625143000-admin-test",
  "status": "done",
  "spec_file": "docs/superpowers/specs/2026-06-25-admin-system-design.md",
  "plan_file": "docs/superpowers/plans/2026-06-25-admin-system-plan.md",
  "target_dir": "admin-test",
  "requirement": "用户原始需求描述"
}
```

---

## Phase 2: Coder / Reviewer 自动流水线

**触发条件:** `/build --resume <run_id>`

**流程:**

1. 读取 `review-output/{run_id}/pm-context.json` 获取 spec/plan 路径
2. 检查 `review-output/{run_id}/pipeline-state.json` 是否存在
   - 不存在 → 初始化 pipeline_engine:
     ```bash
     PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
     python3 -m pipeline_engine.cli start \
       --pipeline agents/scheduler/pipeline.yaml \
       --state-file review-output/{run_id}/pipeline-state.json \
       --target-dir "{target_dir}" \
       --requirement "{spec_file}::{plan_file}::{原始需求}"
     ```
   - 存在 → 继续当前进度

3. 执行循环（同现有逻辑）:
   ```
   loop:
     1. python3 -m pipeline_engine.cli next \
          --pipeline agents/scheduler/pipeline.yaml \
          --state-file review-output/{run_id}/pipeline-state.json
   
     2. 解析返回 JSON:
        action=="done"  → 读取 final-review-report.md 展示结果
        action=="error" → 展示错误信息
        action=="execute" → 对每个 node:
          a. 通过 Agent 工具启动子 Agent（subagent_type = agent_type）
          b. 等待子 Agent 完成，提取最终回复
          c. 判断 verdict（REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR）
          d. python3 -m pipeline_engine.cli report \
               --node {node_id} --status {success|failed|error} \
               --summary "{简要描述}" --verdict {verdict}
     3. 回到步骤 1
   ```

### 终止条件

- `next` 返回 `action=="done"` → 读取 `review-output/{run_id}/final-review-report.md` 展示结果
- `next` 返回 `action=="error"` → 展示错误信息，提示用户介入

---

## Phase 0: 参数解析

`--target-dir` 参数解析：
- 如果用户指定了 `--target-dir <值>`，直接使用
- 如果未指定，询问用户一次「是否需要自定义代码输出目录？（默认: 项目根目录）」
  - 用户输入了目录 → 使用
  - 用户直接回车/说"不" → 使用默认值 "."

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 「请描述你要构建的需求，我会和你讨论具体内容后开始开发。」 |
| PM 阶段用户中断 | pm-context.json 保留，`/build --pm <run_id>` 恢复 |
| pipeline_engine 命令失败 | 检查 python3 和 PyYAML 是否可用，展示 stderr |
| `next` 返回 error | 展示 message，询问是否 reset 重来 |
| 子 Agent 超时 | report status=error，让调度器决定下一步 |
| 子 Agent 未生成文件 | report status=failed（非 error），进入修复循环 |
```

- [ ] **步骤 3: 验证行数**

```bash
wc -l agents/scheduler/build.skill.md
```

- [ ] **步骤 4: 对照 spec 自检**

| spec 要求 | build.skill.md 是否覆盖 |
|-----------|------------------------|
| `/build` 无参数 → 提示用户 | ✅ Phase 1 |
| `/build "需求"` → PM 模式 | ✅ Phase 1 |
| `/build --resume <run_id>` → 跳过 PM | ✅ Phase 2 |
| `/build --pm <run_id>` → 恢复 PM | ✅ 入口判断 |
| PM 产出 spec + plan | ✅ Phase 1 步骤 4 |
| pipeline_engine 只管理 coder/reviewer | ✅ Phase 2 |
| pm-context.json 状态文件 | ✅ Phase 1 步骤 3/5 |

- [ ] **步骤 5: 提交**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: /build 集成 PM Agent 需求对话阶段

/build 入口统一处理:
- /build <需求>  → PM 需求对话 → spec + plan → 提示 resume
- /build          → 引导用户描述需求
- /build --resume → 跳过 PM，进入 coder/reviewer 流水线
- /build --pm     → 恢复中断的 PM 对话

pipeline_engine 不受影响，只管理 coder ↔ reviewer 阶段"
```

---

### 任务 4: 更新 hook 白名单

**文件:**
- 修改: `hooks/block-agents-write.sh`

**问题:** PreToolUse hook 拦截所有对 `agents/` 目录的 Write/Edit 操作，创建 `agents/pm/pm.skill.md` 时会被阻止。

**解决方案:** 在 hook 脚本中增加白名单，允许写入 `agents/pm/` 目录。

- [ ] **步骤 1: 读取当前 hook 脚本**

```bash
cat hooks/block-agents-write.sh
```

- [ ] **步骤 2: 在拦截判断之前增加白名单检查**

在 `hooks/block-agents-write.sh` 中，`case "$RESOLVED" in` 语句之前增加：

```bash
# 白名单: 允许写入特定 agent 目录（PM Agent 等新增 agent 的安装）
PM_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/agents/pm/"
case "$RESOLVED" in
    "$PM_DIR"*)
        exit 0
        ;;
esac
```

完整改动：在脚本第 30 行（`case "$RESOLVED" in`）之前插入以上代码块。

- [ ] **步骤 3: 验证 hook 语法**

```bash
bash -n hooks/block-agents-write.sh
```

预期: 无输出（语法正确）

- [ ] **步骤 4: 提交**

```bash
git add hooks/block-agents-write.sh
git commit -m "feat: hook 白名单放行 agents/pm/ 目录写入

PM Agent 文件位于 agents/pm/，需要在 hook 中放行。
白名单仅限 agents/pm/，不影响其他 agents/ 子目录的保护。"
```

---

### 任务 5: 更新 CLAUDE.md

**文件:**
- 修改: `CLAUDE.md`

**说明:** 在 CLAUDE.md 中更新流水线描述，反映新的 PM → Coder → Reviewer 三阶段架构。

- [ ] **步骤 1: 读取当前 CLAUDE.md 中需要修改的部分**

```bash
grep -n "阶段 1\|阶段 2\|阶段 3\|coder\|reviewer\|analyst" CLAUDE.md | head -20
```

- [ ] **步骤 2: 修改"开发流程"部分**

将现有的开发流程描述替换为：

```markdown
### 开发流程

🚀 **一键流程**：`/build <需求描述>` — 自动执行 PM（需求对话）→ Coder（代码生成）→ Reviewer（审查修复）
  入口：`agents/scheduler/build.skill.md`

```
阶段 1（PM）：需求沟通 → spec 设计文档 → plan 实现计划
  入口：agents/pm/pm.skill.md

阶段 2（coder）：读 spec + plan，按架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 3（reviewer）：双层审查 — coder 产出 → 审查 → 修复循环
  入口：agents/reviewer/README.md
```
```

- [ ] **步骤 3: 更新"目录结构"中的 agents 描述**

```markdown
agents/
├── pm/                          # 需求沟通（新增）
│   └── pm.skill.md              # PM Agent 技能定义
├── coder/                       # 架构约束
│   └── ...
├── reviewer/                    # 代码审计
│   └── ...
└── scheduler/                   # 调度器
    └── ...
```

- [ ] **步骤 4: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 反映 PM → Coder → Reviewer 三阶段流水线"
```

---

### 任务 6: 集成测试

**文件:**
- 无（仅测试）

- [ ] **步骤 1: 测试 /build 无参数**

输入 `/build`，验证输出为:
```
请描述你要构建的需求，我会和你讨论具体内容后开始开发。
```

- [ ] **步骤 2: 测试 /build 有需求**

输入 `/build 添加一个健康检查接口`，验证:
- PM Agent 加载并开始提问（探索上下文 + 逐轮澄清）
- PM 产出 spec 和 plan 文件
- PM 提示运行 `/build --resume <run_id>`

- [ ] **步骤 3: 测试 /build --resume**

输入 `/build --resume <run_id>`，验证:
- 跳过 PM，直接进入 coder 阶段
- Coder 读取 spec/plan 生成代码
- Reviewer 审查代码
- 流水线正常完成

- [ ] **步骤 4: 测试 PM 中断恢复**

在 PM 对话中 Ctrl+C 中断，验证:
```bash
cat review-output/<run_id>/pm-context.json  # status 应为 "interrupted"
```
输入 `/build --pm <run_id>`，验证 PM 恢复对话。

- [ ] **步骤 5: 测试 hook 不拦截 PM 文件创建**

```bash
# 验证可以正常创建 agents/pm/pm.skill.md
ls agents/pm/pm.skill.md
```

预期: 文件存在

---

### 任务 7: 最终提交

- [ ] **步骤 1: 确认所有文件变更**

```bash
git status
git diff --stat
```

预期变更清单:
```
新增:
  agents/pm/pm.skill.md
  .claude/skills/pm/SKILL.md

修改:
  agents/scheduler/build.skill.md
  hooks/block-agents-write.sh
  CLAUDE.md
```

- [ ] **步骤 2: 确认不改动的文件**

```bash
# 以下文件应无改动
git diff agents/scheduler/pipeline_engine/
git diff agents/scheduler/pipeline.yaml
git diff agents/reviewer/
```

预期: 无输出（零改动）

- [ ] **步骤 3: 最终提交（如果有未提交的变更）**

```bash
git add -A
git commit -m "feat: 完成 PM Agent 集成 — 需求 → spec → plan → coder → reviewer"
```
