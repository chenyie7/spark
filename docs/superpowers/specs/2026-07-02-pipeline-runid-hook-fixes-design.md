# Pipeline Run ID & Hook 修复设计

日期: 2026-07-02
状态: 待审核

---

## 1. 架构总览

三层分离（不变）：

```
┌──────────────────────────────────────────────────┐
│  Loop Agent (build.skill.md)                      │
│  职责: 驱动循环，编排 coder → reviewer → fix      │
│  run_id 的唯一记忆者                               │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │  Pipeline Engine (CLI 工具)                   │ │
│  │  职责: DAG 状态机，回答路由决策                │ │
│  │  run_id 的磁盘存储者，被动加载，唯一生成入口    │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │  Worker Agent: coder / reviewer              │ │
│  │  职责: 读 .current-run，输出到指定目录         │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

| 层 | 谁做 | run_id 角色 |
|----|------|------------|
| DAG 循环边 | `pipeline.yaml` 声明式规则 | 不涉及 |
| 状态机 | `engine.next()` 评估规则 | 从磁盘被动加载 |
| 循环驱动 | `build.skill.md` 的 while | **唯一记忆者，攥着 run_id** |

### 概念澄清

- **DAG 循环边**（如 `reviewer → coder on REVIEW_FAILED`）是声明式状态转移规则，不是代码层面的 `while` 或 `for`
- **Loop Agent**（`build.skill.md`）是 DAG 循环边的执行载体，通过 `while True: next → spawn → report` 驱动状态机循环往复
- **Pipeline Engine** 不执行 Agent，不循环，只做路由决策

### run_id 数据流

```
build skill 记得 run_id
    │
    ├── CLI 调用：--state-file review-output/{run_id}/pipeline-state.json
    │     │
    │     └── engine 被动加载 → state.run_id 自动恢复
    │
    └── .current-run 文件 → Agent 固定路径读取
```

---

## 2. 改动点一：run_id 唯一源头

### 问题

run_id 在三个阶段各自生成，时间戳不同导致不一致：

| 阶段 | 生成方式 | 问题 |
|------|---------|------|
| `build.skill.md` Phase 1 | shell `date` 命令 | 自算，与 engine 无关联 |
| `cli.py cmd_start()` | `_generate_run_id()` | 独立生成，覆盖 engine 内部值 |
| `PipelineState.start()` | fallback 生成 | 被 CLI 立即覆盖 |

### 方案

**PipelineState.start() 为 run_id 唯一生成入口。** 同时拆开「生成 run_id」和「启动流水线」，start 后保持 PENDING 状态，由 `next()` 触发 RUNNING。

### 改动

#### 2.1 `PipelineState.start()` — 不设 RUNNING，保持 PENDING，生成 run_id

当前代码（`models.py`）：

```python
def start(self):
    self.status = PipelineStatus.RUNNING   # ← 直接标为运行中
    ...
    if not self.run_id:
        self.run_id = datetime.now(...)     # ← fallback 生成
```

改为：

```python
def start(self, requirement: str = "", target_dir: str = "."):
    self.requirement = requirement
    self.target_dir = target_dir
    self.status = PipelineStatus.PENDING    # ← 保持待命，不启动
    self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not self.run_id:
        self.run_id = _generate_run_id(target_dir)   # ← 唯一生成点
    self._touch()
```

#### 2.2 `_generate_run_id()` 移至 `engine.py`

从 `cli.py` 移到 `engine.py`（或 `models.py`），作为 `PipelineState.start()` 的内部辅助：

```python
def _generate_run_id(target_dir: str) -> str:
    """格式: YYYYMMDDHHmmss[-target_dir]"""
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if target_dir and target_dir != ".":
        return f"{timestamp}-{target_dir}"
    return timestamp
```

#### 2.3 `cli.py cmd_start()` — 去掉 run_id 覆盖

当前代码：

```python
state = engine.start(args.requirement)
run_id = _generate_run_id(args.target_dir)   # ← 重复生成
state.run_id = run_id                        # ← 覆盖
```

改为：

```python
state = engine.start(requirement=args.requirement,
                     target_dir=args.target_dir)
# run_id 已由 PipelineState.start() 生成，不再覆盖
```

#### 2.4 `next()` 中 PENDING → RUNNING 转换（已有，无需改动）

当前代码已处理：

```python
if state.status == PipelineStatus.PENDING:
    start_nodes = self.config.get_start_nodes()
    state.set_current_nodes([n.id for n in start_nodes])
    state.status = PipelineStatus.RUNNING
```

#### 2.5 `build.skill.md` Phase 1 — 调用 engine start 获取 run_id

当前 Phase 1 手动生成：

```bash
# 旧：shell 命令自己算
run_id=$(date +%Y%m%d%H%M%S)-admin-test
mkdir review-output/$run_id
```

改为从 engine 获取：

```bash
# 新：调用 engine start，从 stdout 提取 run_id
result=$(PYTHONPATH="..." python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/.pipeline-state.tmp \
  --target-dir "admin-test" \
  --requirement "placeholder")

run_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")

# 用 run_id 建目录和保存状态文件
mkdir -p "review-output/$run_id"
mv review-output/.pipeline-state.tmp "review-output/$run_id/pipeline-state.json"
```

---

## 3. 改动点二：`.current-run` 固定上下文文件

### 问题

run_id 通过 prompt 传递给 Agent，依赖 Agent 的"记忆力"和"服从性"，不可靠。

### 方案

新增固定路径文件 `review-output/.current-run`，Agent 启动时读取，程序路径不依赖 prompt。

### 文件格式

```json
{
  "run_id": "20260702120000-admin-test",
  "target_dir": "admin-test",
  "output_dir": "review-output/20260702120000-admin-test/",
  "scan_path": "admin-test/src/main/java"
}
```

### 存储位置

```
review-output/
├── .current-run              ← 固定路径，当前活跃的 run_id 上下文
├── .pipeline-active          ← 标记文件，hook 检查
├── 20260702120000-admin-test/
│   ├── pm-context.json
│   ├── pipeline-state.json
│   ├── review-result.json
│   └── final-review-report.md
└── 20260702150000-admin-test/
    └── ...
```

### 生命周期

```
Phase 2 开始:
  touch .pipeline-active
  写入 review-output/.current-run

循环 (coder → reviewer → fix):
  Agent 启动 → 读 .current-run → 自动写入正确目录

Phase 2 结束:
  rm .pipeline-active
  rm review-output/.current-run
```

### Agent prompt 改动

`pipeline.yaml` 中 coder prompt 改为引用 `.current-run`：

```
coder prompt:
  开始工作前，先读取 review-output/.current-run。
  你的代码输出到 output_dir 指定的路径。

reviewer prompt:
  开始工作前，先读取 review-output/.current-run。
  扫描 scan_path，审查结果输出到 output_dir。
```

### 对比

| | Prompt 传 run_id | `.current-run` 文件 |
|--|-----------------|---------------------|
| 可靠性 | Agent 可能忽略 prompt | 固定路径，Agent 被训练去读文件 |
| 一致性 | 每次 prompt 都要渲染 | 一个文件，所有 Agent 读同一份 |
| 代码耦合 | prompt_template 嵌 run_id | CLI/Agent 各自读文件，解耦 |
| 可调试性 | run_id 散落在 prompt 里 | 一个文件，一目了然 |

---

## 4. 改动点三：`.pipeline-active` 标记文件控制 Hook 开关

### 问题

Hook（`block-agents-write.sh` 等）在任何会话中都触发，影响项目开发和日常使用。

### 方案

新增 `.pipeline-active` 标记文件。所有 hook 脚本检查该标记，不存在则静默跳过。

### 标记文件生命周期

```
Phase 2 开始:  touch .pipeline-active    ← 在 spawn Agent 之前
Phase 2 结束:  rm .pipeline-active       ← 循环退出后（done 或 error）
```

- 异常退出保护：CLAUDE.md 自检规则检测残留标记

### Hook 脚本改动

每个 hook 脚本开头加 3 行：

```bash
if [ ! -f "${CLAUDE_PROJECT_DIR}/.pipeline-active" ]; then
    exit 0
fi
```

涉及文件：
- `hooks/block-agents-write.sh`
- `benchmarks/hooks/dump-agent-payload.sh`
- `benchmarks/hooks/synthesize-benchmark.sh`

### CLAUDE.md 自检规则

在 CLAUDE.md 中新增：

```markdown
## 会话自检

- 每次会话开始，检查项目根目录是否存在 `.pipeline-active`
- 如存在，读取 `review-output/.current-run` 获取 run_id：
  - `pipeline-state.json` 中 status 为 running/pending → 提醒用户「流水线未完成，可 /build --resume <run_id> 恢复」
  - 否则 → 提醒用户「.pipeline-active 是残留标记，建议手动删除」
```

---

## 5. 完整执行流程

```
/build "需求描述"
    │
    ├── Phase 1 (PM):
    │   │
    │   ├── pipeline-engine start --target-dir admin-test
    │   │     → PipelineState.start() 生成 run_id（唯一入口）
    │   │     → status = PENDING
    │   │     → stdout: {"status":"started","run_id":"20260702120000-admin-test",...}
    │   │
    │   ├── 提取 run_id
    │   ├── mkdir review-output/{run_id}/
    │   ├── mv .pipeline-state.tmp → review-output/{run_id}/pipeline-state.json
    │   ├── 写入 review-output/{run_id}/pm-context.json
    │   ├── PM 需求对话
    │   └── 提示: /build --resume 20260702120000-admin-test
    │
    ├── Phase 2 (/build --resume {run_id}):
    │   │
    │   ├── 读取 review-output/{run_id}/pm-context.json
    │   ├── touch .pipeline-active                         ← hooks 生效
    │   ├── 写入 review-output/.current-run                 ← Agent 上下文
    │   │
    │   ├── pipeline-engine next
    │   │     --state-file review-output/{run_id}/pipeline-state.json
    │   │     → PENDING → RUNNING，派发 coder
    │   │
    │   ├── while action != done/error:
    │   │     │
    │   │     ├── spawn Agent(agent_type, prompt)
    │   │     │     → Agent 读 review-output/.current-run
    │   │     │     → 自动输出到正确目录
    │   │     │     → Hook 检查 .pipeline-active → 通过
    │   │     │
    │   │     ├── pipeline-engine report
    │   │     │     --node coder --status success
    │   │     │
    │   │     └── pipeline-engine next
    │   │           → 评估 DAG 边 → 返回下一节点或 DONE
    │   │
    │   ├── rm .pipeline-active                            ← hooks 停止
    │   ├── rm review-output/.current-run                   ← 上下文清理
    │   └── 展示最终报告
```

---

## 6. 错误处理

| 场景 | 处理 |
|------|------|
| `.pipeline-active` 残留 | CLAUDE.md 自检规则提醒用户手动删除 |
| 重复 start 同一 run_id | `cmd_start()` 检测 status 为 running/pending 时报错 |
| Phase 1 未调用 start | Phase 2 `--resume` 时检查状态文件不存在 → 提示先跑 Phase 1 |
| Agent 未读 `.current-run` | 输出落到错误目录，reviewer 扫描不到 → 报 REVIEW_ERROR |
| Phase 2 用户 Ctrl+C 中断 | `.pipeline-active` 和 `.current-run` 可能残留，CLAUDE.md 自检兜底 |
| pipeline-state.json 路径包含 run_id | 每次 `--resume` 时 build skill 明确传入完整路径，无歧义 |

---

## 7. 影响范围

| 文件 | 改动类型 |
|------|---------|
| `agents/scheduler/pipeline_engine/models.py` | `PipelineState.start()` 改为 PENDING，接收 target_dir |
| `agents/scheduler/pipeline_engine/engine.py` | 移入 `_generate_run_id()` |
| `agents/scheduler/pipeline_engine/cli.py` | `cmd_start()` 去掉 run_id 覆盖 |
| `agents/scheduler/build.skill.md` | Phase 1 调用 engine start；Phase 2 管理标记文件 |
| `agents/scheduler/pipeline.yaml` | prompt_template 改为引用 `.current-run` |
| `hooks/block-agents-write.sh` | 开头加 `.pipeline-active` 检查 |
| `benchmarks/hooks/dump-agent-payload.sh` | 同上 |
| `benchmarks/hooks/synthesize-benchmark.sh` | 同上 |
| `CLAUDE.md` | 新增会话自检规则 |
| `.gitignore` | 添加 `.pipeline-active` 和 `review-output/.current-run` |

---

## 8. 自检清单

- [ ] run_id 生成只有一个入口（`PipelineState.start()`）
- [ ] Phase 1 和 Phase 2 使用同一个 run_id
- [ ] `.current-run` 文件在 Phase 2 开始创建、结束删除
- [ ] `.pipeline-active` 标记文件在 Phase 2 开始创建、结束删除
- [ ] 所有 hook 脚本检查 `.pipeline-active` 后才执行
- [ ] CLAUDE.md 包含残留标记文件的自检提示
- [ ] `.gitignore` 忽略标记文件和上下文文件
- [ ] 现有测试不因 `start()` 返回 PENDING 而破坏
