# Pipeline Engine 调度器设计规格

> 设计日期：2026-06-24
> 关联问题：`architecture-review-2025-06-24.md` §3.1 — pipeline.yaml 是死配置，DAG 从未被机器执行

## 一、问题陈述

### 现状

`agents/scheduler/pipeline.yaml` 定义了完整的 DAG（节点、边、条件、触发器、循环控制），但 `build.skill.md` **完全没有解析这个 DAG**。它用自然语言硬编码了 coder→reviewer→fix 循环逻辑，等价于把 DAG 又写了一遍。

**后果：**
- 修改 YAML 中的 edges 不会改变流水线行为
- 新增节点（如未来加入 analyst/测试节点）需要同时改 YAML 和 build.skill.md
- 两份"真相"必然漂移

### 目标

创建一个 Python 调度器包 `pipeline_engine/`，真实解析 `pipeline.yaml` 中的 DAG 定义，通过 CLI 接口向 Claude Code Agent 提供步进式执行指令。Claude Code Agent（`build.skill.md`）简化为"薄执行器"：只做 `while next() → Agent执行 → report()` 循环，所有路由决策由调度器完成。

---

## 二、架构设计

### 2.1 整体模式

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code Agent (build.skill.md 简化为薄执行器)         │
│                                                          │
│  1. scheduler start  → 初始化状态                         │
│  2. scheduler next   → 获取下一步指令（节点 + 渲染后prompt）│
│  3. Agent 工具执行节点 → 拿到结果/verdict                  │
│  4. scheduler report → 上报结果，更新状态                  │
│  5. 循环 2-4 直到 next 返回 action=done                   │
└──────────────────────────────────────────────────────────┘
         │                        ▲
         │ CLI 调用 (subprocess)   │ JSON 响应 (stdout)
         ▼                        │
┌──────────────────────────────────────────────────────────┐
│  Python Scheduler (agents/scheduler/pipeline_engine/)     │
│                                                          │
│  config.py  → 严格加载 pipeline.yaml → PipelineConfig     │
│  engine.py  → DAG 状态机（start/next/report/status/reset） │
│  models.py  → 所有 dataclass（配置实体 + 运行时实体）       │
│  cli.py     → argparse CLI 入口                           │
│  reporter.py → 状态可视化                                  │
│                                                          │
│  状态持久化: review-output/pipeline-state.json             │
└──────────────────────────────────────────────────────────┘
```

**关键设计原则：调度器不执行 Agent。** 它只做路由决策，Agent 的创建和执行由 Claude Code Agent 通过 `Agent` 工具完成。这是和 check_system（CLI 直接执行扫描）最大的区别——调度器是"决策引擎"而非"执行引擎"。

### 2.2 包结构（对齐 check_system/code_check/）

```
agents/scheduler/
├── build.skill.md              # 简化为薄执行器（~30行 while 循环）
├── pipeline.yaml               # DAG 定义（已有，小幅增强）
├── pipeline-config.yaml        # 调度器自身配置
├── requirements.txt            # PyYAML
├── pipeline_engine/            # Python 包（对齐 code_check/）
│   ├── __init__.py
│   ├── models.py               # 所有 dataclass — 配置实体 + 运行时实体
│   ├── config.py               # YAML → typed dataclass 加载器 + 严格校验
│   ├── engine.py               # DAG 状态机核心
│   ├── cli.py                  # argparse CLI 入口
│   └── reporter.py             # 状态可视化、进度输出
└── tests/                      # 对齐 check_system/tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_config.py
    ├── test_engine.py
    └── test_cli.py
```

对比参照：
```
code_check/                     pipeline_engine/
├── models.py    — 数据模型      ├── models.py    — 数据模型（更复杂）
├── config.py    — YAML 加载     ├── config.py    — YAML + 严格校验
├── scanner.py   — 扫描引擎      ├── engine.py    — DAG 状态机
├── reporter.py  — 报告生成      ├── reporter.py  — 进度/状态输出
├── cli.py       — CLI 入口      ├── cli.py       — CLI 入口
```

---

## 三、Spring Boot 风格配置绑定

### 3.1 设计理念

像 Spring Boot 的 `@ConfigurationProperties` 一样：YAML 结构 → 严格类型树 → `from_dict()` 工厂方法带完整校验。改了 YAML 就会立即被校验——要么校验通过（DAG 正确执行），要么报错明确告知哪里不对。

### 3.2 YAML 结构 → Dataclass 映射

```
pipeline.yaml
├── name: str
├── version: str
├── description: str
├── defaults: PipelineDefaults
│   ├── timeout: str = "600s"
│   ├── max_retries: int = 3
│   └── block_on: list[str] = ["P0"]
├── nodes: list[NodeConfig]
│   ├── id: str                    # 唯一标识
│   ├── type: str                  # "agent"
│   ├── agent: str                 # agent 类型名
│   ├── description: str           # 人类可读描述
│   ├── prompt_template: str       # 含 {requirement} {review_context} 等变量
│   ├── inputs: dict[str, str]     # 输入映射
│   ├── outputs: dict[str, str]    # 输出产物路径
│   ├── timeout: Optional[str]     # 节点级超时覆盖
│   └── depends_on: list[str]      # 显式依赖声明（用于并行控制）
└── edges: list[EdgeConfig]
    ├── from_node: str             # YAML 中为 "from"
    ├── to: str                    # 目标节点 ID 或 "DONE"
    ├── trigger: TriggerType       # on_success | on_condition
    ├── condition: Optional[EdgeCondition]
    │   └── status: str            # REVIEW_PASSED | REVIEW_FAILED | REVIEW_ERROR
    └── description: str
```

### 3.3 校验规则

1. **必填字段缺失** → `ConfigLoadError("pipeline.yaml: nodes[0].id is required")`
2. **类型错误** → `ConfigLoadError("pipeline.yaml: defaults.max_retries must be int, got str")`
3. **未知字段** → `ConfigLoadError("pipeline.yaml: nodes[0].unknown_field is not a valid key")`
4. **边引用完整性** → edges 中的 `from`/`to`（非 "DONE"）必须存在于 nodes 中
5. **trigger/condition 一致性** → `trigger=on_condition` 则 `condition` 必填
6. **DAG 无环检查** → 禁止循环依赖（修复循环通过 round 状态机实现，不走 DAG 环路）
7. **唯一入口节点** → 有且仅有一个入度为 0 的起始节点

---

## 四、DAG 状态机

### 4.1 状态转换

```
                    ┌──────────┐
    start ─────────→│ PENDING  │
                    └────┬─────┘
                         │ next()
                    ┌────▼─────┐
         ┌─────────│ RUNNING  │←──────────┐
         │         └────┬─────┘           │
         │              │ next()          │
         │    ┌─────────┼──────────┐      │
         │    ▼         ▼          ▼      │
         │  [coder]  [reviewer]  [...]    │  ← 支持并行多节点
         │    │         │          │      │
         │    └─────────┼──────────┘      │
         │              │ report()        │
         │    ┌─────────▼──────────┐      │
         │    │  评估边条件         │      │
         │    │  - on_success      │      │
         │    │  - on_condition    │──────┘ 修复循环
         │    └─────────┬──────────┘
         │              │ 无匹配边
         │    ┌─────────▼──────────┐
         └────│   COMPLETED        │
              └────────────────────┘
```

### 4.2 核心方法

```python
class PipelineEngine:
    def __init__(self, config: PipelineConfig, state_path: Path)

    def start(self, requirement: str) -> PipelineState
        """初始化状态文件。设置 status=PENDING，保存 requirement。"""

    def next(self) -> NextAction
        """
        核心路由：
        1. PENDING → 找入度为0的节点，渲染prompt，返回 EXECUTE
        2. RUNNING 且 current_nodes 全完成 → 评估出边，确定下一组节点
        3. 有匹配边 → 渲染 prompt，返回 EXECUTE
        4. 无匹配边 → 返回 DONE
        5. ERROR → 返回 ERROR
        """

    def report(self, node_id, status, summary, agent_verdict) -> PipelineState
        """
        记录节点执行结果。
        agent_verdict 是关键区分字段：
        - coder 不填（无 verdict）
        - reviewer 填 REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR
        """

    def status(self) -> PipelineState
    def reset(self) -> None
```

### 4.3 边条件评估算法

```python
def _evaluate_edges(self, completed_node_id: str) -> list[NodeConfig]:
    """评估节点所有出边，返回下一步要执行的节点列表（支持并行）。"""
    edges = self.config.get_outgoing_edges(completed_node_id)
    result = self.state.node_results[completed_node_id]
    next_nodes = []

    for edge in edges:
        if edge.to == "DONE":
            continue  # 终止边

        if edge.trigger == TriggerType.ON_SUCCESS:
            if result.status == NodeStatus.SUCCESS:
                next_nodes.append(self.config.get_node(edge.to))

        elif edge.trigger == TriggerType.ON_CONDITION:
            if self._check_condition(edge.condition, result):
                next_nodes.append(self.config.get_node(edge.to))

    return next_nodes

def _check_condition(self, condition: EdgeCondition, result: NodeResult) -> bool:
    if condition.status == "REVIEW_PASSED":
        return result.agent_verdict == "REVIEW_PASSED"
    if condition.status == "REVIEW_FAILED":
        return (result.agent_verdict == "REVIEW_FAILED"
                and self.state.round < self.config.defaults.max_retries)
    if condition.status == "REVIEW_ERROR":
        return result.agent_verdict == "REVIEW_ERROR"
    return False
```

### 4.4 修复循环处理

修复循环（reviewer → coder 回到修复）不是 DAG 环路，而是 **round 递增 + 重新触发节点**：

1. reviewer 返回 `REVIEW_FAILED` → `report()` 中 `round` 不递增（由 `next()` 判断时递增）
2. `next()` 评估 reviewer → coder 的 `on_condition` 边 → 满足条件 → 返回 coder 节点
3. coder 节点的 prompt 渲染时，`{review_context}` 变量自动填充 review-output 产物路径
4. `{round}` 变量自动替换为当前轮次

### 4.5 并行节点支持

`next()` 返回值 `NextAction.nodes` 已经是 `list[NodeToExecute]`，天然支持返回多个可并行节点。

并行判定逻辑：
- 多个节点的 `depends_on` 完全一致 → 可以并行
- 节点之间无直接依赖关系 → 可以并行
- 当前 DAG 是线性的，始终返回 1 个节点；未来扩展 DAG 时无需改代码

---

## 五、Prompt 模板渲染

### 5.1 变量体系

| 变量 | 来源 | 说明 |
|------|------|------|
| `{requirement}` | `start --requirement` | 用户需求原文 |
| `{review_context}` | 自动生成 | 修复轮时填充产物文件路径提示 |
| `{round}` | PipelineState.round | 当前轮次（首轮为 0） |
| `{max_retries}` | PipelineDefaults.max_retries | 最大修复轮次 |

### 5.2 渲染规则

- 首轮（round=0）：`{review_context}` → 空字符串
- 修复轮（round>=1）：`{review_context}` → 自动生成产物读取提示
- 使用 Python `str.format()` 渲染，缺失变量报错

---

## 六、状态持久化

### 6.1 状态文件

路径：`review-output/pipeline-state.json`（在 check_system 的 output_dir 下）

```json
{
  "pipeline_name": "coder-reviewer-pipeline",
  "status": "running",
  "round": 1,
  "current_nodes": ["reviewer"],
  "node_results": {
    "coder": {
      "node_id": "coder",
      "status": "success",
      "summary": "生成了5个Java文件",
      "agent_verdict": "",
      "outputs": {},
      "timestamp": "2026-06-24T10:30:00Z"
    },
    "reviewer": {
      "node_id": "reviewer",
      "status": null
    }
  },
  "history": [
    {"round": 0, "node": "coder", "status": "success", "timestamp": "..."},
    {"round": 0, "node": "reviewer", "status": "success", "timestamp": "..."}
  ],
  "requirement": "实现用户登录功能",
  "started_at": "2026-06-24T10:29:00Z",
  "updated_at": "2026-06-24T10:31:00Z"
}
```

### 6.2 中断恢复

Ctrl+C 中断后，`pipeline-state.json` 保留在磁盘上。重新运行 `/build` 时：

1. `build.skill.md` Phase 0 检测到已有 state 文件
2. 调用 `scheduler status` 查看当前进度
3. 询问用户「检测到未完成的流水线，是否续接？」
4. 续接 → 从 `scheduler next` 继续
5. 重新开始 → `scheduler reset` 清空状态

---

## 七、CLI 接口

### 7.1 命令总览

```bash
# 启动流水线
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --requirement "实现用户登录功能"

# 获取下一步
python3 -m pipeline_engine.cli next

# 上报节点结果
python3 -m pipeline_engine.cli report \
  --node coder \
  --status success \
  --summary "生成了5个Java文件"

# 上报 reviewer 结果（带 verdict）
python3 -m pipeline_engine.cli report \
  --node reviewer \
  --status success \
  --summary "审查完成，发现3个P0问题" \
  --verdict REVIEW_FAILED

# 查看状态
python3 -m pipeline_engine.cli status

# 重置
python3 -m pipeline_engine.cli reset
```

### 7.2 返回值格式（JSON stdout）

**start:**
```json
{"status": "started", "round": 0, "message": "Pipeline 'coder-reviewer-pipeline' started"}
```

**next (execute):**
```json
{
  "action": "execute",
  "nodes": [{
    "node_id": "coder",
    "agent_type": "coder",
    "prompt": "你需要根据用户需求生成 Java 代码。\n\n用户需求：\n实现用户登录功能\n\n...",
    "timeout": "900s",
    "round": 0,
    "phase": "code_generation"
  }],
  "message": "Execute node 'coder'"
}
```

**next (done):**
```json
{"action": "done", "nodes": [], "message": "Pipeline completed successfully after 1 round"}
```

**next (error):**
```json
{"action": "error", "nodes": [], "message": "Max retries (3) exhausted"}
```

**report:**
```json
{"accepted": true, "state": "running"}
```

**status:**
```json
{"pipeline_name": "coder-reviewer-pipeline", "status": "running", "round": 1, ...}
```

### 7.3 退出码

| 场景 | exit code |
|------|-----------|
| 正常执行（start/next/report/status/reset） | 0 |
| 配置加载失败 | 1 |
| 状态文件损坏 | 2 |
| 非法参数 | 3 |

---

## 八、build.skill.md 简化

### 8.1 简化前（现状）

~130 行自然语言，硬编码了 coder→reviewer→fix 循环的完整逻辑。包含：
- Phase 0 手动解析 YAML 中的 defaults
- Phase 1 coder prompt 硬编码
- Phase 2 reviewer 流程硬编码
- Phase 3 判定逻辑（if REVIEW_PASSED / if REVIEW_FAILED...）
- Phase 4 修复 prompt 硬编码

### 8.2 简化后（目标）

~30 行，只做薄执行器，所有决策委托给调度器：

```markdown
## 执行流程

### Phase 0: 初始化

1. 检测 `review-output/pipeline-state.json` 是否存在 → 询问续接或重来
2. 调用 `python3 -m pipeline_engine.cli start --requirement "{用户需求}"`
3. 向用户报告启动信息

### Phase 1-N: 执行循环

loop:
  1. 调用 `python3 -m pipeline_engine.cli next`
  2. 解析返回 JSON：
     - action=="done"    → 退出循环，展示完成信息
     - action=="error"   → 退出循环，展示错误信息
     - action=="execute" → 对 nodes 中每个节点：
       a. 通过 Agent 工具启动子 Agent（subagent_type="general-purpose"）
       b. prompt 使用节点返回的已渲染 prompt（无需自行拼接）
       c. 等待完成，提取返回的 verdict（如有）
       d. 调用 `python3 -m pipeline_engine.cli report --node {id} --status {s} --verdict {v}`
  3. 回到步骤 1
```

### 8.3 关键简化点

| 原 build.skill.md | 简化后 |
|---|---|
| 硬编码 Phase 3 判定逻辑 | 调度器 `next()` 评估边条件 |
| 硬编码 coder prompt 模板 | YAML `prompt_template` → 调度器渲染 |
| 硬编码修复轮 prompt | 调度器根据 round 自动切换 |
| 硬编码 max_retries 判断 | YAML `defaults.max_retries` → 引擎自动处理 |
| 硬编码 Phase 4 产物文件列表 | `{review_context}` 自动生成 |

---

## 九、与现有系统的关系

### 9.1 产物路径不变

调度器的状态文件写入 `review-output/pipeline-state.json`，与 check_system 的产物目录一致：
```
review-output/
├── pre-check-result.json      # check_system 产出
├── pre-check-report.md        # check_system 产出
├── review-result.json         # check_system 产出
├── final-review-report.md     # check_system 产出
└── pipeline-state.json        # ← 调度器新增
```

### 9.2 不修改 check_system

`pipeline_engine/` 和 `code_check/` 是平级的独立包，职责完全不同：
- `code_check/` — 扫描 Java 文件，执行检查规则，生成报告
- `pipeline_engine/` — 解析 DAG，管理流水线状态，路由节点执行

### 9.3 pipeline.yaml 向后兼容

现有 `pipeline.yaml` 字段全部保留，仅新增：
- `nodes[].depends_on` — 可选字段，不填从 edges 自动推导

---

## 十、测试策略

### 10.1 测试层次

| 层次 | 文件 | 覆盖 |
|------|------|------|
| 单元 — 模型 | `test_models.py` | from_dict/to_dict 序列化、枚举值校验 |
| 单元 — 配置 | `test_config.py` | YAML 加载、严格校验、错误信息 |
| 单元 — 引擎 | `test_engine.py` | start/next/report 状态转换、边条件评估、修复循环、max_retries 耗尽 |
| 集成 — CLI | `test_cli.py` | 完整 start→next→report 流程、JSON 输出格式、退出码 |

### 10.2 关键测试场景

1. **线性流水线**：coder 成功 → reviewer PASSED → DONE
2. **修复循环 1 轮**：coder 成功 → reviewer FAILED → coder 修复 → reviewer PASSED → DONE
3. **max_retries 耗尽**：连续 FAILED 3 轮 → next 返回 action=error
4. **REVIEW_ERROR 终止**：reviewer 返回 ERROR → 立即 DONE
5. **配置校验**：缺失必填字段 → ConfigLoadError
6. **中断恢复**：state 文件存在时重新 start → 提示续接
7. **并行节点**：两个 depends_on 相同的节点 → next 一次返回两个（未来场景）
8. **未知节点引用**：edge 引用不存在的 node → ConfigLoadError
