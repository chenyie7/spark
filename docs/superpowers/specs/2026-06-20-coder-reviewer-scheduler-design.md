# Coder-Reviewer 调度器设计

> 设计日期：2026-06-20  
> 状态：已确认

## 一、背景与目标

当前已有两个独立 Agent：

- **Coder Agent**（`agents/coder/`）：按 20+ 规范文件生成 Spring Boot 3 Java 代码
- **Reviewer Agent**（`agents/reviewer/`）：双层校验 — Layer 1 Python CLI 程序预检（39 条规则）+ Layer 2 AI 语义检查（17 条规则）

目前两者之间是**手动交互**：用户先让 coder 写代码，然后手动 `/review`，发现问题后手动修复，再 `/review`，循环。

**目标**：实现一个调度器，自动化 coder → reviewer → fix 循环，让用户一次输入需求即可得到经过审查的代码。

---

## 二、架构方案：Skill 驱动调度器

选择在 Claude Code 内用 Skill（斜杠命令）实现调度器，是当前阶段最小可行的实现方式。长期方向可能是 Python CLI + Docker 容器隔离，但 YAML DAG 模板的 schema 不绑定 Skill 实现，未来切换引擎时模板无需改动。

```
用户: /build 实现用户登录功能
            │
    ┌───────▼──────────┐
    │  /build Skill     │  1. 读取 pipeline.yaml
    │  (调度 Agent)     │  2. 解析 DAG
    └───────┬──────────┘  3. 初始化循环计数器 round=0
            │
    ┌───────▼──────────┐
    │  STEP 1: coder    │  启动 coder Agent
    │  生成代码          │  输入: 用户需求 (+ 上轮 review JSON)
    └───────┬──────────┘  输出: src/main/java/*.java
            │
    ┌───────▼──────────┐
    │  STEP 2: reviewer │  启动 reviewer Agent
    │  双层审查          │  Layer 1: Python CLI 预检
    └───────┬──────────┘  Layer 2: AI 语义检查
            │                 
            ├── P0=0 ────▶ DONE: 展示 final-report.md
            │
            └── P0>0 ────▶ round++，检查 round < max_retries?
                              ├── 是 → 回到 STEP 1（带 review JSON）
                              └── 否 → 超限退出，展示剩余问题
```

### 设计原则

- **不修改 coder 和 reviewer 现有行为**，调度器只是按 DAG 自动化调用
- **YAML 模板优先**，调度逻辑从配置读取，不硬编码
- **循环在 DAG 中可见**（显式回边），不隐藏在节点内部
- **失败可见**，超时/超限时明确告知用户剩余问题

---

## 三、YAML 调度模板 Schema

```yaml
# pipeline.yaml
name: coder-reviewer-pipeline
version: "1.0"
description: "标准 coder → reviewer 代码生成流水线"

# ── 全局配置 ──
defaults:
  timeout: 600s          # 单节点默认超时
  max_retries: 3         # 循环最大轮次
  block_on: [P0]         # 哪些级别触发回退

# ── DAG 节点 ──
nodes:
  - id: coder
    type: agent           # agent | script | manual
    agent: coder          # 对应 agents/coder/ 下的 Agent
    prompt_template: |
      根据用户需求生成 Java 代码：
      {requirement}
      
      遵守 agents/coder/ 下的所有规范。
    inputs:
      - requirement: "${user_input}"
      - review_result: "review-output/review-result.json"
    outputs:
      - target_dir: "src/main/java"
    timeout: 900s

  - id: reviewer
    type: agent
    agent: reviewer       # 对应 agents/reviewer/ 下的 Agent
    prompt_template: |
      对 {coder_output} 执行双层代码审查。
    inputs:
      - coder_output: "${coder.outputs.target_dir}"
    outputs:
      - pre_check: "review-output/pre-check-result.json"
      - ai_review: "review-output/review-result.json"
      - final_report: "review-output/final-review-report.md"
    timeout: 600s

# ── DAG 边（含循环回边） ──
edges:
  - from: coder
    to: reviewer
    trigger: on_success

  - from: reviewer
    to: coder
    trigger: on_condition
    condition:
      field: "${reviewer.outputs.pre_check}.summary.p0_count"
      operator: gt
      value: 0
    description: "存在 P0 问题，回到 coder 修复"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      field: "${reviewer.outputs.pre_check}.summary.p0_count"
      operator: eq
      value: 0
    description: "P0 清零，流水线结束"
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `nodes[].type` | 节点类型：`agent`（AI Agent）、`script`（Shell/Python）、`manual`（等待用户） |
| `nodes[].agent` | 关联的 Agent 名称，对应 `agents/<name>/` |
| `nodes[].prompt_template` | Agent 的 prompt，支持 `{var}` 变量插值 |
| `nodes[].inputs` | 输入变量，支持 `${user_input}` 和 `${node.outputs.field}` 引用 |
| `nodes[].outputs` | 输出产物路径 |
| `edges[].trigger` | `on_success` 无条件流转 / `on_condition` 条件流转 |
| `defaults.block_on` | 触发循环回退的严重级别列表 |
| `defaults.max_retries` | 最大循环轮次 |

### 变量引用语法

- `${user_input}` — 用户原始输入
- `${coder.outputs.target_dir}` — 前序节点的产出字段
- `${reviewer.outputs.pre_check}.summary.p0_count` — JSON 文件内的深层路径

---

## 四、文件结构

```
agents/
├── coder/              # 已有，不变
├── reviewer/           # 已有，不变
└── scheduler/          # 新增
    ├── build.skill.md          # /build Skill 指令
    └── pipeline.yaml           # 调度模板

CLAUDE.md               # 加一行入口，指向 agents/scheduler/
```

### 集成关系

- `/build` Skill 读取 `pipeline.yaml` 获取 DAG 定义
- 启动 coder 子 Agent 时，按 `agents/coder/README.md` 规范索引指导
- 启动 reviewer 子 Agent 时，按 `agents/reviewer/review.skill.md` 规范执行
- coder 和 reviewer 的行为不变，调度器只是按 DAG 自动化调用

---

## 五、错误处理

### Agent 执行失败

| 场景 | 处理 |
|------|------|
| coder 生成不可编译代码 | 不阻断，推进到 reviewer。结构性问题通过循环回边修复 |
| reviewer Python CLI 失败 | 立即停止，告知用户检查 Python 环境 |
| Agent 超时 | 终止当前节点。coder 超时 → 整条线失败；reviewer 超时 → 保留上一轮产物 |

### 循环异常

| 场景 | 处理 |
|------|------|
| 循环 max_retries 轮后 P0 仍未清零 | 停止，展示剩余 P0 列表和 final-report，用户手动介入 |
| P0 数量不降反增 | 不自动终止，让循环自然耗尽 |
| 用户手动中断 | 保留当前产物，展示已完成轮的产出 |

### 产物缺失

| 场景 | 处理 |
|------|------|
| coder 未生成任何 .java 文件 | reviewer 预检报「无可扫描文件」，停止流水线 |
| pre-check-result.json 不存在 | 降级为只执行 Layer 2 AI 检查 |
| review-result.json 不存在 | 循环回边缺少输入，降级展示 pre-check 结果 |

### 用户输入

| 场景 | 处理 |
|------|------|
| `/build` 不带参数 | 提示用户输入需求描述 |
| 需求过于模糊 | 调度 Agent 追问澄清，不直接启动流水线 |

---

## 六、测试策略

1. **YAML 解析正确性**：验证 pipeline.yaml 能被正确加载，节点和边解析无误
2. **DAG 拓扑正确性**：验证 DAG 无死循环、无孤立节点
3. **条件表达式求值**：验证 `${node.outputs.file}.field` 能从 JSON 文件中正确提取值
4. **循环终止条件**：验证 P0=0 时正确终止，P0>0 且未超限时正确回退，超限时正确停止
5. **端到端**：用一个简单需求（如「生成一个带 /health 接口的 Controller」）跑完整流水线

---

## 七、未来扩展方向

以下不在此次实现范围内，但 YAML schema 预留了扩展空间：

- **多项目并行**：`pipeline.yaml` 支持 `jobs: [...]` 数组，Python 引擎管理并发
- **Docker 容器隔离**：节点 `type: container`，每个 Agent 跑在独立容器
- **CI/CD 集成**：CLI 命令 `scheduler run --pipeline pipeline.yaml` 可在 GitHub Actions 中调用
- **通知钩子**：节点完成后触发 webhook / Slack 通知
