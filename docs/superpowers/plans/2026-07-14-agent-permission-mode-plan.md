# Agent 子进程权限自动放行 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 pipeline 体系中增加 `mode` 字段透传，让子 Agent 以 `acceptEdits` 模式启动，避免权限弹窗中断流水线。

**Architecture:** 在 pipeline.yaml → models.py → engine.py → CLI JSON → build.skill.md 链路上增加 `mode` 字段，每个环节只做透传，不改变业务逻辑。默认值 `"default"` 保持向后兼容，`pipeline.yaml` 中显式配置为 `"acceptEdits"`。

**Tech Stack:** Python 3 (dataclasses, PyYAML), Shell (bash)

---

## File Structure

| 文件 | 职责 | 改动类型 |
|------|------|----------|
| `agents/scheduler/pipeline.yaml` | 流水线配置，声明 defaults 和每个 node 的 mode | 修改 |
| `agents/scheduler/pipeline_engine/models.py` | 数据模型：3 个 dataclass 加 mode 字段 | 修改 |
| `agents/scheduler/pipeline_engine/engine.py` | 核心引擎：`_render_nodes()` 透传 mode | 修改 |
| `agents/scheduler/build.skill.md` | 流水线入口：Agent 工具调用加 mode 参数 | 修改 |
| `agents/scheduler/tests/conftest.py` | 测试夹具：YAML 和 dict 增加 mode | 修改 |
| `agents/scheduler/tests/test_models.py` | 模型测试：覆盖 mode 字段 | 修改 |
| `agents/scheduler/tests/test_engine.py` | 引擎测试：验证 mode 渲染和回退逻辑 | 修改 |
| `agents/scheduler/tests/test_config.py` | 配置测试：验证 YAML 加载 mode | 修改 |

---

### Task 1: pipeline.yaml — 配置 mode 字段

**Files:**
- Modify: `agents/scheduler/pipeline.yaml:9-17` (defaults), `agents/scheduler/pipeline.yaml:20-51` (coder node), `agents/scheduler/pipeline.yaml:53-91` (reviewer node)

- [ ] **Step 1: 在 defaults 中加 `mode: acceptEdits`**

在 defaults 块末尾（`project_name: ""` 之后）加一行：

```yaml
defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]
  base_path: "."
  project_name: ""
  mode: acceptEdits
```

- [ ] **Step 2: 在 coder 节点中加 `mode: acceptEdits`**

在 coder 节点 `timeout: 900s` 之前加一行：

```yaml
  - id: coder
    type: agent
    agent: coder
    description: "根据需求生成 Spring Boot 3 Java 代码，遵守 agents/coder/ 下的所有规范"
    mode: acceptEdits
    prompt_template: |
      ...
    timeout: 900s
```

- [ ] **Step 3: 在 reviewer 节点中加 `mode: acceptEdits`**

在 reviewer 节点 `timeout: 600s` 之前加一行：

```yaml
  - id: reviewer
    type: agent
    agent: reviewer
    description: "对 coder 产出的代码执行双层审查：Layer 1 Python CLI 预检 + Layer 2 AI 语义检查"
    mode: acceptEdits
    prompt_template: |
      ...
    timeout: 600s
```

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "feat(pipeline): defaults 和节点增加 mode: acceptEdits 配置"
```

---

### Task 2: models.py — 3 个 dataclass 增加 mode 字段

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py:61-77` (PipelineDefaults)
- Modify: `agents/scheduler/pipeline_engine/models.py:143-175` (NodeConfig)
- Modify: `agents/scheduler/pipeline_engine/models.py:423-441` (NodeToExecute)

- [ ] **Step 1: PipelineDefaults 加 mode 字段**

在 `PipelineDefaults` dataclass 中加 `mode: str = "default"`：

```python
@dataclass
class PipelineDefaults:
    """全局默认值，对应 pipeline.yaml 中的 ``defaults`` 节点。"""
    timeout: str = "600s"
    max_retries: int = 3
    block_on: list[str] = field(default_factory=lambda: ["P0"])
    mode: str = "default"
```

- [ ] **Step 2: PipelineDefaults.from_dict 处理 mode**

在 `from_dict` 中加 mode 提取：

```python
    @classmethod
    def from_dict(cls, d: dict) -> "PipelineDefaults":
        if not isinstance(d, dict):
            raise ValueError(f"defaults 必须是 dict，实际类型为 {type(d).__name__}")
        return cls(
            timeout=d.get("timeout", "600s"),
            max_retries=d.get("max_retries", 3),
            block_on=d.get("block_on", ["P0"]),
            mode=d.get("mode", "default"),
        )
```

- [ ] **Step 3: PipelineDefaults.to_dict 加 mode**

```python
    def to_dict(self) -> dict:
        return {
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "block_on": self.block_on,
            "mode": self.mode,
        }
```

- [ ] **Step 4: NodeConfig 加 mode 字段（Optional，None 时回退到 defaults）**

```python
@dataclass
class NodeConfig:
    """单个 DAG 节点，对应 pipeline.yaml ``nodes`` 列表中的一项。"""
    id: str
    type: str              # "agent"
    agent: str
    description: str
    prompt_template: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    timeout: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    mode: Optional[str] = None
```

- [ ] **Step 5: NodeConfig.from_dict 处理 mode**

在 `from_dict` 返回中加 `mode=d.get("mode")`：

```python
        return cls(
            id=d["id"],
            type=d["type"],
            agent=d["agent"],
            description=d["description"],
            prompt_template=d["prompt_template"],
            inputs=d.get("inputs", {}),
            outputs=d.get("outputs", {}),
            timeout=d.get("timeout"),
            depends_on=d.get("depends_on", []),
            mode=d.get("mode"),
        )
```

- [ ] **Step 6: NodeConfig.to_dict 加 mode（仅非 None 时输出）**

在 `to_dict` 方法中，`if self.depends_on:` 块之后加：

```python
        if self.mode is not None:
            d["mode"] = self.mode
```

- [ ] **Step 7: NodeToExecute 加 mode 字段**

```python
@dataclass
class NodeToExecute:
    """`next` 命令返回的单个待执行节点。"""
    node_id: str
    agent_type: str
    prompt: str          # 已渲染完整的 prompt
    timeout: str
    round: int
    phase: str           # "code_generation" | "review" | "fix"
    mode: str = "default"
```

- [ ] **Step 8: NodeToExecute.to_dict 加 mode**

```python
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "agent_type": self.agent_type,
            "prompt": self.prompt,
            "timeout": self.timeout,
            "round": self.round,
            "phase": self.phase,
            "mode": self.mode,
        }
```

- [ ] **Step 9: Commit**

```bash
git add agents/scheduler/pipeline_engine/models.py
git commit -m "feat(models): PipelineDefaults/NodeConfig/NodeToExecute 增加 mode 字段"
```

---

### Task 3: engine.py — _render_nodes 透传 mode

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py:298-313` (_render_nodes)

- [ ] **Step 1: _render_nodes() 取 node.mode 或 defaults.mode**

修改 `_render_nodes`，在构造 `NodeToExecute` 之前计算 mode：

```python
    def _render_nodes(self, node_configs: list) -> list[NodeToExecute]:
        """将节点配置渲染为可执行的 NodeToExecute 列表。"""
        rendered = []
        for node in node_configs:
            prompt = self._render_prompt(node)
            phase = self._determine_phase(node)
            timeout = node.timeout or self.config.defaults.timeout
            mode = node.mode or self.config.defaults.mode
            rendered.append(NodeToExecute(
                node_id=node.id,
                agent_type=node.agent,
                prompt=prompt,
                timeout=timeout,
                round=self.state.round,
                phase=phase,
                mode=mode,
            ))
        return rendered
```

- [ ] **Step 2: Commit**

```bash
git add agents/scheduler/pipeline_engine/engine.py
git commit -m "feat(engine): _render_nodes 透传 mode 字段到 NodeToExecute"
```

---

### Task 4: build.skill.md — Agent 工具调用加 mode 参数

**Files:**
- Modify: `agents/scheduler/build.skill.md:160-165` (Agent 工具调用步骤)

- [ ] **Step 1: Agent 工具调用步骤加 mode 参数**

在第 3 步「启动子 Agent」的子步骤 a 中，增加 `mode`：

```markdown
a. 使用 Agent 工具启动子 Agent：
   - `subagent_type` 使用节点返回的 `agent_type`
   - `prompt` 使用节点返回的已渲染 `prompt`
   - `mode` 使用节点返回的 `mode` 值
   - 超时参考节点返回的 `timeout`
```

- [ ] **Step 2: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat(build): Agent 工具调用增加 mode 参数透传"
```

---

### Task 5: 测试 — conftest.py 更新夹具

**Files:**
- Modify: `agents/scheduler/tests/conftest.py:10-82` (SAMPLE_PIPELINE_YAML)
- Modify: `agents/scheduler/tests/conftest.py:103-136` (sample_pipeline_dict)

- [ ] **Step 1: SAMPLE_PIPELINE_YAML 的 defaults 加 mode**

在 defaults 块末尾加 `mode: acceptEdits`：

```yaml
defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]
  mode: acceptEdits
```

- [ ] **Step 2: SAMPLE_PIPELINE_YAML 的 coder 节点加 mode**

```yaml
  - id: coder
    type: agent
    agent: coder
    description: "Generate code"
    mode: acceptEdits
    prompt_template: |
      ...
```

- [ ] **Step 3: SAMPLE_PIPELINE_YAML 的 reviewer 节点加 mode**

```yaml
  - id: reviewer
    type: agent
    agent: reviewer
    description: "Review code"
    mode: acceptEdits
    prompt_template: |
      ...
```

- [ ] **Step 4: sample_pipeline_dict 的 defaults 加 mode**

在 defaults dict 中加 `"mode": "acceptEdits"`：

```python
        "defaults": {"timeout": "600s", "max_retries": 3, "block_on": ["P0"], "mode": "acceptEdits"},
```

- [ ] **Step 5: sample_pipeline_dict 的两个 node 各加 mode**

在 coder node dict 中加 `"mode": "acceptEdits"`：

```python
            {
                "id": "coder", "type": "agent", "agent": "coder",
                "description": "Generate code",
                "prompt_template": "Generate: {requirement} to {output_dir}src/main/java",
                "inputs": {"requirement": "${user_input}"},
                "outputs": {"target_dir": "{output_dir}src/main/java"},
                "timeout": "900s",
                "mode": "acceptEdits"
            },
```

在 reviewer node dict 中加 `"mode": "acceptEdits"`：

```python
            {
                "id": "reviewer", "type": "agent", "agent": "reviewer",
                "description": "Review code",
                "prompt_template": "Review {output_dir}src/main/java. Output: review-output/{run_id}/",
                "inputs": {"coder_output": "${coder.outputs.target_dir}"},
                "outputs": {"final_report": "review-output/{run_id}/final-review-report.md"},
                "timeout": "600s",
                "mode": "acceptEdits"
            }
```

- [ ] **Step 6: 运行现有测试确认夹具更新后不破坏测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```
Expected: 部分测试可能因缺少 mode 断言而失败，这是预期的——下一步更新测试用例。

- [ ] **Step 7: Commit**

```bash
git add agents/scheduler/tests/conftest.py
git commit -m "test(conftest): 测试夹具增加 mode: acceptEdits"
```

---

### Task 6: 测试 — test_models.py 更新用例

**Files:**
- Modify: `agents/scheduler/tests/test_models.py:92-109` (TestPipelineDefaults)
- Modify: `agents/scheduler/tests/test_models.py:160-200` (TestNodeConfig)
- Modify: `agents/scheduler/tests/test_models.py:380-391` (TestNodeToExecute)

- [ ] **Step 1: TestPipelineDefaults.test_from_dict_full 加 mode 断言**

```python
    def test_from_dict_full(self):
        d = {"timeout": "300s", "max_retries": 5, "block_on": ["P0", "P1"], "mode": "bypassPermissions"}
        obj = PipelineDefaults.from_dict(d)
        assert obj.timeout == "300s"
        assert obj.max_retries == 5
        assert obj.block_on == ["P0", "P1"]
        assert obj.mode == "bypassPermissions"
```

- [ ] **Step 2: TestPipelineDefaults 加 mode 默认值测试**

在 `test_from_dict_defaults` 中追加断言：

```python
    def test_from_dict_defaults(self):
        obj = PipelineDefaults.from_dict({})
        assert obj.timeout == "600s"
        assert obj.max_retries == 3
        assert obj.block_on == ["P0"]
        assert obj.mode == "default"
```

- [ ] **Step 3: TestNodeConfig.test_from_dict_minimal 加 mode 默认值断言**

在末尾追加：

```python
        assert obj.mode is None
```

- [ ] **Step 4: TestNodeConfig.test_from_dict_full 加 mode**

在 dict 中加 `"mode": "acceptEdits"`，断言中加：

```python
    def test_from_dict_full(self):
        d = {"id": "reviewer", "type": "agent", "agent": "reviewer",
             "description": "Review", "prompt_template": "Review.",
             "inputs": {"src": "path"}, "outputs": {"report": "path"},
             "timeout": "600s", "depends_on": ["coder"], "mode": "acceptEdits"}
        obj = NodeConfig.from_dict(d)
        assert obj.inputs == {"src": "path"}
        assert obj.outputs == {"report": "path"}
        assert obj.timeout == "600s"
        assert obj.depends_on == ["coder"]
        assert obj.mode == "acceptEdits"
```

- [ ] **Step 5: TestNodeToExecute.test_to_dict 加 mode**

```python
    def test_to_dict(self):
        obj = NodeToExecute(node_id="coder", agent_type="coder",
                            prompt="Generate code", timeout="900s",
                            round=1, phase="fix", mode="acceptEdits")
        d = obj.to_dict()
        assert d["node_id"] == "coder"
        assert d["prompt"] == "Generate code"
        assert d["phase"] == "fix"
        assert d["round"] == 1
        assert d["timeout"] == "900s"
        assert d["mode"] == "acceptEdits"
```

- [ ] **Step 6: 运行模型测试**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add agents/scheduler/tests/test_models.py
git commit -m "test(models): 增加 mode 字段的单元测试"
```

---

### Task 7: 测试 — test_engine.py 验证 mode 透传和回退

**Files:**
- Modify: `agents/scheduler/tests/test_engine.py` (新增测试方法)

- [ ] **Step 1: 在 TestPipelineEngineNext 类中加 mode 透传测试**

在 `test_first_next_returns_start_node` 中追加 mode 断言：

```python
    def test_first_next_returns_start_node(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("build something")
        action = engine.next()
        assert action.action == ActionType.EXECUTE
        assert len(action.nodes) == 1
        assert action.nodes[0].node_id == "coder"
        assert "build something" in action.nodes[0].prompt
        assert action.nodes[0].phase == "code_generation"
        assert action.nodes[0].round == 0
        assert action.nodes[0].mode == "acceptEdits"
```

- [ ] **Step 2: 在 TestPipelineEngineNext 类中加 node 覆盖 defaults mode 的测试**

新增测试方法：

```python
    def test_node_mode_overrides_defaults(self, tmp_path: Path, state_path: Path):
        """节点级别的 mode 覆盖 defaults.mode"""
        import yaml
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine
        from pipeline_engine.models import NodeStatus

        # 构造 YAML：defaults.mode="default"，coder 节点 mode="bypassPermissions"
        yaml_content = """
name: test-override
version: "1.0"
description: "Test mode override"
defaults:
  timeout: 600s
  max_retries: 3
  mode: default
nodes:
  - id: coder
    type: agent
    agent: coder
    description: "Generate"
    prompt_template: "Generate {requirement}"
    mode: bypassPermissions
    timeout: 900s
  - id: reviewer
    type: agent
    agent: reviewer
    description: "Review"
    prompt_template: "Review. Return REVIEW_PASSED or REVIEW_FAILED."
    mode: acceptEdits
    timeout: 600s
edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: ""
"""
        p = tmp_path / "override-mode.yaml"
        p.write_text(yaml_content)

        config = load_pipeline(p)
        engine = PipelineEngine(config, state_path)
        engine.start("test")

        # coder 应该使用自己的 mode
        action = engine.next()
        assert action.nodes[0].node_id == "coder"
        assert action.nodes[0].mode == "bypassPermissions"

        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()
        # reviewer 应该使用自己的 mode
        assert action.nodes[0].node_id == "reviewer"
        assert action.nodes[0].mode == "acceptEdits"
```

- [ ] **Step 3: 在 TestPipelineEngineNext 类中加 mode 默认回退测试**

新增测试方法：

```python
    def test_mode_falls_back_to_defaults(self, tmp_path: Path, state_path: Path):
        """节点未指定 mode 时回退到 defaults.mode"""
        import yaml
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine

        yaml_content = """
name: test-fallback
version: "1.0"
description: "Test mode fallback"
defaults:
  timeout: 600s
  max_retries: 3
  mode: plan
nodes:
  - id: coder
    type: agent
    agent: coder
    description: "Generate"
    prompt_template: "Generate {requirement}"
    timeout: 900s
  - id: reviewer
    type: agent
    agent: reviewer
    description: "Review"
    prompt_template: "Review. Return REVIEW_PASSED or REVIEW_FAILED."
    timeout: 600s
edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: ""
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: ""
"""
        p = tmp_path / "fallback-mode.yaml"
        p.write_text(yaml_content)

        config = load_pipeline(p)
        engine = PipelineEngine(config, state_path)
        engine.start("test")

        action = engine.next()
        # coder 没有指定 mode，应该回退到 defaults.mode = "plan"
        assert action.nodes[0].node_id == "coder"
        assert action.nodes[0].mode == "plan"
```

- [ ] **Step 4: 运行引擎测试**

```bash
cd agents/scheduler && python3 -m pytest tests/test_engine.py -v
```
Expected: 全部 PASS（含新增的 mode 测试）

- [ ] **Step 5: Commit**

```bash
git add agents/scheduler/tests/test_engine.py
git commit -m "test(engine): 增加 mode 透传和回退逻辑的测试"
```

---

### Task 8: 全量测试验证

**Files:** 无新建

- [ ] **Step 1: 运行全部测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 2: 手动验证 CLI next 命令输出含 mode 字段**

```bash
cd /Users/chenyi/ai-project/spark

# 启动一个测试流水线
result=$(PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-mode-pipeline-state.json \
  --base-path "." \
  --project-name "test-mode" \
  --requirement "test mode field")

run_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "run_id: $run_id"

# 获取 next，检查 mode 字段
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli next \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-mode-pipeline-state.json | python3 -m json.tool
```
Expected: JSON 输出中 `nodes[0].mode` 为 `"acceptEdits"`

- [ ] **Step 3: 清理测试状态**

```bash
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli reset \
  --state-file /tmp/test-mode-pipeline-state.json
rm -f /tmp/test-mode-pipeline-state.json
rm -rf review-output/${run_id} 2>/dev/null
```

- [ ] **Step 4: Commit（如有临时文件清理）**

---

### Task 9: 最终验证 — 全量测试 + 清理

**Files:** 无新建

- [ ] **Step 1: 最终全量测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```
Expected: 全部 PASS

- [ ] **Step 2: 查看 git log 确认 commit 链完整**

```bash
git log --oneline -10
```
Expected: 看到 7 个 feat/test commit

---

## 自检

| 检查项 | 结果 |
|--------|------|
| Spec 覆盖 | ✅ spec 中 4.1-4.5 全部有对应 Task |
| Placeholder | ✅ 无 TBD/TODO，所有步骤有具体代码 |
| 类型一致性 | ✅ `mode: str` 在 models.py → engine.py → NodeToExecute 全程一致，`Optional[str]` 在 NodeConfig 中用于区分未设置和显式设置 |
