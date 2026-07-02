# PM Agent 设计规格

**日期**: 2026-06-25  
**状态**: 已确认  
**目标**: 在 `/build` 流水线中新增 PM Agent，实现「需求对话 → spec 设计文档 → plan 实现计划」完整链路

---

## 1. 概述

将 superpowers 插件中 brainstorming + writing-plans 的核心逻辑抽取为独立 PM Agent，嵌入到 `/build` 命令中，形成 `PM（需求对话）→ Coder（代码生成）→ Reviewer（代码审查）` 三段式自动化流水线。

### 设计原则

| 原则 | 说明 |
|------|------|
| **主 Agent 纯调度，零交互** | 主 Agent 上下文只含调度逻辑，需求对话在 PM 阶段独立完成 |
| **单入口** | 用户只需 `/build`，无需理解内部阶段切换 |
| **跨轮次流转** | PM 完成 → 用户输入 `/build --resume` → 自动进入 coder/reviewer |
| **零外部依赖** | PM Agent 不依赖 superpowers 插件 |
| **pipeline_engine 不改动** | PM 阶段在 pipeline_engine 启动之前处理，pipeline_engine 只管理 coder ↔ reviewer |

---

## 2. 核心流程

```
用户输入
   │
   ├── /build "做一个后台管理系统"（有需求描述）
   │         │
   │         └──→ Phase 1: PM 需求对话（主线，用户交互）
   │                 逐轮问答，产出 spec + plan
   │                 提示: 「需求梳理完毕，运行 /build --resume <run_id> 开始开发」
   │                    │
   │                    └──→ Phase 2: /build --resume <run_id>
   │                              │
   │                              ├── Coder（subagent，读 spec/plan 写代码）
   │                              └── Reviewer（subagent，审查 + 修复循环）
   │                                    │
   │                                    └──→ DONE
   │
   └── /build（无参数）
             │
             ├── 提示: 「请描述你要构建的需求，我会和你讨论具体内容后开始开发。」
             └── 等待用户下一行输入 → 进入 Phase 1
```

### 三种入口行为

| 入口 | 行为 |
|------|------|
| `/build "具体需求"` | 生成 run_id，直接启动 PM 开始需求对话 |
| `/build`（无参数） | 输出提示，引导用户描述需求 |
| `/build --resume <run_id>` | 跳过 PM，从 pipeline_engine coder/reviewer 恢复 |
| `/build --pm <run_id>` | 恢复未完成的 PM 对话 |

---

## 3. 轮次流转

```
第 N 轮:   /build "需求描述"
           └── Phase 1: PM 需求对话（主线，多轮交互）
                └── 产出 spec + plan 到 docs/superpowers/
                └── pm-context.json 写入 review-output/{run_id}/
                └── 输出: 「需求梳理完毕，运行 /build --resume {run_id} 开始开发」

第 N+1 轮: /build --resume {run_id}
           └── Phase 2: pipeline_engine start
                └── Coder subagent → Reviewer subagent → DONE
```

### 状态文件

```
review-output/{run_id}/
├── pm-context.json            ← PM 阶段状态（新文件）
│   { "status": "done" | "interrupted",
│     "run_id": "...",
│     "spec_file": "docs/superpowers/specs/...",
│     "plan_file": "docs/superpowers/plans/..." }
│
├── pipeline-state.json        ← pipeline_engine 状态（现有，不改动）
├── findings.json              ← reviewer 审查结果（现有）
└── final-review-report.md     ← 最终报告（现有）
```

---

## 4. 文件变更

### 4.1 需新增的文件

| 文件 | 说明 |
|------|------|
| `agents/pm/pm.skill.md` | PM Agent 定义文件，从 superpowers brainstorming + writing-plans 抽取核心逻辑 |
| `.claude/skills/pm/SKILL.md` | symlink → `../../agents/pm/pm.skill.md`，使 `/pm` 命令可用 |

### 4.2 需修改的文件

| 文件 | 变更内容 |
|------|---------|
| `agents/scheduler/build.skill.md` | 增加 Phase 1 PM 需求对话阶段，修改入口判断逻辑 |
| `.claude/settings.json` | PreToolUse hook 规则需要允许创建 `agents/pm/` 目录下的文件 |
| `CLAUDE.md` | 更新流水线描述，将 PM 加入三阶段流程 |

### 4.3 不需改动的文件

| 文件/目录 | 原因 |
|-----------|------|
| `agents/scheduler/pipeline_engine/` | PM 在 pipeline_engine 之前处理，pipeline_engine 只管理 coder ↔ reviewer |
| `agents/scheduler/pipeline.yaml` | 同上，PM 不作为 pipeline 节点 |
| `agents/reviewer/` | 审查逻辑不变 |
| `agents/coder/` | 代码生成逻辑不变 |

### 4.4 完整变更清单

```
新增:
  agents/pm/pm.skill.md                ← PM Agent 核心定义（~120行）
  .claude/skills/pm/SKILL.md           ← symlink

修改:
  agents/scheduler/build.skill.md      ← 入口逻辑：PM phase + pipeline phase
  .claude/settings.json                ← hook 白名单放宽
  CLAUDE.md                            ← 流水线描述更新

不改动:
  agents/scheduler/pipeline_engine/    ← 零改动
  agents/scheduler/pipeline.yaml       ← 零改动
  agents/reviewer/                     ← 零改动
  agents/coder/                        ← 零改动
```

---

## 5. PM Agent 内部流程

从 superpowers brainstorming + writing-plans 抽取，去除 visual-companion、subagent-driven 等非必要部分。

```
PM 启动（收到需求描述）
  │
  ├── 第一步: 探索项目上下文
  │     检查现有代码、CLAUDE.md、agents/coder/ 规范、已有设计文档
  │
  ├── 第二步: 逐轮澄清需求
  │     一次只问一个问题
  │     优先多选（2-4 个选项），其次开放式
  │     覆盖：目的、用户角色、核心功能、约束条件、成功标准
  │
  ├── 第三步: 提出 2-3 种方案对比
  │     各有优缺点 + 推荐理由
  │
  ├── 第四步: 逐节确认设计
  │     架构 → 数据模型 → API → 数据流 → 错误处理 → 测试
  │     每节等用户确认
  │
  ├── 第五步: 写入 spec
  │     路径: docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
  │     自检: placeholder、内部矛盾、歧义、范围
  │
  ├── 第六步: 用户 review spec → 确认或修改
  │
  ├── 第七步: 写入 plan
  │     路径: docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md
  │     包含: 文件结构、bite-size 任务、代码示例、测试命令
  │     自检: spec 覆盖、placeholder、类型一致性
  │
  └── 第八步: 衔接
         更新 pm-context.json
         提示用户运行 /build --resume <run_id>
```

---

## 6. 与现有 hook 的兼容

### 问题

`.claude/settings.json` 配置了 PreToolUse hook，拦截所有对 `agents/` 目录的 Write/Edit 操作。创建 `agents/pm/pm.skill.md` 时会被拦截。

### 解决方案

修改 `hooks/block-agents-write.sh`，增加例外规则：
- 允许写入 `agents/pm/` 目录（PM Agent 文件）
- 或者：检查调用者身份，仅拦截 subagent 发起的写入

实际采用方案：在 hook 脚本中增加白名单目录 `agents/pm/`。

---

## 7. 刻意舍弃的 superpowers 内容

| 舍弃 | 原因 |
|------|------|
| visual-companion.md | PM 不需要浏览器可视化 |
| subagent-driven-development | 不是 PM 职责 |
| executing-plans | PM 只管到 plan 文档 |
| requesting/receiving-code-review | Review 阶段已有独立 agent |
| test-driven-development | 已在 coder 规范约束中 |
| systematic-debugging | 独立功能 |
| dispatching-parallel-agents | 独立功能 |
| using-git-worktrees | 独立功能 |
| finishing-a-development-branch | 独立功能 |
| verification-before-completion | 独立功能 |

---

## 8. 后续扩展

支持 PM 作为独立命令调用（不通过 /build）：

```
/pm <需求>  → 仅执行 PM 流程，产出 spec + plan，不触发开发
```

---

## 9. spec 自检结果

- ✅ 无 placeholder（TBD、TODO）
- ✅ 内部一致：Phase 1/2 划分清晰，状态文件定义明确
- ✅ 范围恰当：仅 PM Agent 定义 + build skill 适配，不涉及 pipeline_engine
- ✅ 无歧义：三种入口行为表明确，轮次流转图清晰
