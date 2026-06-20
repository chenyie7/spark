# 重构 Build-Review 流水线：程序预检硬阻断 + 修复循环闭环

## 背景

当前 `/build` 一键流程存在两个核心缺陷：

1. **程序预检（Layer 1 Python CLI）未被强制执行**：`/build` 在 Phase 2 启动 reviewer 子 Agent，在 prompt 中"建议"其执行 CLI。子 Agent 作为 AI 进程可能跳过此步骤，导致预检形同虚设。
2. **修复循环不工作**：预检失败后，coder 未被召回修复。`pre-check-result.json` 可能不存在，Phase 3 判定降级跳过，P0 阻断逻辑失效。

本次重构的目标：**使程序预检成为确定性硬闸门，预检失败立即阻断并回到 coder 修复，直到 P0 清零或达到最大轮次。**

---

## 核心设计决策

### 废弃方案：Docker 容器化 Agent

曾讨论将 coder/reviewer Agent 打包为 Docker 镜像，实现环境隔离和入口脚本强制。**结论：当前阶段为过度设计。**
- 程序检查仅需 Python 3 + PyYAML，无环境冲突
- Docker 无法解决"AI agent 是否执行 CLI"这一核心问题（容器不保证内部 AI 行为）
- 先跑通流程闭环，再考虑容器化

### 保留项

- `agents/reviewer/hooks/settings.template.json` 保留，不删除。未来可能需要重新启用 hook 机制。
- `/review:on` / `/review:off` 功能在 `review.skill.md` 中废弃，但 settings.template.json 文件本身保留。

---

## 架构设计

### 方案 C：`/build` 调度 `Skill("review")`，review 内部强制 Bash 预检

```
/build 调度 Agent（薄，只编排）
  │
  ├─ Phase 1: Agent("coder") → 产出 src/main/java/*.java
  │
  ├─ Phase 2: Skill("review", args="src/main/java")
  │     │
  │     │  /review 技能内部：
  │     │  ┌──────────────────────────────────────────┐
  │     │  │ Step 1: Bash review-pre-hook.sh           │
  │     │  │   python3 -m code_check.cli scan <path>   │
  │     │  │   → exit 0: pre-check-result.json 已生成  │
  │     │  │   → exit 1: pre-check-result.json + .md   │
  │     │  │           （两个文件都已生成，CLI 默认行为） │
  │     │  │           返回失败，/review 终止            │
  │     │  │                                            │
  │     │  │ Step 2: Agent("reviewer AI")              │
  │     │  │   只做 AI 语义检查（17 项）                 │
  │     │  │   读 ai-checklist.yaml + pre-check-result  │
  │     │  │   输出 review-result.json                  │
  │     │  │                                            │
  │     │  │ Step 3: Bash review-post-hook.sh           │
  │     │  │   合并报告 → final-review-report.md         │
  │     │  └──────────────────────────────────────────┘
  │     │
  │     └─ 返回结果给 /build
  │
  ├─ Phase 3: 读取产物，判定
  │     │
  │     │ 读 pre-check-result.json → summary.p0_count
  │     │ 读 review-result.json → summary.fail
  │     │   ├─ p0=0 且 fail=0 → ✅ 完成
  │     │   ├─ p0>0 且 round < max → 🔄 回 Phase 1（coder 修复）
  │     │   ├─ fail>0 且 round < max → 🔄 回 Phase 1（coder 修复）
  │     │   └─ round >= max → ❌ 超限，展示报告
  │     │
  │     └─（CLI 已在 exit 1 时输出 JSON，判定入口统一）
  │
  └─ Phase 4（修复轮）: Agent("coder", review_context=问题列表)
```

### 关键设计点

**强制发生在 Skill 层，不是 AI Agent 层。** `/review` 作为一个 Skill，在执行 AI 子 Agent 之前，先通过 Bash 工具直接执行 Python CLI。Bash 工具调用是确定性的，不依赖 AI 自觉。

**调度 Agent 保持薄层。** `/build` 只知道"调用 review 技能"和"读 JSON 文件判断 P0"，不关心 review 内部如何执行预检。

**产物文件作为 Agent 间契约。** coder → review → coder 之间通过 `review-output/` 下的 JSON 文件传递状态，不依赖内存或 prompt 透传。

---

## 判定矩阵

`/build` Phase 3 统一读 `pre-check-result.json` 做判定：

| pre-check p0 | AI check fail | round < max | 动作 |
|-------------|---------------|-------------|------|
| 0 | 0 | - | ✅ 完成 |
| 0 | >0 | Y | 🔄 回 coder（AI 问题） |
| 0 | >0 | N | ❌ 超限，展示报告 |
| >0 | - | Y | 🔄 回 coder（程序问题优先） |
| >0 | - | N | ❌ 超限，展示报告 |

> 注：CLI 在 exit 1 时已输出 `pre-check-result.json`（包含 p0_count），所以 Phase 3 始终可以统一读 JSON。不需要两套判定逻辑。

---

## 修复轮 Coder Prompt 模板

从 `pre-check-result.json` 和 `review-result.json` 中提取问题，格式化后填入 coder prompt：

```
{requirement}

⚠️ 这是第 {round}/{max_retries} 轮修复。以下是上一轮审查发现的问题：

## 程序预检问题（{p0_pre} 个 P0, {p1_pre} 个 P1）

| # | 文件 | 行号 | 方法 | 级别 | 规则 | 问题 |
|---|------|------|------|------|------|------|
| 1 | UserController.java | 42 | getUser | 🔴 P0 | PKG-001 | 包结构不符合规范 |
| 2 | UserService.java | 15 | — | 🔴 P0 | INJ-001 | 未使用构造注入 |

## AI 语义检查问题（{p0_ai} 个 FAIL）

| # | 文件 | 行号 | 类别 | 规则 | 问题 | 建议 |
|---|------|------|------|------|------|------|
| 1 | UserController.java | 50 | quality | ERR-001 | 异常信息不规范 | 使用 BusinessException |

## 修复原则
1. 只修改上述有问题的文件和行，不动其他代码
2. 修复后必须重新符合 agents/coder/ 下的所有规范
3. 如果同一文件有多个问题，一次性全部修复
4. 不确定的改动，加注释说明原因
```

数据来源映射：
- 程序预检问题 → `pre-check-result.json` 的 `file_reports[].findings[]`（字段：file, line, method, level, code, message）
- AI 检查问题 → `review-result.json` 的 `items[]`（字段：file, line, category, code, evidence, suggestion）

---

## 数据模型（现有，无需改动）

### pre-check-result.json 结构

```json
{
  "metadata": { "module": "...", "scan_scope": {...}, "passed": false, ... },
  "file_reports": [
    {
      "file": "src/main/java/com/example/controller/UserController.java",
      "findings": [
        {
          "code": "PKG-001",
          "level": "P0",
          "line": 42,
          "message": "包结构不符合规范",
          "evidence": "package com.xxx.controller;",
          "method": "getUser"
        }
      ]
    }
  ],
  "summary": {
    "total_checks": 9, "passed": 7,
    "failed": [{"code": "PKG-001", "level": "P0", "line": 42, ...}, ...]
  },
  "hints_for_ai": [
    { "file": "...", "line": 42, "code": "PKG-001", "snippet": "..." }
  ]
}
```

> CLi 当前在 `output_format=json`（默认）时，无论 pass 或 fail 都会先写入该 JSON，再根据 passed 决定 exit code。行为无需修改。

### review-result.json 结构

```json
{
  "metadata": { "module": "...", "precheck_passed": false, ... },
  "items": [
    {
      "code": "ERR-001", "category": "quality", "result": "FAIL",
      "file": "UserController.java", "line": 50,
      "evidence": "throw new RuntimeException(...)", "suggestion": "使用 BusinessException 替代"
    }
  ],
  "summary": { "total": 17, "pass": 15, "fail": 2, "na": 0 }
}
```

---

## 错误处理矩阵

### `/review` 内部错误

| 场景 | 表现 | 处理 |
|------|------|------|
| python3 不可用 | Step 1 exit 127 | `/review` 返回错误。`/build` 展示「需要 Python 3 环境」，停止流水线 |
| 扫描路径无 .java 文件 | CLI exit 0，summary 文件数=0 | `/review` 返回警告。`/build` 判定 coder 未产出代码，回 coder |
| CLI Python 异常崩溃 | exit 1，pre-check-result.json 未生成 | `/review` Step 1 检测 JSON 缺失 → 判定「CLI 异常」，终止。`/build` 展示 stderr，停止（工具问题，不循环） |
| pre-check-result.json 格式异常 | JSON 存在但缺必要字段 | `/review` Step 2 做 schema 校验，失败 → 降级跳过 AI 检查，直接返回 pre-check 结果 |
| reviewer AI 未生成 review-result.json | Step 2 完成但文件缺失 | `/review` Step 3 用 `--pre` only 生成报告。`/build` 只展示程序检查结果，不进入修复循环（AI 无产出不循环） |
| reviewer AI 超时 | Step 2 > 600s | 保留已生成产物，`/build` 展示「审查超时」，停止 |

### `/build` 调度层错误

| 场景 | 处理 |
|------|------|
| coder 未生成 .java 文件 | 不进入 Phase 2。告知用户，停止流水线 |
| coder 子 Agent 超时（900s） | 告知用户超时，保留已生成文件，停止 |
| Skill("review") 调用失败 | 环境问题→停止；代码问题→正常走修复循环 |
| 修复后 P0 不变/反增 | 继续循环，不特殊处理。max_retries 是唯一硬上限 |
| max_retries 耗尽 | 展示最终报告，列出剩余 P0/P1，提示用户手动介入 |
| 用户 Ctrl+C | 保留当前轮产物（review-output/），展示已完成轮次总结 |

### 产物文件组合速查

| pre-check-result.json | review-result.json | 含义 | 动作 |
|----------------------|-------------------|------|------|
| 存在，p0=0 | 存在，p0=0 | 全绿 | ✅ 完成 |
| 存在，p0=0 | 存在，p0>0 | 程序OK，AI有建议 | 🔄 回 coder |
| 存在，p0>0 | 存在 | 程序有问题 | 🔄 回 coder（优先程序问题） |
| 存在，p0>0 | 不存在 | 程序有问题，AI未跑 | 🔄 回 coder（程序问题） |
| 不存在 | - | CLI 异常崩溃 | 🛑 停止，报工具错误 |

---

## 改动范围

| 文件 | 改动类型 | 改动内容 |
|------|---------|----------|
| `agents/scheduler/build.skill.md` | 重构 | Phase 2 改为 `Skill("review")` 调用；Phase 3 统一读 JSON 判定；新增修复轮 coder prompt 构造逻辑 |
| `agents/scheduler/pipeline.yaml` | 更新 | reviewer 节点 prompt_template 去掉 CLI 指令，只保留 AI 语义检查 |
| `agents/reviewer/review.skill.md` | 简化 | Step 1 Bash 保留，Step 2 AI Agent 保留，移除 `/review:on` 和 `/review:off` 用法说明 |
| CLI/数据模型 | **不改** | 现有 `Finding`/`FileReport`/`ScanResult` 数据结构已满足需求，CLI 已在 exit 1 时输出 JSON |

### 明确不改

- `code-check-config.yaml` — 配置不变
- `code_check/` 下的 Python 代码 — CLI 行为不变
- `agents/reviewer/hooks/settings.template.json` — 保留文件，不在本文档范围内废弃
- `agents/coder/` — 规范文件不改
- 不引入 Docker、不引入新组件

---

## 不做的事（YAGNI）

- 不做自动合并修复（AI 自动修 pre-check 问题）— 必须回 coder 完整走一轮
- 不做增量扫描 — 每轮全量扫描
- 不做 P1 阻断 — 当前 `block_on: [P0]`，P1 记录但不触发修复循环
- 不做并行修复（多 Agent 同时修不同文件）— 单 Agent 顺序修复
