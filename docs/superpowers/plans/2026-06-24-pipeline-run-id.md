# Pipeline Run ID 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每次 `/build` 运行生成唯一 run_id（格式 `YYYYMMDDHHmmss-NNN`），reviewer Agent 拿到后传给 check_system 作为输出子目录，实现产物隔离。

**Architecture:** 最小化改动——调度器只负责生成 run_id，不管理目录。run_id 存入 PipelineState，通过 prompt 模板变量 `{run_id}` 注入到 reviewer 的 prompt 中，reviewer Agent 读到后传给 check_system 的 `--output-dir`。coder 不需要 run_id。

**Tech Stack:** Python 3, dataclasses, 无新依赖

---

## 数据流

```
scheduler start → 生成 run_id（如 20260624103000-001）
       │             存入 PipelineState.run_id
       │             写入 pipeline-state.json
       │             返回给 build.skill.md（可选，仅用于报告）
       │
scheduler next (reviewer) → _render_prompt 注入 {run_id}
       │             生成: "请使用以下输出目录：review-output/20260624103000-001/"
       │
build.skill.md → Agent 工具启动 reviewer，prompt 已包含目录信息
       │
reviewer Agent → 调用 check_system 时传入 --output-dir review-output/<run_id>/
       │
check_system → 产物写入 review-output/20260624103000-001/
```

---

### Task 1: PipelineState 新增 run_id 字段

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py:286-370`
- Modify: `agents/scheduler/tests/test_models.py` — TestPipelineState

- [ ] **Step 1: 写测试**

在 `TestPipelineState` 类末尾添加：

```python
    def test_run_id_present(self):
        obj = PipelineState(pipeline_name="test", run_id="20260624103000-001")
        assert obj.run_id == "20260624103000-001"

    def test_run_id_default(self):
        obj = PipelineState(pipeline_name="test")
        assert obj.run_id == ""

    def test_run_id_roundtrip(self):
        obj = PipelineState(pipeline_name="test", run_id="20260624103000-001")
        obj.start()
        d = obj.to_dict()
        assert d["run_id"] == "20260624103000-001"
        restored = PipelineState.from_dict(d)
        assert restored.run_id == "20260624103000-001"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py::TestPipelineState::test_run_id_present -v
```
Expected: FAIL — `run_id` 未定义

- [ ] **Step 3: 修改 PipelineState**

在 `PipelineState` 的字段定义中（`updated_at: str = ""` 之后）新增一行：

```python
    run_id: str = ""
```

在 `from_dict` 中（`updated_at=d.get("updated_at", ""),` 之后）新增：

```python
            run_id=d.get("run_id", ""),
```

在 `to_dict` 中（`"updated_at": self.updated_at,` 之后）新增：

```python
            "run_id": self.run_id,
```

在 `start` 方法的 `self.started_at = ...` 之后，`self._touch()` 之前新增（如果 run_id 为空则自动生成，作为安全兜底）：

```python
        if not self.run_id:
            self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-000"
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py::TestPipelineState -v
```
Expected: 11 passed（原有 8 个 + 新增 3 个）

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd agents/scheduler && python3 -m pytest tests/ -q
```
Expected: 101 passed

- [ ] **Step 6: Commit**

```bash
git add agents/scheduler/pipeline_engine/models.py agents/scheduler/tests/test_models.py
git commit -m "feat: add run_id field to PipelineState for per-run output isolation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: CLI start 命令生成 run_id

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py:22-53` — cmd_start
- Modify: `agents/scheduler/tests/test_cli.py` — TestCLIStart

- [ ] **Step 1: 写测试**

在 `TestCLIStart` 类末尾添加：

```python
    def test_start_returns_run_id(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "pipeline-state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "run_id" in data
        assert len(data["run_id"]) == 18  # YYYYMMDDHHmmss-NNN
        assert data["run_id"][8] == "T" or data["run_id"][8].isdigit()  # will check format

    def test_run_id_increments_counter(self, tmp_path: Path):
        """Same minute → counter increments: -001, -002."""
        pipeline_file = _make_minimal_pipeline(tmp_path)
        # 在同一秒内调用两次 start，计数器应递增
        result1 = run_cli(["start", "--pipeline", str(pipeline_file),
                           "--state-file", str(tmp_path / "state-a.json"),
                           "--requirement", "test a"], cwd=tmp_path)
        result2 = run_cli(["start", "--pipeline", str(pipeline_file),
                           "--state-file", str(tmp_path / "state-b.json"),
                           "--requirement", "test b"], cwd=tmp_path)
        data1 = json.loads(result1.stdout)
        data2 = json.loads(result2.stdout)
        # 时间戳前缀相同（同一秒内），但计数器递增
        prefix1 = data1["run_id"][:15]
        prefix2 = data2["run_id"][:15]
        assert prefix1 == prefix2
        assert data1["run_id"][-3:] != data2["run_id"][-3:]
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py::TestCLIStart::test_start_returns_run_id -v
```
Expected: FAIL — `run_id` 不在返回的 JSON 中

- [ ] **Step 3: 实现 run_id 生成函数**

在 `cli.py` 的 `cmd_start` 函数上方添加辅助函数：

```python
def _generate_run_id(output_base: Path) -> str:
    """生成唯一运行 ID，格式: YYYYMMDDHHmmss-NNN

    扫描 output_base 目录下当天已有的子目录名，计数器 +1。
    例如当天第 1 次运行 → 20260624103000-001。
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    prefix = now.strftime("%Y%m%d%H%M%S")

    # 扫描当天已有目录，找出最大计数器
    max_counter = 0
    if output_base.exists():
        for entry in output_base.iterdir():
            if entry.is_dir() and entry.name.startswith(prefix):
                try:
                    counter = int(entry.name.split("-")[-1])
                    max_counter = max(max_counter, counter)
                except (ValueError, IndexError):
                    pass

    return f"{prefix}-{max_counter + 1:03d}"
```

在 `cmd_start` 中，`state = engine.start(args.requirement)` 之后、`print` 之前添加：

```python
    # 生成 run_id 并存入状态
    from pathlib import Path
    run_id = _generate_run_id(Path("review-output"))
    state.run_id = run_id
    engine._save_state()
```

同时更新 `print` 的输出 JSON，在 `"round": 0,` 之后添加：

```python
        "run_id": run_id,
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py::TestCLIStart -v
```
Expected: 4 passed

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd agents/scheduler && python3 -m pytest tests/ -q
```
Expected: 103 passed

- [ ] **Step 6: Commit**

```bash
git add agents/scheduler/pipeline_engine/cli.py agents/scheduler/tests/test_cli.py
git commit -m "feat: CLI start generates unique run_id with timestamp+counter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: engine._render_prompt 注入 run_id 变量

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py:327-332` — variables dict
- Modify: `agents/scheduler/tests/test_engine.py` — 已有测试验证 prompt 内容

- [ ] **Step 1: 修改 _render_prompt 的 variables**

在 `variables` 字典中，`"max_retries"` 之后添加：

```python
            "run_id": self.state.run_id,
```

完整变为：

```python
        variables = {
            "requirement": self.state.requirement,
            "review_context": review_context,
            "round": str(self.state.round),
            "max_retries": str(self.config.defaults.max_retries),
            "run_id": self.state.run_id,
        }
```

- [ ] **Step 2: 写测试验证 run_id 出现在 prompt 中**

在 `test_engine.py` 的 `TestPipelineEngineNext` 类中添加：

```python
    def test_prompt_contains_run_id(self, sample_pipeline_path: Path, state_path: Path):
        """reviewer prompt should include run_id from state."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        # Manually set run_id on state (simulating what CLI start does)
        engine._ensure_state()
        engine.state.run_id = "20260624103000-001"
        engine._save_state()
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()  # reviewer
        assert action.nodes[0].node_id == "reviewer"
        assert "20260624103000-001" in action.nodes[0].prompt
```

- [ ] **Step 3: 运行全量测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -q
```
Expected: 104 passed（现有 98 + Task 1 新增 3 + Task 2 新增 2 + 本 Task 新增 1 = 104）

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/pipeline_engine/engine.py agents/scheduler/tests/test_engine.py
git commit -m "feat: inject {run_id} variable into prompt template rendering

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: pipeline.yaml reviewer prompt_template 引用 {run_id}

**Files:**
- Modify: `agents/scheduler/pipeline.yaml` — reviewer 节点

- [ ] **Step 1: 在 reviewer prompt_template 末尾添加输出目录指令**

在 `pipeline.yaml` 第 66 行（`你的最终回复必须且只能是这三种状态之一。`）之后，追加：

```yaml
      4. 执行 review 前，请设置输出目录为 review-output/{run_id}/，将所有产物写入该目录。

      输出目录：review-output/{run_id}/
```

注意缩进对齐（6 个空格，与 1-3 的缩进一致）。

- [ ] **Step 2: 验证 YAML 可正常加载**

```bash
cd agents/scheduler && python3 -c "
from pathlib import Path
from pipeline_engine.config import load_pipeline
config = load_pipeline(Path('pipeline.yaml'))
reviewer = config.get_node('reviewer')
assert '{run_id}' in reviewer.prompt_template
print('OK: reviewer prompt_template contains {run_id}')
"
```
Expected: `OK: reviewer prompt_template contains {run_id}`

- [ ] **Step 3: 运行全量测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -q
```
Expected: 104 passed

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "feat: add {run_id} output directory instruction to reviewer prompt

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 手动测试 run_id 生成和注入**

```bash
cd agents/scheduler

# 启动，观察 run_id
python3 -m pipeline_engine.cli start \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-runid-state.json \
  --requirement "测试 run_id"

# 查看返回的 run_id
# 再到 reviewer prompt 中确认 run_id 已渲染
python3 -m pipeline_engine.cli next \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-runid-state.json

python3 -m pipeline_engine.cli report \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-runid-state.json \
  --node coder --status success

python3 -m pipeline_engine.cli next \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-runid-state.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['nodes'][0]['prompt'])"

# 清理
python3 -m pipeline_engine.cli reset --state-file /tmp/test-runid-state.json
```

- [ ] **Step 2: 验证连续两次运行生成不同 run_id**

```bash
cd agents/scheduler
python3 -m pipeline_engine.cli start --pipeline pipeline.yaml --state-file /tmp/r1.json --requirement "run 1"
python3 -m pipeline_engine.cli start --pipeline pipeline.yaml --state-file /tmp/r2.json --requirement "run 2"
python3 -m pipeline_engine.cli reset --state-file /tmp/r1.json
python3 -m pipeline_engine.cli reset --state-file /tmp/r2.json
```
Expected: 两次 start 返回的 `run_id` 不同。
