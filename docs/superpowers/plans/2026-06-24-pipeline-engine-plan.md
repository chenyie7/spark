# Pipeline Engine 调度器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 Python 调度器包 `pipeline_engine/`，解析 `pipeline.yaml` 中的 DAG 定义，通过 CLI 接口向 Claude Code Agent 提供步进式执行指令

**Architecture:** 6 个模块（models / config / engine / reporter / cli / tests），对齐 check_system/code_check/ 模式。调度器不执行 Agent，只做路由决策。状态持久化到 `review-output/pipeline-state.json`

**Tech Stack:** Python 3.11+, PyYAML, dataclasses, argparse, pytest

---

### Task 1: 项目骨架搭建

**Files:**
- Create: `agents/scheduler/pipeline_engine/__init__.py`
- Create: `agents/scheduler/requirements.txt`
- Create: `agents/scheduler/tests/__init__.py`
- Create: `agents/scheduler/tests/conftest.py`

- [ ] **Step 1: 创建 Python 包目录和空文件**

```bash
mkdir -p agents/scheduler/pipeline_engine
mkdir -p agents/scheduler/tests
```

- [ ] **Step 2: 写入 `pipeline_engine/__init__.py`**

```python
"""Pipeline Engine — DAG-based workflow scheduler for code generation pipelines.

Parses pipeline.yaml, manages DAG state machine, and provides a CLI
for Claude Code agents to execute nodes step-by-step.
"""
```

- [ ] **Step 3: 写入 `tests/__init__.py`**

```python
"""Tests for pipeline_engine."""
```

- [ ] **Step 4: 写入 `requirements.txt`**

```
PyYAML>=6.0
```

- [ ] **Step 5: 写入 `tests/conftest.py`**

```python
import json
import pytest
from pathlib import Path

SAMPLE_PIPELINE_YAML = """
name: test-pipeline
version: "1.0"
description: "Test pipeline for unit tests"

defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]

nodes:
  - id: coder
    type: agent
    agent: coder
    description: "Generate code"
    prompt_template: |
      Generate code for: {requirement}
      {review_context}
    inputs:
      requirement: "${user_input}"
    outputs:
      target_dir: "src/main/java"
    timeout: 900s

  - id: reviewer
    type: agent
    agent: reviewer
    description: "Review code"
    prompt_template: |
      Review the code in {coder_output}.
      Return REVIEW_PASSED, REVIEW_FAILED, or REVIEW_ERROR.
    inputs:
      coder_output: "${coder.outputs.target_dir}"
    outputs:
      final_report: "review-output/final-review-report.md"
    timeout: 600s

edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: "coder done → reviewer"

  - from: reviewer
    to: coder
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: "review FAILED → fix loop"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: "review PASSED → done"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: "max_retries reached → done"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: "review ERROR → done"
"""


@pytest.fixture
def sample_pipeline_yaml() -> str:
    return SAMPLE_PIPELINE_YAML


@pytest.fixture
def sample_pipeline_path(tmp_path: Path) -> Path:
    p = tmp_path / "test-pipeline.yaml"
    p.write_text(SAMPLE_PIPELINE_YAML)
    return p


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "pipeline-state.json"


@pytest.fixture
def sample_pipeline_dict() -> dict:
    return json.loads("""
    {
        "name": "test-pipeline",
        "version": "1.0",
        "description": "Test pipeline",
        "defaults": {"timeout": "600s", "max_retries": 3, "block_on": ["P0"]},
        "nodes": [
            {
                "id": "coder", "type": "agent", "agent": "coder",
                "description": "Generate code",
                "prompt_template": "Generate: {requirement}",
                "inputs": {"requirement": "${user_input}"},
                "outputs": {"target_dir": "src/main/java"},
                "timeout": "900s"
            },
            {
                "id": "reviewer", "type": "agent", "agent": "reviewer",
                "description": "Review code",
                "prompt_template": "Review and return verdict.",
                "inputs": {"coder_output": "${coder.outputs.target_dir}"},
                "outputs": {"final_report": "review-output/final-review-report.md"},
                "timeout": "600s"
            }
        ],
        "edges": [
            {"from": "coder", "to": "reviewer", "trigger": "on_success", "description": ""},
            {"from": "reviewer", "to": "coder", "trigger": "on_condition", "condition": {"status": "REVIEW_FAILED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_PASSED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_FAILED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_ERROR"}, "description": ""}
        ]
    }
    """)
```

- [ ] **Step 6: 验证骨架**

```bash
python3 -c "from pipeline_engine import __init__; print('pipeline_engine OK')"
```

Expected: 需要在 `agents/scheduler/` 目录下运行，或设置 PYTHONPATH。

---

### Task 2: models.py — 枚举和基础类型

**Files:**
- Create: `agents/scheduler/pipeline_engine/models.py`
- Test: `agents/scheduler/tests/test_models.py`

- [ ] **Step 1: 写枚举测试**

```python
# tests/test_models.py
import pytest
from pipeline_engine.models import (
    TriggerType, NodeStatus, PipelineStatus, ActionType,
)


class TestTriggerType:
    def test_on_success(self):
        assert TriggerType.ON_SUCCESS == "on_success"

    def test_on_condition(self):
        assert TriggerType.ON_CONDITION == "on_condition"

    def test_from_str(self):
        assert TriggerType("on_success") == TriggerType.ON_SUCCESS
        assert TriggerType("on_condition") == TriggerType.ON_CONDITION

    def test_invalid_trigger(self):
        with pytest.raises(ValueError):
            TriggerType("invalid")


class TestNodeStatus:
    def test_values(self):
        assert NodeStatus.SUCCESS == "success"
        assert NodeStatus.FAILED == "failed"
        assert NodeStatus.ERROR == "error"
        assert NodeStatus.SKIPPED == "skipped"


class TestPipelineStatus:
    def test_values(self):
        assert PipelineStatus.PENDING == "pending"
        assert PipelineStatus.RUNNING == "running"
        assert PipelineStatus.COMPLETED == "completed"
        assert PipelineStatus.ERROR == "error"


class TestActionType:
    def test_values(self):
        assert ActionType.EXECUTE == "execute"
        assert ActionType.DONE == "done"
        assert ActionType.ERROR == "error"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: 写枚举定义**

```python
# pipeline_engine/models.py
"""Data models for pipeline-engine — typed bindings for pipeline.yaml and runtime state.

All model classes follow the Spring Boot @ConfigurationProperties pattern:
YAML structure → strict dataclass tree → from_dict() factory with validation.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional


# ── Enums ──────────────────────────────────────────────────────────


class TriggerType(str, Enum):
    """Edge trigger type."""
    ON_SUCCESS = "on_success"
    ON_CONDITION = "on_condition"


class NodeStatus(str, Enum):
    """Execution status of a single node."""
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    """Overall pipeline lifecycle status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ActionType(str, Enum):
    """Action type returned by the `next` command."""
    EXECUTE = "execute"
    DONE = "done"
    ERROR = "error"
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: 4 passed

---

### Task 3: models.py — 配置实体（PipelineConfig 树）

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py`
- Modify: `agents/scheduler/tests/test_models.py`

- [ ] **Step 1: 写配置实体测试**

```python
# 追加到 tests/test_models.py

class TestPipelineDefaults:
    def test_from_dict_full(self):
        d = {"timeout": "300s", "max_retries": 5, "block_on": ["P0", "P1"]}
        obj = PipelineDefaults.from_dict(d)
        assert obj.timeout == "300s"
        assert obj.max_retries == 5
        assert obj.block_on == ["P0", "P1"]

    def test_from_dict_defaults(self):
        obj = PipelineDefaults.from_dict({})
        assert obj.timeout == "600s"
        assert obj.max_retries == 3
        assert obj.block_on == ["P0"]


class TestEdgeCondition:
    def test_from_dict(self):
        obj = EdgeCondition.from_dict({"status": "REVIEW_FAILED"})
        assert obj.status == "REVIEW_FAILED"


class TestEdgeConfig:
    def test_from_dict_on_success(self):
        d = {"from": "coder", "to": "reviewer", "trigger": "on_success", "description": "go"}
        obj = EdgeConfig.from_dict(d)
        assert obj.from_node == "coder"
        assert obj.to == "reviewer"
        assert obj.trigger == TriggerType.ON_SUCCESS
        assert obj.condition is None
        assert obj.description == "go"

    def test_from_dict_on_condition(self):
        d = {"from": "reviewer", "to": "coder", "trigger": "on_condition",
             "condition": {"status": "REVIEW_FAILED"}, "description": "fix"}
        obj = EdgeConfig.from_dict(d)
        assert obj.from_node == "reviewer"
        assert obj.to == "coder"
        assert obj.trigger == TriggerType.ON_CONDITION
        assert obj.condition is not None
        assert obj.condition.status == "REVIEW_FAILED"


class TestNodeConfig:
    def test_from_dict_minimal(self):
        d = {"id": "coder", "type": "agent", "agent": "coder",
             "description": "Gen code", "prompt_template": "Generate: {requirement}"}
        obj = NodeConfig.from_dict(d)
        assert obj.id == "coder"
        assert obj.type == "agent"
        assert obj.agent == "coder"
        assert obj.prompt_template == "Generate: {requirement}"
        assert obj.inputs == {}
        assert obj.outputs == {}
        assert obj.timeout is None
        assert obj.depends_on == []

    def test_from_dict_full(self):
        d = {"id": "reviewer", "type": "agent", "agent": "reviewer",
             "description": "Review", "prompt_template": "Review.",
             "inputs": {"src": "path"}, "outputs": {"report": "path"},
             "timeout": "600s", "depends_on": ["coder"]}
        obj = NodeConfig.from_dict(d)
        assert obj.inputs == {"src": "path"}
        assert obj.outputs == {"report": "path"}
        assert obj.timeout == "600s"
        assert obj.depends_on == ["coder"]


class TestPipelineConfig:
    def test_from_dict(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        assert obj.name == "test-pipeline"
        assert obj.version == "1.0"
        assert obj.defaults.max_retries == 3
        assert len(obj.nodes) == 2
        assert len(obj.edges) == 5

    def test_get_node(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        node = obj.get_node("coder")
        assert node.id == "coder"
        assert node.agent == "coder"

    def test_get_node_missing(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        with pytest.raises(ValueError, match="Node 'nonexistent' not found"):
            obj.get_node("nonexistent")

    def test_get_outgoing_edges(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        edges = obj.get_outgoing_edges("reviewer")
        assert len(edges) == 4  # → coder, DONE×3

    def test_get_start_nodes(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        start = obj.get_start_nodes()
        assert len(start) == 1
        assert start[0].id == "coder"

    def test_to_dict_roundtrip(self, sample_pipeline_dict):
        obj = PipelineConfig.from_dict(sample_pipeline_dict)
        d = obj.to_dict()
        assert d["name"] == "test-pipeline"
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 5

class TestPipelineConfigMissingField:
    def test_missing_nodes(self):
        d = {"name": "p", "version": "1", "description": "d",
             "defaults": {}, "edges": []}
        with pytest.raises(ValueError, match="nodes"):
            PipelineConfig.from_dict(d)

    def test_missing_edges(self):
        d = {"name": "p", "version": "1", "description": "d",
             "defaults": {}, "nodes": []}
        with pytest.raises(ValueError, match="edges"):
            PipelineConfig.from_dict(d)
```

需要在文件顶部添加 import：
```python
from pipeline_engine.models import (
    TriggerType, NodeStatus, PipelineStatus, ActionType,
    PipelineDefaults, EdgeCondition, EdgeConfig, NodeConfig, PipelineConfig,
)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: FAIL — PipelineDefaults, EdgeCondition, EdgeConfig, NodeConfig, PipelineConfig not defined

- [ ] **Step 3: 写配置实体**

在 `models.py` 中 enum 定义之后追加：

```python
# ── Pipeline Configuration Entities ─────────────────────────────────


@dataclass
class PipelineDefaults:
    """Global default values for all nodes. Maps to pipeline.yaml ``defaults``."""
    timeout: str = "600s"
    max_retries: int = 3
    block_on: list[str] = field(default_factory=lambda: ["P0"])

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineDefaults":
        if not isinstance(d, dict):
            raise ValueError(f"defaults must be a dict, got {type(d).__name__}")
        return cls(
            timeout=d.get("timeout", "600s"),
            max_retries=d.get("max_retries", 3),
            block_on=d.get("block_on", ["P0"]),
        )

    def to_dict(self) -> dict:
        return {
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "block_on": self.block_on,
        }


@dataclass
class EdgeCondition:
    """Condition for ``on_condition`` trigger edges."""
    status: str  # REVIEW_PASSED | REVIEW_FAILED | REVIEW_ERROR

    @classmethod
    def from_dict(cls, d: dict) -> "EdgeCondition":
        if not isinstance(d, dict):
            raise ValueError(f"condition must be a dict, got {type(d).__name__}")
        if "status" not in d:
            raise ValueError("condition.status is required")
        return cls(status=d["status"])

    def to_dict(self) -> dict:
        return {"status": self.status}


@dataclass
class EdgeConfig:
    """A single DAG edge. Maps to an item in pipeline.yaml ``edges`` list."""
    from_node: str      # YAML key "from" — renamed because "from" is a Python keyword
    to: str
    trigger: TriggerType
    condition: Optional[EdgeCondition] = None
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "EdgeConfig":
        if not isinstance(d, dict):
            raise ValueError(f"edge must be a dict, got {type(d).__name__}")
        for req in ("from", "to", "trigger"):
            if req not in d:
                raise ValueError(f"edge.{req} is required")
        condition = None
        if "condition" in d and d["condition"] is not None:
            condition = EdgeCondition.from_dict(d["condition"])
        return cls(
            from_node=d["from"],
            to=d["to"],
            trigger=TriggerType(d["trigger"]),
            condition=condition,
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {
            "from": self.from_node,
            "to": self.to,
            "trigger": self.trigger.value,
        }
        if self.condition is not None:
            d["condition"] = self.condition.to_dict()
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class NodeConfig:
    """A single DAG node. Maps to an item in pipeline.yaml ``nodes`` list."""
    id: str
    type: str              # "agent"
    agent: str
    description: str
    prompt_template: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    timeout: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "NodeConfig":
        if not isinstance(d, dict):
            raise ValueError(f"node must be a dict, got {type(d).__name__}")
        for req in ("id", "type", "agent", "description", "prompt_template"):
            if req not in d:
                raise ValueError(f"node.{req} is required")
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
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "agent": self.agent,
            "description": self.description,
            "prompt_template": self.prompt_template,
        }
        if self.inputs:
            d["inputs"] = self.inputs
        if self.outputs:
            d["outputs"] = self.outputs
        if self.timeout is not None:
            d["timeout"] = self.timeout
        if self.depends_on:
            d["depends_on"] = self.depends_on
        return d


@dataclass
class PipelineConfig:
    """Root configuration entity. Maps to the entire pipeline.yaml file."""
    name: str
    version: str
    description: str
    defaults: PipelineDefaults
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        if not isinstance(d, dict):
            raise ValueError(f"pipeline config must be a dict, got {type(d).__name__}")
        for req in ("name", "version", "description"):
            if req not in d:
                raise ValueError(f"pipeline.{req} is required")
        if "nodes" not in d or not isinstance(d["nodes"], list):
            raise ValueError("pipeline.nodes is required and must be a list")
        if "edges" not in d or not isinstance(d["edges"], list):
            raise ValueError("pipeline.edges is required and must be a list")
        defaults = PipelineDefaults.from_dict(d.get("defaults", {}))
        nodes = [NodeConfig.from_dict(n) for n in d["nodes"]]
        edges = [EdgeConfig.from_dict(e) for e in d["edges"]]
        return cls(
            name=d["name"],
            version=d["version"],
            description=d["description"],
            defaults=defaults,
            nodes=nodes,
            edges=edges,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "defaults": self.defaults.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def get_node(self, node_id: str) -> NodeConfig:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise ValueError(f"Node '{node_id}' not found in pipeline '{self.name}'")

    def get_outgoing_edges(self, node_id: str) -> list[EdgeConfig]:
        return [e for e in self.edges if e.from_node == node_id]

    def get_start_nodes(self) -> list[NodeConfig]:
        """Nodes with zero incoming edges (in-degree = 0)."""
        has_incoming = {e.to for e in self.edges if e.to != "DONE"}
        return [n for n in self.nodes if n.id not in has_incoming]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: all tests pass (4 enum + 11 config entity = 15 passed)

---

### Task 4: models.py — 运行时实体（PipelineState / NextAction 等）

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py`
- Modify: `agents/scheduler/tests/test_models.py`

- [ ] **Step 1: 写运行时实体测试**

```python
# 追加到 tests/test_models.py

class TestNodeResult:
    def test_from_dict(self):
        d = {"node_id": "coder", "status": "success", "summary": "ok",
             "agent_verdict": "", "outputs": {}, "timestamp": "2026-01-01T00:00:00Z"}
        obj = NodeResult.from_dict(d)
        assert obj.node_id == "coder"
        assert obj.status == NodeStatus.SUCCESS
        assert obj.agent_verdict == ""

    def test_to_dict(self):
        obj = NodeResult(node_id="reviewer", status=NodeStatus.SUCCESS,
                         summary="ok", agent_verdict="REVIEW_PASSED")
        d = obj.to_dict()
        assert d["node_id"] == "reviewer"
        assert d["agent_verdict"] == "REVIEW_PASSED"

    def test_defaults(self):
        obj = NodeResult(node_id="x", status=NodeStatus.SKIPPED)
        assert obj.summary == ""
        assert obj.agent_verdict == ""
        assert obj.timestamp != ""


class TestPipelineState:
    def test_from_dict_empty(self):
        d = {"pipeline_name": "test", "status": "pending"}
        obj = PipelineState.from_dict(d)
        assert obj.pipeline_name == "test"
        assert obj.status == PipelineStatus.PENDING
        assert obj.round == 0
        assert obj.current_nodes == []

    def test_from_dict_full(self):
        d = {
            "pipeline_name": "test", "status": "running", "round": 2,
            "current_nodes": ["reviewer"],
            "node_results": {
                "coder": {"node_id": "coder", "status": "success", "summary": "ok",
                          "agent_verdict": "", "outputs": {}, "timestamp": ""}
            },
            "history": [],
            "requirement": "build login",
            "started_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:01:00Z",
        }
        obj = PipelineState.from_dict(d)
        assert obj.round == 2
        assert obj.current_nodes == ["reviewer"]
        assert "coder" in obj.node_results
        assert obj.node_results["coder"].status == NodeStatus.SUCCESS

    def test_to_dict_roundtrip(self):
        obj = PipelineState(pipeline_name="test")
        obj.requirement = "build something"
        obj.start()
        d = obj.to_dict()
        assert d["pipeline_name"] == "test"
        assert d["status"] == "running"

    def test_start_sets_running(self):
        obj = PipelineState(pipeline_name="test")
        obj.start()
        assert obj.status == PipelineStatus.RUNNING
        assert obj.started_at != ""

    def test_complete(self):
        obj = PipelineState(pipeline_name="test")
        obj.complete()
        assert obj.status == PipelineStatus.COMPLETED

    def test_error(self):
        obj = PipelineState(pipeline_name="test")
        obj.error()
        assert obj.status == PipelineStatus.ERROR


class TestNodeToExecute:
    def test_to_dict(self):
        obj = NodeToExecute(node_id="coder", agent_type="coder",
                            prompt="Generate code", timeout="900s",
                            round=1, phase="fix")
        d = obj.to_dict()
        assert d["node_id"] == "coder"
        assert d["prompt"] == "Generate code"
        assert d["phase"] == "fix"


class TestNextAction:
    def test_to_dict_execute(self):
        node = NodeToExecute(node_id="coder", agent_type="coder",
                             prompt="Generate", timeout="900s", round=0,
                             phase="code_generation")
        obj = NextAction(action=ActionType.EXECUTE, nodes=[node],
                         message="Execute coder")
        d = obj.to_dict()
        assert d["action"] == "execute"
        assert len(d["nodes"]) == 1
        assert d["nodes"][0]["node_id"] == "coder"

    def test_to_dict_done(self):
        obj = NextAction(action=ActionType.DONE, message="Completed")
        d = obj.to_dict()
        assert d["action"] == "done"
        assert d["nodes"] == []

    def test_to_json(self):
        obj = NextAction(action=ActionType.DONE, message="Done!")
        j = obj.to_json()
        assert '"action": "done"' in j
        assert '"message": "Done!"' in j
```

更新文件顶部 import：
```python
from pipeline_engine.models import (
    TriggerType, NodeStatus, PipelineStatus, ActionType,
    PipelineDefaults, EdgeCondition, EdgeConfig, NodeConfig, PipelineConfig,
    NodeResult, PipelineState, NodeToExecute, NextAction,
)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v -k "TestNodeResult or TestPipelineState or TestNodeToExecute or TestNextAction"
```
Expected: FAIL — classes not defined

- [ ] **Step 3: 写运行时实体**

在 `models.py` 末尾追加：

```python
# ── Runtime State Entities ─────────────────────────────────────────


@dataclass
class NodeResult:
    """Record of a single node execution."""
    node_id: str
    status: NodeStatus
    summary: str = ""
    agent_verdict: str = ""    # REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR / ""
    outputs: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_dict(cls, d: dict) -> "NodeResult":
        return cls(
            node_id=d["node_id"],
            status=NodeStatus(d["status"]),
            summary=d.get("summary", ""),
            agent_verdict=d.get("agent_verdict", ""),
            outputs=d.get("outputs", {}),
            timestamp=d.get("timestamp", ""),
        )

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "summary": self.summary,
            "agent_verdict": self.agent_verdict,
            "outputs": self.outputs,
            "timestamp": self.timestamp,
        }


@dataclass
class PipelineState:
    """Persistent runtime state stored in pipeline-state.json."""
    pipeline_name: str
    status: PipelineStatus = PipelineStatus.PENDING
    round: int = 0
    current_nodes: list[str] = field(default_factory=list)
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    requirement: str = ""
    started_at: str = ""
    updated_at: str = ""

    def _touch(self):
        self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def start(self):
        self.status = PipelineStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._touch()

    def complete(self):
        self.status = PipelineStatus.COMPLETED
        self.current_nodes = []
        self._touch()

    def error(self):
        self.status = PipelineStatus.ERROR
        self.current_nodes = []
        self._touch()

    def set_current_nodes(self, node_ids: list[str]):
        self.current_nodes = node_ids
        self._touch()

    def record_result(self, result: NodeResult):
        self.node_results[result.node_id] = result
        self.history.append({
            "round": self.round,
            "node": result.node_id,
            "status": result.status.value,
            "verdict": result.agent_verdict,
            "summary": result.summary,
            "timestamp": result.timestamp,
        })
        self._touch()

    def clear_current_nodes(self):
        self.current_nodes = []
        self._touch()

    def increment_round(self):
        self.round += 1
        self._touch()

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineState":
        node_results = {}
        for k, v in d.get("node_results", {}).items():
            node_results[k] = NodeResult.from_dict(v)
        return cls(
            pipeline_name=d.get("pipeline_name", ""),
            status=PipelineStatus(d.get("status", "pending")),
            round=d.get("round", 0),
            current_nodes=d.get("current_nodes", []),
            node_results=node_results,
            history=d.get("history", []),
            requirement=d.get("requirement", ""),
            started_at=d.get("started_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def to_dict(self) -> dict:
        return {
            "pipeline_name": self.pipeline_name,
            "status": self.status.value,
            "round": self.round,
            "current_nodes": self.current_nodes,
            "node_results": {k: v.to_dict() for k, v in self.node_results.items()},
            "history": self.history,
            "requirement": self.requirement,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


# ── CLI Response Entities ──────────────────────────────────────────


@dataclass
class NodeToExecute:
    """A single node returned by the `next` command for execution."""
    node_id: str
    agent_type: str
    prompt: str          # fully rendered prompt
    timeout: str
    round: int
    phase: str           # "code_generation" | "review" | "fix"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "agent_type": self.agent_type,
            "prompt": self.prompt,
            "timeout": self.timeout,
            "round": self.round,
            "phase": self.phase,
        }


@dataclass
class NextAction:
    """Return value of the `next` command."""
    action: ActionType
    nodes: list[NodeToExecute] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "nodes": [n.to_dict() for n in self.nodes],
            "message": self.message,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v
```
Expected: all tests pass (4 + 11 + 9 = 24 passed)

---

### Task 5: config.py — YAML 加载与严格校验

**Files:**
- Create: `agents/scheduler/pipeline_engine/config.py`
- Test: `agents/scheduler/tests/test_config.py`

- [ ] **Step 1: 写配置测试**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from pipeline_engine.config import load_pipeline, ConfigLoadError
from pipeline_engine.models import PipelineConfig, TriggerType


class TestLoadPipeline:
    def test_load_valid_pipeline(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        assert isinstance(config, PipelineConfig)
        assert config.name == "test-pipeline"
        assert len(config.nodes) == 2
        assert len(config.edges) == 5

    def test_load_defaults(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        assert config.defaults.timeout == "600s"
        assert config.defaults.max_retries == 3

    def test_load_nodes(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        coder = config.get_node("coder")
        assert coder.agent == "coder"
        assert "Generate code for:" in coder.prompt_template
        assert coder.timeout == "900s"

    def test_load_edges(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        edges = config.get_outgoing_edges("reviewer")
        assert len(edges) == 4
        on_cond_edges = [e for e in edges if e.trigger == TriggerType.ON_CONDITION]
        assert len(on_cond_edges) == 4

    def test_file_not_found(self):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_pipeline(Path("/nonexistent/pipeline.yaml"))

    def test_not_yaml(self, tmp_path: Path):
        p = tmp_path / "bad.yaml"
        p.write_text("not: valid: yaml: [")
        with pytest.raises(ConfigLoadError, match="YAML"):
            load_pipeline(p)

    def test_missing_name(self, tmp_path: Path):
        p = tmp_path / "no_name.yaml"
        p.write_text("version: '1.0'\ndescription: test\nnodes: []\nedges: []")
        with pytest.raises(ConfigLoadError, match="name"):
            load_pipeline(p)

    def test_edge_references_missing_node(self, tmp_path: Path):
        p = tmp_path / "bad_edge.yaml"
        p.write_text("""
name: test
version: "1.0"
description: test
defaults: {}
nodes:
  - id: coder
    type: agent
    agent: coder
    description: "d"
    prompt_template: "p"
edges:
  - from: nonexistent
    to: coder
    trigger: on_success
    description: ""
""")
        with pytest.raises(ConfigLoadError, match="Edge references unknown node"):
            load_pipeline(p)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_config.py -v
```
Expected: FAIL — `pipeline_engine.config` module not found

- [ ] **Step 3: 写 config.py**

```python
"""Configuration loader — reads pipeline.yaml into typed PipelineConfig with strict validation.

Follows the Spring Boot @ConfigurationProperties pattern:
1. Load YAML with PyYAML
2. Deserialize into typed dataclass tree via from_dict()
3. Run semantic validations (edge references, DAG integrity, etc.)
4. Return immutable PipelineConfig or raise ConfigLoadError with precise message
"""

from pathlib import Path
from pipeline_engine.models import PipelineConfig

try:
    import yaml
except ImportError:
    yaml = None


class ConfigLoadError(Exception):
    """Raised when a pipeline.yaml cannot be loaded or fails validation."""
    pass


def load_pipeline(pipeline_path: Path) -> PipelineConfig:
    """Load and strictly validate a pipeline.yaml file.

    Args:
        pipeline_path: Path to the pipeline YAML file.

    Returns:
        A fully validated PipelineConfig instance.

    Raises:
        ConfigLoadError: If the file is missing, invalid YAML, missing required
                         fields, or contains semantic errors (e.g. edge references
                         to non-existent nodes).
    """
    if yaml is None:
        raise ConfigLoadError(
            "PyYAML is required. Install with: pip3 install pyyaml"
        )

    if not pipeline_path.exists():
        raise ConfigLoadError(f"Pipeline file not found: {pipeline_path}")

    # ── Phase 1: Parse YAML ────────────────────────────────────────
    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"Failed to parse YAML in {pipeline_path}: {e}")

    if data is None:
        raise ConfigLoadError(f"Pipeline file is empty: {pipeline_path}")

    if not isinstance(data, dict):
        raise ConfigLoadError(f"Pipeline YAML must be a mapping, got {type(data).__name__}")

    # ── Phase 2: Deserialize to typed tree ─────────────────────────
    try:
        config = PipelineConfig.from_dict(data)
    except (ValueError, KeyError) as e:
        raise ConfigLoadError(f"Invalid pipeline config in {pipeline_path}: {e}")

    # ── Phase 3: Semantic validation ───────────────────────────────
    _validate_edges(config, pipeline_path)
    _validate_start_nodes(config, pipeline_path)

    return config


def _validate_edges(config: PipelineConfig, path: Path) -> None:
    """Ensure all edge 'from' and 'to' (non-DONE) nodes exist."""
    node_ids = {n.id for n in config.nodes}
    for edge in config.edges:
        if edge.from_node not in node_ids:
            raise ConfigLoadError(
                f"Edge references unknown node '{edge.from_node}' in 'from' field. "
                f"Available nodes: {sorted(node_ids)}"
            )
        if edge.to != "DONE" and edge.to not in node_ids:
            raise ConfigLoadError(
                f"Edge references unknown node '{edge.to}' in 'to' field. "
                f"Available nodes: {sorted(node_ids)}"
            )


def _validate_start_nodes(config: PipelineConfig, path: Path) -> None:
    """Ensure there is at least one start node (in-degree = 0)."""
    start_nodes = config.get_start_nodes()
    if not start_nodes:
        raise ConfigLoadError(
            "No start nodes found. At least one node must have no incoming edges."
        )
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_config.py -v
```
Expected: all 7 passed

---

### Task 6: engine.py — DAG 状态机核心

**Files:**
- Create: `agents/scheduler/pipeline_engine/engine.py`
- Test: `agents/scheduler/tests/test_engine.py`

- [ ] **Step 1: 写 engine 测试（含线性流水线和修复循环场景）**

```python
# tests/test_engine.py
import json
import pytest
from pathlib import Path
from pipeline_engine.config import load_pipeline
from pipeline_engine.engine import PipelineEngine
from pipeline_engine.models import (
    PipelineStatus, NodeStatus, ActionType, NextAction,
)


class TestPipelineEngineStart:
    def test_start_creates_state_file(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        state = engine.start("build login feature")
        assert state.status == PipelineStatus.RUNNING
        assert state.requirement == "build login feature"
        assert state_path.exists()

    def test_start_when_already_running_asks_continue(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("first")
        with pytest.raises(RuntimeError, match="already running"):
            engine.start("second")


class TestPipelineEngineNext:
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

    def test_next_when_nodes_in_progress_returns_error(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # returns coder, sets current_nodes
        # current_nodes still has "coder" (not reported yet)
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "in progress" in action.message.lower()

    def test_after_coder_success_next_returns_reviewer(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "5 files generated")
        action = engine.next()
        assert action.action == ActionType.EXECUTE
        assert action.nodes[0].node_id == "reviewer"
        assert action.nodes[0].phase == "review"

    def test_reviewer_passed_leads_to_done(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        engine.next()  # reviewer
        engine.report("reviewer", NodeStatus.SUCCESS, "all good", agent_verdict="REVIEW_PASSED")
        action = engine.next()
        assert action.action == ActionType.DONE
        assert "completed" in action.message.lower()

    def test_reviewer_failed_triggers_fix_loop(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        # Round 0: coder → reviewer FAILED
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        engine.next()  # reviewer
        engine.report("reviewer", NodeStatus.SUCCESS, "3 P0 issues", agent_verdict="REVIEW_FAILED")
        action = engine.next()
        # Should go back to coder for fix (round 1)
        assert action.action == ActionType.EXECUTE
        assert action.nodes[0].node_id == "coder"
        assert action.nodes[0].round == 1
        assert action.nodes[0].phase == "fix"
        assert "review_context" in action.nodes[0].prompt.lower() or "review-output" in action.nodes[0].prompt

    def test_max_retries_exhausted(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        # Simulate 3 rounds of failure
        for round_num in range(3):
            engine.next()  # coder
            engine.report("coder", NodeStatus.SUCCESS, f"fix round {round_num}")
            engine.next()  # reviewer
            engine.report("reviewer", NodeStatus.SUCCESS, "still failing", agent_verdict="REVIEW_FAILED")
        # After 3rd FAILED, should be DONE (max_retries exhausted)
        action = engine.next()
        assert action.action == ActionType.DONE
        assert "max" in action.message.lower() or "retries" in action.message.lower()

    def test_reviewer_error_terminates(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        engine.next()  # reviewer
        engine.report("reviewer", NodeStatus.ERROR, "python3 not available", agent_verdict="REVIEW_ERROR")
        action = engine.next()
        assert action.action == ActionType.DONE
        assert "error" in action.message.lower()


class TestPipelineEngineReport:
    def test_report_with_verdict(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        state = engine.report("coder", NodeStatus.SUCCESS, "ok")
        assert "coder" in state.node_results
        assert state.node_results["coder"].status == NodeStatus.SUCCESS

    def test_report_unknown_node(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        with pytest.raises(ValueError, match="not in current_nodes"):
            engine.report("reviewer", NodeStatus.SUCCESS, "?")


class TestPipelineEngineStatus:
    def test_status_returns_state(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        state = engine.status()
        assert state.pipeline_name == "test-pipeline"
        assert state.status == PipelineStatus.RUNNING


class TestPipelineEngineReset:
    def test_reset_removes_state(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        assert state_path.exists()
        engine.reset()
        assert not state_path.exists()

    def test_reset_when_no_state(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.reset()  # should not raise
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_engine.py -v
```
Expected: FAIL — `pipeline_engine.engine` module not found

- [ ] **Step 3: 写 engine.py**

```python
"""DAG state machine — the core of the pipeline scheduler.

PipelineEngine manages the lifecycle of a pipeline execution:
  start  → initialize state from PipelineConfig
  next   → evaluate DAG edges, determine next node(s) to execute
  report → record node execution result, update state
  status → return current state summary
  reset  → clear state file

Key design: the engine does NOT execute agents. It only makes routing
decisions. Claude Code Agent handles actual agent execution via the Agent tool.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from pipeline_engine.models import (
    PipelineConfig, PipelineState, NodeResult, NextAction, NodeToExecute,
    PipelineStatus, NodeStatus, ActionType, TriggerType,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PipelineEngine:
    """DAG state machine that routes pipeline execution.

    Args:
        config: Fully validated PipelineConfig from config.load_pipeline().
        state_path: Path to the persistent state JSON file.
    """

    def __init__(self, config: PipelineConfig, state_path: Path):
        self.config = config
        self.state_path = Path(state_path)
        self.state: PipelineState | None = None

    # ── Public API ──────────────────────────────────────────────────

    def start(self, requirement: str) -> PipelineState:
        """Initialize the pipeline and persist state.

        Raises:
            RuntimeError: If a pipeline is already running (state file exists
                          with status running/pending).
        """
        if self.state_path.exists():
            existing = self._load_state()
            if existing.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
                raise RuntimeError(
                    f"Pipeline '{existing.pipeline_name}' is already running "
                    f"(status: {existing.status.value}). Use 'reset' to clear, "
                    f"or call 'next' to continue."
                )
        self.state = PipelineState(pipeline_name=self.config.name)
        self.state.requirement = requirement
        self.state.start()
        self._save_state()
        return self.state

    def next(self) -> NextAction:
        """Determine the next node(s) to execute based on DAG state.

        Returns:
            NextAction with action=EXECUTE and rendered nodes, or
            action=DONE if pipeline is complete, or action=ERROR.
        """
        self._ensure_state()
        state = self.state

        # ── Already completed or errored ──
        if state.status == PipelineStatus.COMPLETED:
            return NextAction(action=ActionType.DONE,
                              message="Pipeline already completed.")
        if state.status == PipelineStatus.ERROR:
            return NextAction(action=ActionType.ERROR,
                              message="Pipeline is in error state. Use 'reset' to restart.")

        # ── PENDING → find start nodes ──
        if state.status == PipelineStatus.PENDING:
            start_nodes = self.config.get_start_nodes()
            state.set_current_nodes([n.id for n in start_nodes])
            state.status = PipelineStatus.RUNNING
            self._save_state()
            rendered = self._render_nodes(start_nodes)
            return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                              message=f"Starting pipeline with {len(rendered)} node(s)")

        # ── RUNNING: check if current nodes are still in progress ──
        pending = [nid for nid in state.current_nodes
                   if nid not in state.node_results]
        if pending:
            return NextAction(
                action=ActionType.ERROR,
                message=f"Cannot advance: nodes still in progress: {pending}. "
                        f"Report results for these nodes first."
            )

        # ── Evaluate edges from completed current nodes ──
        next_node_configs = []
        for nid in state.current_nodes:
            result = state.node_results[nid]
            next_node_configs.extend(self._evaluate_edges(nid, result))

        state.clear_current_nodes()

        # ── No more nodes → DONE ──
        if not next_node_configs:
            state.complete()
            self._save_state()
            return NextAction(action=ActionType.DONE,
                              message=f"Pipeline completed successfully after {state.round + 1} round(s).")

        # ── Check for fix loop (coder re-entry) → increment round ──
        node_ids = [n.id for n in next_node_configs]
        # If we're going back to a node that already has results, it's a fix round
        already_executed = [nid for nid in node_ids if nid in state.node_results]
        if already_executed:
            # Check if we hit max_retries
            if state.round >= self.config.defaults.max_retries:
                state.complete()
                self._save_state()
                return NextAction(
                    action=ActionType.DONE,
                    message=f"Max retries ({self.config.defaults.max_retries}) exhausted. "
                            f"Pipeline stopped after {state.round} round(s)."
                )
            state.increment_round()

        state.set_current_nodes(node_ids)
        self._save_state()
        rendered = self._render_nodes(next_node_configs)
        return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                          message=f"Execute {len(rendered)} node(s)")

    def report(self, node_id: str, status: NodeStatus, summary: str = "",
               agent_verdict: str = "") -> PipelineState:
        """Record the result of a node execution.

        Args:
            node_id: The node that completed.
            status: Execution status (success/failed/error/skipped).
            summary: Human-readable summary of what happened.
            agent_verdict: The agent's verdict (REVIEW_PASSED/REVIEW_FAILED/
                           REVIEW_ERROR), empty string for non-reviewer nodes.

        Raises:
            ValueError: If node_id is not in current_nodes.
        """
        self._ensure_state()
        if node_id not in self.state.current_nodes:
            raise ValueError(
                f"Node '{node_id}' is not in current_nodes {self.state.current_nodes}. "
                f"Did you already report it?"
            )
        result = NodeResult(
            node_id=node_id,
            status=status,
            summary=summary,
            agent_verdict=agent_verdict,
        )
        self.state.record_result(result)
        self._save_state()
        return self.state

    def status(self) -> PipelineState:
        """Return the current pipeline state."""
        self._ensure_state()
        return self.state

    def reset(self) -> None:
        """Delete the state file and reset in-memory state."""
        self.state = None
        if self.state_path.exists():
            self.state_path.unlink()

    # ── Internal helpers ────────────────────────────────────────────

    def _ensure_state(self):
        if self.state is None:
            if self.state_path.exists():
                self.state = self._load_state()
            else:
                raise RuntimeError(
                    "No pipeline state found. Call 'start' first, "
                    "or ensure a state file exists."
                )

    def _load_state(self) -> PipelineState:
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineState.from_dict(data)

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)

    def _evaluate_edges(self, node_id: str, result: NodeResult) -> list:
        """Evaluate outgoing edges from a completed node.

        Returns list of NodeConfig for the next step(s).
        Handles fix-loop round check internally.
        """
        edges = self.config.get_outgoing_edges(node_id)
        next_nodes = []

        for edge in edges:
            if edge.to == "DONE":
                # DONE edges are terminal — they don't produce a next node.
                # But they're only checked when there are no other matches.
                continue

            if edge.trigger == TriggerType.ON_SUCCESS:
                if result.status == NodeStatus.SUCCESS:
                    next_nodes.append(self.config.get_node(edge.to))

            elif edge.trigger == TriggerType.ON_CONDITION:
                if edge.condition is None:
                    continue
                if self._check_condition(edge.condition.status, result):
                    next_nodes.append(self.config.get_node(edge.to))

        # If no next nodes found but there are DONE edges, that's fine —
        # the caller will see empty list and transition to COMPLETED.
        return next_nodes

    def _check_condition(self, condition_status: str, result: NodeResult) -> bool:
        """Check if a condition edge matches the node result."""
        if condition_status == "REVIEW_PASSED":
            return result.agent_verdict == "REVIEW_PASSED"
        if condition_status == "REVIEW_FAILED":
            return (result.agent_verdict == "REVIEW_FAILED"
                    and self.state.round < self.config.defaults.max_retries)
        if condition_status == "REVIEW_ERROR":
            return result.agent_verdict == "REVIEW_ERROR"
        return False

    def _render_nodes(self, node_configs: list) -> list[NodeToExecute]:
        """Render prompt templates for each node into executable form.

        Substitutes {requirement}, {review_context}, {round}, {max_retries}
        into each node's prompt_template.
        """
        rendered = []
        for node in node_configs:
            prompt = self._render_prompt(node)
            phase = self._determine_phase(node)
            timeout = node.timeout or self.config.defaults.timeout
            rendered.append(NodeToExecute(
                node_id=node.id,
                agent_type=node.agent,
                prompt=prompt,
                timeout=timeout,
                round=self.state.round,
                phase=phase,
            ))
        return rendered

    def _render_prompt(self, node: NodeConfig) -> str:
        """Render a single node's prompt_template with current state variables."""
        review_context = ""
        if self.state.round > 0:
            review_context = (
                "\n\n⚠️ 这是第 {round}/{max_retries} 轮修复。\n\n"
                "请先读取以下文件，了解上一轮审查发现的问题：\n"
                "1. review-output/pre-check-result.json — 程序预检结果\n"
                "2. review-output/review-result.json — AI 语义检查结果（如存在）\n"
                "3. review-output/pre-check-report.md — 预检报告\n\n"
                "然后逐个修复所有阻断级问题。\n\n"
                "修复原则：\n"
                "- 只修改有问题的文件和行\n"
                "- 修复后必须符合 agents/coder/ 下的所有规范\n"
                "- 不确定的改动，加注释说明原因"
            ).format(round=self.state.round,
                     max_retries=self.config.defaults.max_retries)

        variables = {
            "requirement": self.state.requirement,
            "review_context": review_context,
            "round": str(self.state.round),
            "max_retries": str(self.config.defaults.max_retries),
        }

        try:
            return node.prompt_template.format(**variables)
        except KeyError as e:
            # If the template references a variable we don't have, leave it as-is
            # but log a warning
            import sys
            print(f"Warning: unknown variable {e} in prompt_template for node '{node.id}'",
                  file=sys.stderr)
            return node.prompt_template

    def _determine_phase(self, node: NodeConfig) -> str:
        """Determine the execution phase label for a node."""
        if node.id == "coder":
            if self.state.round > 0:
                return "fix"
            return "code_generation"
        if node.id == "reviewer":
            return "review"
        return node.id
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_engine.py -v
```
Expected: all tests pass

---

### Task 7: cli.py — CLI 入口

**Files:**
- Create: `agents/scheduler/pipeline_engine/cli.py`
- Test: `agents/scheduler/tests/test_cli.py`

- [ ] **Step 1: 写 CLI 集成测试**

```python
# tests/test_cli.py
import json
import subprocess
import sys
from pathlib import Path

CLI_ENTRY = [sys.executable, "-m", "pipeline_engine.cli"]


def run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI_ENTRY + args,
        capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
    )


class TestCLIStart:
    def test_start_ok(self, tmp_path: Path):
        # Create a minimal pipeline in tmp_path
        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("""
name: cli-test
version: "1.0"
description: CLI test
defaults:
  timeout: 300s
  max_retries: 2
  block_on: [P0]
nodes:
  - id: coder
    type: agent
    agent: coder
    description: Generate code
    prompt_template: "Generate: {requirement}"
    timeout: 500s
  - id: reviewer
    type: agent
    agent: reviewer
    description: Review
    prompt_template: "Review."
    timeout: 300s
edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: go
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: done
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: done
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: done
""")
        state_file = tmp_path / "pipeline-state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test feature",
        ], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "started"
        assert state_file.exists()

    def test_start_no_pipeline(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(tmp_path / "nonexistent.yaml"),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode != 0


class TestCLINext:
    def test_next_returns_coder(self, tmp_path: Path):
        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("""
name: t
version: "1"
description: d
defaults: {timeout: 300s, max_retries: 2, block_on: [P0]}
nodes:
  - {id: coder, type: agent, agent: coder, description: d, prompt_template: "Generate: {requirement}", timeout: 500s}
  - {id: reviewer, type: agent, agent: reviewer, description: d, prompt_template: "Review.", timeout: 300s}
edges:
  - {from: coder, to: reviewer, trigger: on_success, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_PASSED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_FAILED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_ERROR}, description: ""}
""")
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        result = run_cli(["next", "--state-file", str(state_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["action"] == "execute"
        assert data["nodes"][0]["node_id"] == "coder"
        assert "test" in data["nodes"][0]["prompt"]


class TestCLIReport:
    def test_report_coder_success(self, tmp_path: Path):
        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("""
name: t
version: "1"
description: d
defaults: {timeout: 300s, max_retries: 2, block_on: [P0]}
nodes:
  - {id: coder, type: agent, agent: coder, description: d, prompt_template: "Generate: {requirement}", timeout: 500s}
  - {id: reviewer, type: agent, agent: reviewer, description: d, prompt_template: "Review.", timeout: 300s}
edges:
  - {from: coder, to: reviewer, trigger: on_success, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_PASSED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_FAILED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_ERROR}, description: ""}
""")
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        run_cli(["next", "--state-file", str(state_file)], cwd=tmp_path)
        result = run_cli([
            "report", "--state-file", str(state_file),
            "--node", "coder", "--status", "success",
            "--summary", "Generated 3 files",
        ], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["accepted"] is True


class TestCLIStatus:
    def test_status(self, tmp_path: Path):
        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("""
name: t
version: "1"
description: d
defaults: {timeout: 300s, max_retries: 2, block_on: [P0]}
nodes:
  - {id: coder, type: agent, agent: coder, description: d, prompt_template: "Generate: {requirement}", timeout: 500s}
  - {id: reviewer, type: agent, agent: reviewer, description: d, prompt_template: "Review.", timeout: 300s}
edges:
  - {from: coder, to: reviewer, trigger: on_success, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_PASSED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_FAILED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_ERROR}, description: ""}
""")
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        result = run_cli(["status", "--state-file", str(state_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "running"


class TestCLIReset:
    def test_reset(self, tmp_path: Path):
        pipeline_file = tmp_path / "pipeline.yaml"
        pipeline_file.write_text("""
name: t
version: "1"
description: d
defaults: {timeout: 300s, max_retries: 2, block_on: [P0]}
nodes:
  - {id: coder, type: agent, agent: coder, description: d, prompt_template: "Generate: {requirement}", timeout: 500s}
  - {id: reviewer, type: agent, agent: reviewer, description: d, prompt_template: "Review.", timeout: 300s}
edges:
  - {from: coder, to: reviewer, trigger: on_success, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_PASSED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_FAILED}, description: ""}
  - {from: reviewer, to: DONE, trigger: on_condition, condition: {status: REVIEW_ERROR}, description: ""}
""")
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        assert state_file.exists()
        result = run_cli(["reset", "--state-file", str(state_file)], cwd=tmp_path)
        assert result.returncode == 0
        assert not state_file.exists()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py -v
```
Expected: FAIL — CLI module not found

- [ ] **Step 3: 写 cli.py**

```python
#!/usr/bin/env python3
"""pipeline-engine CLI — DAG-based workflow scheduler entry point.

Commands:
  start   — Initialize pipeline state from pipeline.yaml
  next    — Get next node(s) to execute
  report  — Record node execution result
  status  — Show current pipeline state
  reset   — Clear pipeline state
"""

import argparse
import json
import sys
from pathlib import Path

from pipeline_engine.config import load_pipeline, ConfigLoadError
from pipeline_engine.engine import PipelineEngine
from pipeline_engine.models import NodeStatus


def cmd_start(args):
    """Initialize pipeline state."""
    pipeline_path = Path(args.pipeline)
    state_path = Path(args.state_file)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        state = engine.start(args.requirement)
    except RuntimeError as e:
        # Pipeline already running — return current state info
        existing = engine.status()
        print(json.dumps({
            "status": "already_running",
            "pipeline_name": existing.pipeline_name,
            "current_round": existing.round,
            "message": str(e),
        }))
        sys.exit(0)

    print(json.dumps({
        "status": "started",
        "pipeline_name": state.pipeline_name,
        "round": 0,
        "max_retries": config.defaults.max_retries,
        "message": f"Pipeline '{config.name}' started.",
    }))


def cmd_next(args):
    """Get next node(s) to execute."""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": "No pipeline state found. Run 'start' first.",
        }))
        sys.exit(0)

    # Load config from the pipeline name stored in state
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": f"Failed to read state file: {e}",
        }))
        sys.exit(2)

    pipeline_path = Path(args.pipeline) if args.pipeline else Path("pipeline.yaml")
    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": f"Failed to load pipeline config: {e}",
        }))
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        action = engine.next()
    except RuntimeError as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": str(e),
        }))
        sys.exit(0)

    print(action.to_json())


def cmd_report(args):
    """Record node execution result."""
    state_path = Path(args.state_file)
    pipeline_path = Path(args.pipeline) if args.pipeline else Path("pipeline.yaml")

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({"accepted": False, "error": str(e)}), file=sys.stderr)
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        status = NodeStatus(args.status)
        state = engine.report(
            node_id=args.node,
            status=status,
            summary=args.summary or "",
            agent_verdict=args.verdict or "",
        )
    except (ValueError, RuntimeError) as e:
        print(json.dumps({"accepted": False, "error": str(e)}))
        sys.exit(0)

    print(json.dumps({
        "accepted": True,
        "state": state.status.value,
        "round": state.round,
        "current_nodes": state.current_nodes,
    }))


def cmd_status(args):
    """Show current pipeline state."""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({"error": "No pipeline state found."}))
        sys.exit(0)

    with open(state_path, "r", encoding="utf-8") as f:
        state_data = json.load(f)

    print(json.dumps(state_data, ensure_ascii=False, indent=2))


def cmd_reset(args):
    """Clear pipeline state."""
    state_path = Path(args.state_file)

    if state_path.exists():
        state_path.unlink()
        print(json.dumps({"status": "reset", "message": "State cleared."}))
    else:
        print(json.dumps({"status": "reset", "message": "No state file to clear."}))


def main():
    parser = argparse.ArgumentParser(
        prog="pipeline-engine",
        description="DAG-based workflow scheduler for code generation pipelines",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── start ──────────────────────────────────────────────────────
    p_start = sub.add_parser("start", help="Initialize a new pipeline run")
    p_start.add_argument("--pipeline", required=True,
                         help="Path to pipeline.yaml")
    p_start.add_argument("--state-file", default="review-output/pipeline-state.json",
                         help="Path to state file (default: review-output/pipeline-state.json)")
    p_start.add_argument("--requirement", required=True,
                         help="User requirement description")

    # ── next ───────────────────────────────────────────────────────
    p_next = sub.add_parser("next", help="Get next node(s) to execute")
    p_next.add_argument("--pipeline", default="pipeline.yaml",
                        help="Path to pipeline.yaml (default: pipeline.yaml)")
    p_next.add_argument("--state-file", default="review-output/pipeline-state.json",
                        help="Path to state file")

    # ── report ─────────────────────────────────────────────────────
    p_report = sub.add_parser("report", help="Record node execution result")
    p_report.add_argument("--pipeline", default="pipeline.yaml",
                          help="Path to pipeline.yaml")
    p_report.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")
    p_report.add_argument("--node", required=True,
                          help="Node ID that completed")
    p_report.add_argument("--status", required=True,
                          choices=["success", "failed", "error", "skipped"],
                          help="Execution status")
    p_report.add_argument("--summary", default="",
                          help="Human-readable summary")
    p_report.add_argument("--verdict", default="",
                          help="Agent verdict (REVIEW_PASSED/REVIEW_FAILED/REVIEW_ERROR)")

    # ── status ─────────────────────────────────────────────────────
    p_status = sub.add_parser("status", help="Show current pipeline state")
    p_status.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")

    # ── reset ──────────────────────────────────────────────────────
    p_reset = sub.add_parser("reset", help="Clear pipeline state")
    p_reset.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(args)
    elif args.command == "next":
        cmd_next(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py -v
```
Expected: all 6 passed

---

### Task 8: pipeline.yaml 增强 — 添加 depends_on 字段

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 为每个节点添加 depends_on 字段**

在 `pipeline.yaml` 的 `coder` 节点中添加 `depends_on: []`，`reviewer` 节点中添加 `depends_on: [coder]`。

在 coder 节点的 `timeout: 900s` 之后，`inputs:` 之前添加：
```yaml
      depends_on: []          # 起始节点，无依赖
```

在 reviewer 节点的 `timeout: 600s` 之后，`inputs:` 之前添加：
```yaml
      depends_on: [coder]     # 依赖 coder 产出
```

- [ ] **Step 2: 验证 YAML 仍可正常加载**

```bash
cd agents/scheduler && python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '.')
from pipeline_engine.config import load_pipeline
config = load_pipeline(Path('pipeline.yaml'))
print(f'OK: {config.name} v{config.version}')
print(f'Nodes: {len(config.nodes)}, Edges: {len(config.edges)}')
print(f'Coder depends_on: {config.get_node(\"coder\").depends_on}')
print(f'Reviewer depends_on: {config.get_node(\"reviewer\").depends_on}')
print(f'Defaults max_retries: {config.defaults.max_retries}')
"
```
Expected: OK with all values printed

- [ ] **Step 3: 运行全部测试确认无回归**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```
Expected: all tests pass

---

### Task 9: build.skill.md 简化

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 检查当前 build.skill.md 内容**

当前文件已在上文读取，约 137 行。

- [ ] **Step 2: 替换为薄执行器版本**

```markdown
---
name: build
description: 自动化代码生成流水线 — coder 生成 → reviewer 审查 → 自动修复循环
---

# /build — 自动化代码生成流水线

用法：`/build <需求描述>`

通过 `pipeline_engine` CLI 解析 `pipeline.yaml` 中的 DAG 定义，步进执行。

---

## 执行流程

### Phase 0: 初始化

1. 检测 `review-output/pipeline-state.json` 是否存在：
   - 存在 → 调用 `python3 -m pipeline_engine.cli status --state-file review-output/pipeline-state.json`，询问用户「检测到未完成的流水线，是否续接？」
   - 续接 → 直接进入 Phase 1 循环
   - 重新开始 → `python3 -m pipeline_engine.cli reset --state-file review-output/pipeline-state.json`，然后继续初始化
2. 调用 `python3 -m pipeline_engine.cli start --pipeline agents/scheduler/pipeline.yaml --state-file review-output/pipeline-state.json --requirement "{用户需求}"`
3. 向用户报告启动信息

### Phase 1: 执行循环

```
loop:
  1. 调用:
     python3 -m pipeline_engine.cli next \
       --pipeline agents/scheduler/pipeline.yaml \
       --state-file review-output/pipeline-state.json

  2. 解析返回 JSON:
     ┌──────────────────────────────────────────────────────┐
     │ action=="done"  → 退出循环，展示完成信息               │
     │ action=="error" → 退出循环，展示错误信息               │
     │ action=="execute" → 对 nodes 中的每个节点:            │
     │   a. 通过 Agent 工具启动子 Agent（subagent_type 使用  │
     │      节点返回的 agent_type）                          │
     │   b. prompt 使用节点返回的已渲染 prompt               │
     │   c. 超时参考节点返回的 timeout 字段                   │
     │   d. 等待子 Agent 完成，提取其最终回复                 │
     │   e. 判断 verdict（如回复中含 REVIEW_PASSED /          │
     │      REVIEW_FAILED / REVIEW_ERROR）                   │
     │   f. python3 -m pipeline_engine.cli report \         │
     │        --pipeline agents/scheduler/pipeline.yaml \   │
     │        --state-file review-output/pipeline-state.json\│
     │        --node {node_id} \                            │
     │        --status {success|failed|error} \              │
     │        --summary "{简要描述}" \                       │
     │        --verdict {REVIEW_PASSED|REVIEW_FAILED|REVIEW_ERROR|空} │
     │   g. 如果有多个 node → 可以并行启动（Agent 工具并发）   │
     └──────────────────────────────────────────────────────┘
  3. 回到步骤 1
```

### 终止条件

- `next` 返回 `action=="done"` → 读取 `review-output/final-review-report.md` 展示结果
- `next` 返回 `action=="error"` → 展示错误信息，提示用户介入

---

## 错误处理速查

| 场景 | 动作 |
|------|------|
| `/build` 无参数 | 提示「请输入需求描述，如：/build 实现用户登录功能」 |
| 需求模糊 | 追问 1-2 个澄清问题 |
| 调度器命令失败 | 检查 python3 和 PyYAML 是否可用，展示 stderr |
| `next` 返回 error | 展示 message，询问是否 reset 重来 |
| 用户 Ctrl+C | 状态文件保留，下次运行可续接 |
| 子 Agent 超时 | report status=error，让调度器决定下一步 |
| 子 Agent 未生成文件 | report status=failed（非 error），进入修复循环 |
```

- [ ] **Step 3: 验证 Markdown 格式正确**

文件 frontmatter YAML 格式正确，代码块闭合。

---

### Task 10: 全量回归测试

**Files:**
- Modify: 无（仅运行测试）

- [ ] **Step 1: 运行全部测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```
Expected: all tests pass (models + config + engine + CLI ≈ 37 tests)

- [ ] **Step 2: 端到端手动验证**

```bash
cd agents/scheduler && python3 -m pipeline_engine.cli start \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json \
  --requirement "测试需求"

python3 -m pipeline_engine.cli next \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json

python3 -m pipeline_engine.cli report \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json \
  --node coder --status success --summary "测试生成完成"

python3 -m pipeline_engine.cli next \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json

python3 -m pipeline_engine.cli report \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json \
  --node reviewer --status success --verdict REVIEW_PASSED --summary "审查通过"

python3 -m pipeline_engine.cli next \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json

python3 -m pipeline_engine.cli reset \
  --state-file /tmp/test-pipeline-state.json
```
Expected: start→next(coder)→report→next(reviewer)→report→next(DONE)→reset — 全程无错误，JSON 输出正确

- [ ] **Step 3: 测试修复循环**

```bash
cd agents/scheduler && python3 -m pipeline_engine.cli start \
  --pipeline pipeline.yaml \
  --state-file /tmp/test-fix-loop-state.json \
  --requirement "测试修复循环"

# Round 0: coder → reviewer FAILED
python3 -m pipeline_engine.cli next --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json
python3 -m pipeline_engine.cli report --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json --node coder --status success --summary "round 0"
python3 -m pipeline_engine.cli next --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json
python3 -m pipeline_engine.cli report --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json --node reviewer --status success --verdict REVIEW_FAILED --summary "发现问题"

# Round 1: coder fix → reviewer PASSED
python3 -m pipeline_engine.cli next --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json
echo "Should be round 1 coder (fix phase)"
python3 -m pipeline_engine.cli report --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json --node coder --status success --summary "修复完成"
python3 -m pipeline_engine.cli next --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json
python3 -m pipeline_engine.cli report --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json --node reviewer --status success --verdict REVIEW_PASSED --summary "通过"

# Should be DONE
python3 -m pipeline_engine.cli next --pipeline pipeline.yaml --state-file /tmp/test-fix-loop-state.json

python3 -m pipeline_engine.cli reset --state-file /tmp/test-fix-loop-state.json
```
Expected: round 0 coder → reviewer FAILED → round 1 coder fix → reviewer PASSED → DONE

- [ ] **Step 4: Commit**

```bash
git add agents/scheduler/
git commit -m "feat: add pipeline_engine scheduler — DAG-driven pipeline execution

Replace hardcoded build.skill.md routing logic with a Python DAG state
machine that parses pipeline.yaml and provides step-by-step CLI commands
(start/next/report/status/reset) for Claude Code Agent to execute.

Key changes:
- pipeline_engine/models.py — Spring Boot-style typed config binding
- pipeline_engine/config.py — strict YAML loading with validation
- pipeline_engine/engine.py — DAG state machine with fix-loop support
- pipeline_engine/cli.py — argparse CLI entry point
- pipeline_engine/reporter.py — state visualization
- tests/ — 37 unit + integration tests
- pipeline.yaml — add depends_on field for explicit parallelism
- build.skill.md — simplified from 137 lines to ~60 lines

Fixes: architecture-review-2025-06-24.md §3.1 — pipeline.yaml was dead config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: reporter.py — 状态可视化

**Files:**
- Create: `agents/scheduler/pipeline_engine/reporter.py`

- [ ] **Step 1: 写 reporter.py**

```python
"""State visualization — human-readable pipeline status output.

Provides functions to format PipelineState into readable summaries
for terminal display and progress reporting.
"""

from pipeline_engine.models import PipelineState, PipelineStatus, NodeStatus


def format_status_line(state: PipelineState) -> str:
    """Return a single-line status summary.

    Example: "[◉ RUNNING] coder-reviewer-pipeline — Round 1/3 — current: reviewer"
    """
    icons = {
        PipelineStatus.PENDING: "○",
        PipelineStatus.RUNNING: "◉",
        PipelineStatus.COMPLETED: "●",
        PipelineStatus.ERROR: "✕",
    }
    icon = icons.get(state.status, "?")
    name = state.pipeline_name
    round_info = f"Round {state.round}"
    if state.status == PipelineStatus.RUNNING:
        max_r = state.node_results.get("_max_retries", 3) if "_max_retries" in state.node_results else "?"
        round_info = f"Round {state.round}"
    current = ", ".join(state.current_nodes) if state.current_nodes else "—"
    return f"[{icon} {state.status.value.upper()}] {name} — {round_info} — current: {current}"


def format_history_table(state: PipelineState) -> str:
    """Return a Markdown table of the execution history."""
    if not state.history:
        return "*No execution history yet.*"

    lines = [
        "| Round | Node | Status | Verdict | Summary |",
        "|-------|------|--------|---------|----------|",
    ]
    for entry in state.history:
        verdict = entry.get("verdict", "") or "—"
        summary = entry.get("summary", "") or "—"
        lines.append(
            f"| {entry['round']} | {entry['node']} | {entry['status']} "
            f"| {verdict} | {summary} |"
        )
    return "\n".join(lines)


def format_full_status(state: PipelineState) -> str:
    """Return a multi-line status block suitable for terminal display."""
    parts = [
        format_status_line(state),
        "",
        f"Started: {state.started_at or 'N/A'}",
        f"Updated: {state.updated_at or 'N/A'}",
        f"Requirement: {state.requirement or 'N/A'}",
        "",
        "## Execution History",
        format_history_table(state),
    ]
    return "\n".join(parts)
```

这个文件由 engine.py 和 cli.py 内部按需调用，不需要独立测试（通过 CLI 集成测试间接覆盖）。
