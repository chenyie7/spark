# Pipeline Run ID & Hook 修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 run_id 多源头生成不一致 + Hook 非流水线场景误触发两个问题。

**Architecture:** 收敛 run_id 生成为 `PipelineState.start()` 唯一入口，start 保持 PENDING 由 next() 触发 RUNNING；新增 `.pipeline-active` 标记文件控制 Hook 开关；新增 `review-output/.current-run` 固定上下文文件替代 prompt 传参。

**Tech Stack:** Python 3 (dataclasses, json, PyYAML), Bash, pytest

---

### 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `agents/scheduler/pipeline_engine/models.py` | 数据模型，`PipelineState.start()` 改为 PENDING + 生成 run_id | 修改 |
| `agents/scheduler/pipeline_engine/engine.py` | 引擎核心，移入 `_generate_run_id()` | 修改 |
| `agents/scheduler/pipeline_engine/cli.py` | CLI 入口，`cmd_start()` 去掉 run_id 覆盖 | 修改 |
| `agents/scheduler/tests/test_engine.py` | 引擎测试，适配 PENDING 行为 | 修改 |
| `hooks/block-agents-write.sh` | PreToolUse hook：拦截 agents/ 写入 | 修改 |
| `benchmarks/hooks/dump-agent-payload.sh` | PostToolUse hook：采集性能数据 | 修改 |
| `benchmarks/hooks/synthesize-benchmark.sh` | Stop hook：合成 benchmark | 修改 |
| `agents/scheduler/build.skill.md` | Loop Agent 入口 | 修改 |
| `agents/scheduler/pipeline.yaml` | DAG 配置 | 修改 |
| `CLAUDE.md` | 项目引导文件 | 修改 |
| `.gitignore` | Git 忽略规则 | 修改 |

---

### Task 1: 修改 `PipelineState.start()` — PENDING + 生成 run_id

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py`

- [ ] **Step 1: 在 models.py 顶部添加 `_generate_run_id` 函数**

在 `from typing import Optional` 之后、枚举定义之前插入：

```python
def _generate_run_id(target_dir: str = ".") -> str:
    """生成 run_id，格式: YYYYMMDDHHmmss[-target_dir]
    
    target_dir 为 "." 时不加后缀，如 "20260702120000"。
    target_dir 为 "admin-test" 时加后缀，如 "20260702120000-admin-test"。
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if target_dir and target_dir != ".":
        return f"{timestamp}-{target_dir}"
    return timestamp
```

- [ ] **Step 2: 修改 `PipelineState.start()` 方法签名和逻辑**

找到 `models.py` 中的 `def start(self):`，替换为：

```python
def start(self, requirement: str = "", target_dir: str = "."):
    """将流水线标记为待命（PENDING），生成 run_id，记录开始时间。
    
    不直接进入 RUNNING——由 next() 在首次派发节点时完成状态转移。
    这样 Phase 1 可以先拿到 run_id 而不触发流水线执行。
    """
    self.requirement = requirement
    self.target_dir = target_dir
    self.status = PipelineStatus.PENDING
    self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not self.run_id:
        self.run_id = _generate_run_id(target_dir)
    self._touch()
```

旧代码（`PipelineStatus.RUNNING` + fallback 生成）完全替换。

- [ ] **Step 3: Commit**

```bash
git add agents/scheduler/pipeline_engine/models.py
git commit -m "feat: PipelineState.start() 改为 PENDING + 生成 run_id

start() 不再直接进入 RUNNING，由 next() 完成状态转移。
run_id 由 _generate_run_id() 统一生成，格式 YYYYMMDDHHmmss[-target_dir]。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 更新 `engine.py` — 适配新的 `start()` 签名

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py`

- [ ] **Step 1: 更新 `PipelineEngine.start()` 方法**

找到 `engine.py` 中的 `def start(self, requirement: str) -> PipelineState:`，替换为：

```python
def start(self, requirement: str = "", target_dir: str = ".") -> PipelineState:
    """初始化流水线并持久化状态。

    调用 PipelineState.start() 生成 run_id、记录元信息，
    状态保持 PENDING。首次 next() 时才进入 RUNNING。

    Raises:
        RuntimeError: 如果已有流水线在运行中或待命中。
    """
    if self.state_path.exists():
        existing = self._load_state()
        if existing.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
            raise RuntimeError(
                f"流水线 '{existing.pipeline_name}' 已在运行中 "
                f"（状态: {existing.status.value}）。使用 'reset' 清除，"
                f"或调用 'next' 继续。"
            )
    self.state = PipelineState(pipeline_name=self.config.name)
    self.state.start(requirement=requirement, target_dir=target_dir)
    self._save_state()
    return self.state
```

核心变化：`self.state.start(requirement=requirement, target_dir=target_dir)` 传参，不再单独设 `self.state.requirement`。

- [ ] **Step 2: Commit**

```bash
git add agents/scheduler/pipeline_engine/engine.py
git commit -m "refactor: engine.start() 适配 PipelineState.start() 新签名

传递 requirement 和 target_dir 给 PipelineState.start()。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 更新 `cli.py` — 去掉 run_id 覆盖

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py`

- [ ] **Step 1: 修改 `cmd_start()` 函数**

找到 `cli.py` 中的 `cmd_start` 函数，将旧的 start 调用 + run_id 覆盖逻辑替换为：

```python
def cmd_start(args):
    """初始化流水线状态。"""
    pipeline_path = Path(args.pipeline)
    state_path = Path(args.state_file)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        state = engine.start(requirement=args.requirement,
                             target_dir=args.target_dir)
    except RuntimeError as e:
        existing = engine.status()
        print(json.dumps({
            "status": "already_running",
            "pipeline_name": existing.pipeline_name,
            "current_round": existing.round,
            "message": str(e),
        }))
        sys.exit(0)

    run_id = state.run_id  # 由 PipelineState.start() 生成，不再覆盖

    # 同步更新 code-check-config.yaml
    import yaml as _yaml
    _config_path = Path("agents/reviewer/check_system/code-check-config.yaml")
    if _config_path.exists():
        with open(_config_path, "r") as f:
            _cfg = _yaml.safe_load(f) or {}
        _cfg["default_scan_path"] = f"../../../{state.target_dir}/src/main/java"
        _cfg["output_dir"] = f"../../../review-output/{state.run_id}/"
        with open(_config_path, "w") as f:
            _yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)

    print(json.dumps({
        "status": "started",
        "pipeline_name": state.pipeline_name,
        "round": 0,
        "run_id": run_id,
        "target_dir": state.target_dir,
        "max_retries": config.defaults.max_retries,
        "message": f"流水线 '{config.name}' 已启动。",
    }))
```

- [ ] **Step 2: 删除 `_generate_run_id` 函数**

删除 `cli.py` 中第 22-32 行的 `_generate_run_id` 函数定义（已移至 models.py）。

- [ ] **Step 3: Commit**

```bash
git add agents/scheduler/pipeline_engine/cli.py
git commit -m "refactor: cmd_start() 去掉 run_id 覆盖

run_id 由 PipelineState.start() 唯一生成，CLI 不再重复生成。
删除 cli.py 中的 _generate_run_id()。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 修复现有测试适配 PENDING 行为

**Files:**
- Modify: `agents/scheduler/tests/test_engine.py`

- [ ] **Step 1: 修复 `test_start_creates_state_file`**

找到 `TestPipelineEngineStart::test_start_creates_state_file`（第 13-20 行），将 `RUNNING` 断言改为 `PENDING`：

```python
def test_start_creates_state_file(self, sample_pipeline_path: Path, state_path: Path):
    config = load_pipeline(sample_pipeline_path)
    engine = PipelineEngine(config, state_path)
    state = engine.start("build login feature")
    assert state.status == PipelineStatus.PENDING  # start 后为待命状态
    assert state.requirement == "build login feature"
    assert state_path.exists()
```

- [ ] **Step 2: 修复 `test_status_returns_state`**

找到 `TestPipelineEngineStatus::test_status_returns_state`（第 237-242 行），将 `RUNNING` 断言改为 `PENDING`：

```python
def test_status_returns_state(self, sample_pipeline_path: Path, state_path: Path):
    config = load_pipeline(sample_pipeline_path)
    engine = PipelineEngine(config, state_path)
    engine.start("test")
    state = engine.status()
    assert state.pipeline_name == "test-pipeline"
    assert state.status == PipelineStatus.PENDING  # start 后为待命
```

- [ ] **Step 3: 运行测试确认全部通过**

```bash
cd /Users/chenyi/ai-project/spark/agents/scheduler && PYTHONPATH=".:../reviewer/check_system" python3 -m pytest tests/test_engine.py -v
```

预期：全部 PASS（如有失败，检查是否有其他测试直接断言 start 后的 status 为 RUNNING）。

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/tests/test_engine.py
git commit -m "test: 适配 PipelineState.start() 返回 PENDING

start() 不再直接进入 RUNNING，更新两个直接断言 RUNNING 的测试。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Hook 脚本添加 `.pipeline-active` 检查

**Files:**
- Modify: `hooks/block-agents-write.sh`
- Modify: `benchmarks/hooks/dump-agent-payload.sh`
- Modify: `benchmarks/hooks/synthesize-benchmark.sh`

- [ ] **Step 1: `block-agents-write.sh` 开头加标记检查**

在 `set -euo pipefail` 之后、`RESOLVED=` 行之前插入：

```bash
# 仅在流水线运行时生效，非流水线场景静默跳过
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi
```

- [ ] **Step 2: `dump-agent-payload.sh` 开头加标记检查**

在 `set -euo pipefail` 之后、`PROJECT_DIR=` 行之前插入：

```bash
# 仅在流水线运行时生效，非流水线场景静默跳过
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi
```

- [ ] **Step 3: `synthesize-benchmark.sh` 开头加标记检查**

在 `set -euo pipefail` 之后、`PROJECT_DIR=` 行之前插入：

```bash
# 仅在流水线运行时生效，非流水线场景静默跳过
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi
```

- [ ] **Step 4: Commit**

```bash
git add hooks/block-agents-write.sh \
        benchmarks/hooks/dump-agent-payload.sh \
        benchmarks/hooks/synthesize-benchmark.sh
git commit -m "feat: hook 脚本添加 .pipeline-active 标记检查

非流水线场景下 hook 静默跳过，不再误触发。
仅当 .pipeline-active 文件存在时 hook 才执行实际逻辑。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 更新 `build.skill.md` Phase 1

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 替换 Phase 1 的 run_id 生成逻辑**

找到 Phase 1 步骤 1（"生成 run_id: `date +%Y%m%d%H%M%S`-`{target_dir}`"），替换为：

```markdown
1. 调用 pipeline-engine start 获取 run_id（唯一生成入口）：

   ```bash
   result=$(PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
   python3 -m pipeline_engine.cli start \
     --pipeline agents/scheduler/pipeline.yaml \
     --state-file review-output/.pipeline-state.tmp \
     --target-dir "{target_dir}" \
     --requirement "placeholder")
   
   run_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
   ```

   然后将临时状态文件移至最终位置：
   
   ```bash
   mkdir -p "review-output/${run_id}"
   mv review-output/.pipeline-state.tmp "review-output/${run_id}/pipeline-state.json"
   ```
```

- [ ] **Step 2: 更新 pm-context.json 写入**

保持步骤 3 不变，路径 `review-output/${run_id}/pm-context.json` 使用从 engine 获取的 run_id。

- [ ] **Step 3: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: build.skill.md Phase 1 调用 engine start 获取 run_id

不再手动 date 生成，改为调用 pipeline-engine start 从 stdout
提取 run_id，保证 Phase 1 和 Phase 2 使用同一个 run_id。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 更新 `build.skill.md` Phase 2

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: Phase 2 入口添加标记文件创建**

在 Phase 2 步骤 2.1（读取 pm-context.json）之后、步骤 2.3（执行循环）之前，插入标记文件和上下文文件的创建步骤：

```markdown
### 步骤 2.2: 激活流水线保护

在进入执行循环前，创建标记文件和上下文文件：

```bash
# 激活 hook（PreToolUse/PostToolUse/Stop 开始生效）
touch .pipeline-active

# 写入当前 run 上下文，Agent 启动时读取
cat > review-output/.current-run <<EOF
{
  "run_id": "{run_id}",
  "target_dir": "{target_dir}",
  "output_dir": "review-output/{run_id}/",
  "scan_path": "{target_dir}/src/main/java"
}
EOF
```
```

- [ ] **Step 2: 移除步骤 2.2 原有的 start 调用**

原步骤 2.2（"初始化 pipeline_engine（如需）"）中 `pipeline-engine start` 调用已不需要（Phase 1 已调用），删除或改为检查逻辑：

```markdown
### 步骤 2.2: 检查流水线状态

确认状态文件存在且 status 为 pending：

```bash
if [ ! -f "review-output/{run_id}/pipeline-state.json" ]; then
    echo "错误: 未找到流水线状态文件。请先运行 /build <需求> 完成 Phase 1。"
    exit 1
fi
```
```

- [ ] **Step 3: Phase 2 循环退出后添加清理**

在执行循环 `action == "done"` 或 `action == "error"` 后、展示最终报告前，插入清理步骤：

```markdown
**循环结束后，清理标记文件和上下文文件：**

```bash
rm -f .pipeline-active
rm -f review-output/.current-run
```

无论流水线成功还是失败，都执行清理。
```

**注意：** 如果 `action == "error"`，也在展示 message 之前先清理标记文件。

- [ ] **Step 4: 更新步骤 2.3 中 next/report 的 state-file 路径**

确认所有 `pipeline-engine next` 和 `pipeline-engine report` 调用都使用正确的状态文件路径：

```bash
--state-file review-output/{run_id}/pipeline-state.json
```

（现有路径已正确，但需确认 - Phase 1 已将状态文件移至此位置）

- [ ] **Step 5: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: build.skill.md Phase 2 管理 .pipeline-active 和 .current-run

Phase 2 开始时创建标记文件激活 hook，结束时删除。
Agent 通过 review-output/.current-run 获取 run 上下文。
Phase 2 不再调用 pipeline-engine start（Phase 1 已完成）。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 更新 `pipeline.yaml` prompt 模板

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 更新 coder prompt_template**

找到 `prompt_template` 中 coder 节点的模板，在开头插入 `.current-run` 读取指令，将 `{review_context}` 引用更新为基于 `.current-run`：

```yaml
prompt_template: |
  开始工作前，先读取 review-output/.current-run 获取 output_dir 和 target_dir。

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

  ⚠️ 边界约束：你只能修改 {target_dir}/src/main/java/ 目录下的 Java 文件和 {target_dir}/pom.xml（如需添加依赖）。禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。

  代码输出目录：从 review-output/.current-run 读取 scan_path
```

- [ ] **Step 2: 更新 reviewer prompt_template**

在 reviewer 节点的 prompt 开头插入 `.current-run` 读取指令：

```yaml
prompt_template: |
  开始工作前，先读取 review-output/.current-run 获取 output_dir 和 scan_path。

  你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。

  1. 调用 MCP tool `fuck-u-code analyze` 扫描 {target_dir}/src/main/java
     产出 quality.json，保存到 review-output/{run_id}/quality.json
     （如 MCP 调用失败，记录警告后继续第 2 步）

  2. 读取 agents/reviewer/check_system/rules/ai-checklist.yaml（50条审查清单）
     读取 review-output/{run_id}/quality.json（如存在）
     对 {target_dir}/src/main/java 下所有 Java 文件执行统一审查：
     - 逐条对照 ai-checklist 检查规范合规 → spec_violations[]
     - 对 quality.json 标红的高分文件做深度分析 → quality_issues[]

  3. 按固定 JSON schema 输出 findings.json，写入 review-output/{run_id}/findings.json
     判定 review_status: P0>0 → FAILED, 否则 PASSED

  4. 调用 python3 -m code_check.cli report 合并 quality.json + findings.json → final-review-report.md

  返回: REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR
```

- [ ] **Step 3: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "feat: pipeline.yaml prompt 引导 Agent 读取 .current-run

在 coder 和 reviewer 的 prompt 开头添加读取 review-output/.current-run
的指令，确保 Agent 使用正确的 output_dir 和 scan_path。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: 更新 `CLAUDE.md` — 会话自检规则

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 在 CLAUDE.md 末尾添加会话自检区块**

在 `CLAUDE.md` 文件的「全局规则速查」区块之后、文件末尾之前，插入：

```markdown
## 会话自检

- 每次会话开始时，检查项目根目录是否存在 `.pipeline-active` 标记文件
- 如存在，读取 `review-output/.current-run` 获取 run_id：
  - 如 `pipeline-state.json` 中 status 为 `running` 或 `pending` → 提醒用户「⚠️ 有一条未完成的流水线 (run_id: {run_id})，可以 `/build --resume {run_id}` 恢复」
  - 如 status 为 `completed` 或 `error`，或状态文件不存在 → 提醒用户「`.pipeline-active` 是残留标记，建议手动删除：`rm .pipeline-active && rm -f review-output/.current-run`」
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 添加会话自检规则

检测 .pipeline-active 残留标记，提醒用户恢复流水线或清理。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: 更新 `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 添加标记文件和上下文文件到忽略列表**

在 `.gitignore` 末尾追加：

```gitignore
# pipeline runtime markers
.pipeline-active
review-output/.current-run
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: .gitignore 忽略 .pipeline-active 和 .current-run

这些是运行时标记文件，不应提交到版本库。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: 运行完整测试套件验证

- [ ] **Step 1: 运行引擎测试**

```bash
cd /Users/chenyi/ai-project/spark/agents/scheduler && \
PYTHONPATH=".:../reviewer/check_system" python3 -m pytest tests/ -v
```

预期：全部 PASS。

- [ ] **Step 2: 运行 reviewer check_system 测试**

```bash
cd /Users/chenyi/ai-project/spark/agents/reviewer/check_system && \
python3 -m pytest tests/ -v
```

预期：全部 PASS。

- [ ] **Step 3: 端到端验证 — Phase 1 start 返回 PENDING**

```bash
cd /Users/chenyi/ai-project/spark && \
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json \
  --target-dir "test" \
  --requirement "test requirement"
```

验证：
- stdout JSON 中 `status` 为 `"started"`
- `run_id` 字段存在且格式为 `YYYYMMDDHHmmss-test`
- `/tmp/test-pipeline-state.json` 文件内容中 `status` 为 `"pending"`

清理：
```bash
rm -f /tmp/test-pipeline-state.json
```

- [ ] **Step 4: 端到端验证 — next 触发 PENDING → RUNNING**

```bash
# 先 start 再 next，确认状态转移
cd /Users/chenyi/ai-project/spark && \
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-pipeline-state-2.json \
  --target-dir "test" \
  --requirement "test"

PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli next \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-pipeline-state-2.json
```

验证：
- next 的 stdout JSON 中 `action` 为 `"execute"`
- nodes 数组中第一个节点的 `node_id` 为 `"coder"`
- `/tmp/test-pipeline-state-2.json` 中 `status` 为 `"running"`

清理：
```bash
rm -f /tmp/test-pipeline-state-2.json
```

- [ ] **Step 5: 验证 hook 脚本的标记检查**

```bash
# 没有 .pipeline-active 时，hook 应静默退出
cd /tmp && bash /Users/chenyi/ai-project/spark/hooks/block-agents-write.sh
echo "exit code: $?"
```

预期：exit code 为 `0`（静默跳过）。

```bash
# 创建标记文件后再测试
cd /Users/chenyi/ai-project/spark && touch .pipeline-active
# 模拟一个写入 agents/ 的操作（应被拦截）
export CLAUDE_PROJECT_DIR="/Users/chenyi/ai-project/spark"
export CLAUDE_TOOL_INPUT='{"file_path":"agents/scheduler/pipeline.yaml"}'
bash /Users/chenyi/ai-project/spark/hooks/block-agents-write.sh
echo "exit code: $?"
```

预期：exit code 为 `1`（拦截生效），stderr 输出拦截信息。

清理：
```bash
rm -f /Users/chenyi/ai-project/spark/.pipeline-active
unset CLAUDE_PROJECT_DIR CLAUDE_TOOL_INPUT
```

- [ ] **Step 6: Commit（如有修复）**

如果验证过程中发现问题并修复，提交修复。

---

### 完成检查清单

- [ ] `PipelineState.start()` 生成 run_id 后保持 PENDING
- [ ] `cli.py cmd_start()` 不再覆盖 run_id
- [ ] `_generate_run_id()` 从 cli.py 移除，在 models.py 中定义
- [ ] `build.skill.md` Phase 1 调用 engine start 获取 run_id
- [ ] `build.skill.md` Phase 2 管理 `.pipeline-active` 和 `.current-run`
- [ ] `pipeline.yaml` prompt 模板引导 Agent 读取 `.current-run`
- [ ] 3 个 hook 脚本在 `.pipeline-active` 不存在时静默跳过
- [ ] `CLAUDE.md` 包含残留标记文件自检规则
- [ ] `.gitignore` 忽略 `.pipeline-active` 和 `review-output/.current-run`
- [ ] 所有现有测试通过
