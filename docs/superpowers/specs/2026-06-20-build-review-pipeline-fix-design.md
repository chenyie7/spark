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

### 核心思路

| 角色 | 职责 | 不做什么 |
|------|------|---------|
| `/build` 主控 Agent | 启停 Agent、看 pass/fail、计轮次 | 不读 JSON、不验证产物、不构造问题详情 |
| `Agent("coder")` | 写代码 / 读 `review-output/` 产物修复代码 | — |
| `Agent("review")` | 内部调 `Skill("review")`，跑完返回 PASS 或 FAIL | — |
| `Skill("review")` | Step 1 Bash CLI（强制）→ Step 2 AI 检查 → Step 3 合并报告 | — |

**强制发生在 Skill 层**：`/review` 技能内部用 Bash 工具直接执行 Python CLI，不依赖 AI 自觉。

**子进程隔离 + 通知**：`Agent` 工具天然提供子进程隔离，子 Agent 完成后结果返回父 Agent，父 Agent 根据 pass/fail 决定下一步。

### 架构图

```
/build 主控 Agent（编排 + 计数，不碰产物文件）
  │
  ├─ Phase 1: 启动 Agent("coder")
  │     prompt: 写 Java 代码到 src/main/java/
  │     coder 写完 → 返回
  │     主控检查：有 .java 文件产出？
  │       ├─ 无 → "未生成代码文件"，停止
  │       └─ 有 → 继续
  │
  ├─ Phase 2: 启动 Agent("review")
  │     │
  │     │  review Agent（子进程）内部：
  │     │  ┌────────────────────────────────────────────┐
  │     │  │ Skill("review", args="src/main/java")       │
  │     │  │                                              │
  │     │  │  /review 技能内部：                           │
  │     │  │  Step 1: Bash review-pre-hook.sh             │
  │     │  │    python3 -m code_check.cli scan <path>     │
  │     │  │    → exit 0: pre-check-result.json 已生成    │
  │     │  │    → exit 1: pre-check-result.json + .md     │
  │     │  │           返回 "REVIEW_FAILED"               │
  │     │  │                                              │
  │     │  │  Step 2: AI 语义检查（仅 Step 1 通过时执行）  │
  │     │  │    读 ai-checklist.yaml + pre-check-result   │
  │     │  │    输出 review-result.json                   │
  │     │  │                                              │
  │     │  │  Step 3: Bash review-post-hook.sh            │
  │     │  │    合并报告 → final-review-report.md          │
  │     │  │    返回 "REVIEW_PASSED"                      │
  │     │  └────────────────────────────────────────────┘
  │     │
  │     └─ 返回给主控：
  │          "REVIEW_PASSED"  → P0=0, 无阻断
  │          "REVIEW_FAILED"  → 有阻断，产物在 review-output/
  │          "REVIEW_ERROR"   → 环境/工具异常
  │
  ├─ Phase 3: 主控判定
  │     收到 review Agent 的返回结果：
  │       ├─ "REVIEW_PASSED" → ✅ 展示 final-review-report.md，完成
  │       ├─ "REVIEW_FAILED" + round < max_retries
  │       │     → 🔄 round++，进入 Phase 4（coder 修复）
  │       ├─ "REVIEW_FAILED" + round >= max_retries
  │       │     → ❌ 展示报告，提示用户手动介入
  │       └─ "REVIEW_ERROR" → 🛑 告知用户异常，停止
  │
  └─ Phase 4（修复轮）: 启动 Agent("coder")
        prompt 中包含：
        - 原始需求
        - 当前轮次 round/max_retries
        - 引导 coder 自己去读 review-output/ 下的产物：
          "请先读取 review-output/pre-check-result.json 和
           review-output/review-result.json，了解上一轮审查
           发现的问题，然后逐个修复。"
        coder 修完 → 返回 → 回到 Phase 2 重新审查
```

### 关键设计点

1. **Agent + Skill 组合**：Agent 提供子进程隔离和通知机制；Skill 提供结构化的强制执行步骤。没有冲突。
2. **主控极度薄**：只做启停、看 PASS/FAIL、计轮次。不读 JSON、不构造问题、不验证产物。如果 review 没有产出，告知用户即可，主控不自行为试图诊断。
3. **Coder 自己读产物**：修复轮的 coder Agent 自己去读 `review-output/` 下的 JSON 文件，获取具体问题（文件、行号、规则、描述）。主控不代为提取和格式化。
4. **产物文件作为 Agent 间契约**：coder → review → coder 之间通过 `review-output/` 下的文件传递状态。
5. **通知格式极简**：review Agent 对主控只返回三种结果：PASSED / FAILED / ERROR。

---

## Review Agent 返回协议

| 返回值 | 含义 | 产物状态 | 主控动作 |
|--------|------|---------|---------|
| `REVIEW_PASSED` | 预检通过，AI 检查完成 | pre-check-result.json + review-result.json + final-report.md 均存在 | 展示报告，完成 |
| `REVIEW_FAILED` | 预检阻断（P0>0），或 AI 检查有 FAIL | review-output/ 下有对应产物 | round<max → 回 coder；否则超限 |
| `REVIEW_ERROR` | 环境/工具异常（python3 不可用、CLI 崩溃等） | 产物可能不完整 | 告知用户，停止流水线 |

---

## 修复轮 Coder 行为

修复轮的 coder Agent prompt 不同于首轮。首轮只包含需求，修复轮包含引导指令：

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

Coder Agent 自己读取 JSON，自己解析 file/line/code/message 字段，定位到具体问题。

---

## 数据模型（现有，无需改动）

### pre-check-result.json 结构（CLI 默认输出，exit 0 或 exit 1 均生成）

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

> CLI 在 `output_format=json`（默认）时，无论 pass 或 fail 都会先写入该 JSON，再根据 passed 决定 exit code。行为无需修改。

### review-result.json 结构（AI 检查输出）

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

Coder 从 `file_reports[].findings[]` 获取程序问题（file, line, method, level, code, message），从 `items[]` 获取 AI 问题（file, line, category, code, evidence, suggestion）。字段齐全，无需改动数据模型。

---

## 错误处理

### Review Agent 内部错误

| 场景 | Review Agent 返回 | 主控动作 |
|------|------------------|---------|
| python3 不可用 | `REVIEW_ERROR` | 告知「需要 Python 3 环境」，停止 |
| 扫描路径无 .java 文件 | `REVIEW_ERROR` | 告知「未找到 Java 文件，coder 未产出」，停止 |
| CLI Python 异常崩溃（JSON 未生成） | `REVIEW_ERROR` | 告知异常信息，停止（工具问题不循环） |
| pre-check-result.json 格式异常 | `REVIEW_ERROR` | 告知格式异常，停止 |
| AI 检查未生成 review-result.json | `REVIEW_FAILED`（仅有 pre-check 结果） | 正常走修复循环（coder 只修程序问题） |
| AI 检查超时 | `REVIEW_ERROR` | 告知「审查超时」，停止 |

### 主控层错误

| 场景 | 主控动作 |
|------|---------|
| coder 未生成 .java 文件 | 不进入 Phase 2，告知用户，停止 |
| coder 子 Agent 超时（900s） | 告知超时，保留已生成文件，停止 |
| 修复后 P0 不变/反增 | 继续循环，不特殊处理。max_retries 是唯一硬上限 |
| max_retries 耗尽 | 展示 final-review-report.md，列出剩余问题，提示手动介入 |
| 用户 Ctrl+C | 保留当前轮产物，展示已完成轮次总结 |

---

## 改动范围

| 文件 | 改动类型 | 改动内容 |
|------|---------|----------|
| `agents/scheduler/build.skill.md` | 重构 | Phase 2: `Agent("review")` 代替原 reviewer AI Agent；Phase 3: 根据 PASS/FAIL/ERROR 判定；Phase 4: coder 自己读产物修复 |
| `agents/scheduler/pipeline.yaml` | 更新 | reviewer 节点更新为 review Agent prompt（内部调 Skill("review")） |
| `agents/reviewer/review.skill.md` | 简化 | Step 1 Bash 保留；Step 2 AI Agent 保留；Step 3 合并报告保留；移除 `/review:on` 和 `/review:off` 用法说明 |
| CLI/数据模型 | **不改** | `Finding`/`FileReport`/`ScanResult` 已满足需求，CLI 已输出 JSON on both pass and fail |

### 明确不改

- `code-check-config.yaml` — 配置不变
- `code_check/` 下的 Python 代码 — CLI 行为不变
- `agents/reviewer/hooks/settings.template.json` — 保留文件
- `agents/coder/` — 规范文件不改
- 不引入 Docker、不引入新组件

---

## 不做的事（YAGNI）

- 不让主控读 JSON 或构造问题详情 — coder 自己读产物
- 不让主控验证产物文件完整性 — review Agent 返回 ERROR 时直接告知用户
- 不做自动合并修复（AI 自动修 pre-check 问题）— 必须回 coder 完整走一轮
- 不做增量扫描 — 每轮全量扫描
- 不做 P1 阻断 — 当前 `block_on: [P0]`，P1 记录但不触发修复循环
- 不做并行修复（多 Agent 同时修不同文件）— 单 Agent 顺序修复
