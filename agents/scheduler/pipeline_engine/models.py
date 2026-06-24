"""pipeline-engine 数据模型 — pipeline.yaml 的类型化绑定和运行时状态实体。

所有模型类遵循 Spring Boot @ConfigurationProperties 模式：
YAML 结构 → 严格 dataclass 树 → from_dict() 工厂方法带校验。
"""

# 本模块所需的导入。
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional


# ── 枚举 ────────────────────────────────────────────────────────────


class TriggerType(str, Enum):
    """边的触发类型。"""
    ON_SUCCESS = "on_success"
    ON_CONDITION = "on_condition"


class NodeStatus(str, Enum):
    """单个节点的执行状态。"""
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    """流水线整体生命周期状态。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ActionType(str, Enum):
    """`next` 命令返回的动作类型。"""
    EXECUTE = "execute"
    DONE = "done"
    ERROR = "error"


# ── 流水线配置实体 ──────────────────────────────────────────────────


@dataclass
class PipelineDefaults:
    """全局默认值，对应 pipeline.yaml 中的 ``defaults`` 节点。"""
    timeout: str = "600s"
    max_retries: int = 3
    block_on: list[str] = field(default_factory=lambda: ["P0"])

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineDefaults":
        if not isinstance(d, dict):
            raise ValueError(f"defaults 必须是 dict，实际类型为 {type(d).__name__}")
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
    """条件边的触发条件，用于 ``on_condition`` 触发器。"""
    status: str  # REVIEW_PASSED | REVIEW_FAILED | REVIEW_ERROR

    @classmethod
    def from_dict(cls, d: dict) -> "EdgeCondition":
        if not isinstance(d, dict):
            raise ValueError(f"condition 必须是 dict，实际类型为 {type(d).__name__}")
        if "status" not in d:
            raise ValueError("condition.status 为必填字段")
        return cls(status=d["status"])

    def to_dict(self) -> dict:
        return {"status": self.status}


@dataclass
class EdgeConfig:
    """单条 DAG 边，对应 pipeline.yaml ``edges`` 列表中的一项。"""
    from_node: str      # YAML 键为 "from"——因 Python 关键字冲突重命名为 from_node
    to: str
    trigger: TriggerType
    condition: Optional[EdgeCondition] = None
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "EdgeConfig":
        if not isinstance(d, dict):
            raise ValueError(f"edge 必须是 dict，实际类型为 {type(d).__name__}")
        for req in ("from", "to", "trigger"):
            if req not in d:
                raise ValueError(f"edge.{req} 为必填字段")
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

    @classmethod
    def from_dict(cls, d: dict) -> "NodeConfig":
        if not isinstance(d, dict):
            raise ValueError(f"node 必须是 dict，实际类型为 {type(d).__name__}")
        for req in ("id", "type", "agent", "description", "prompt_template"):
            if req not in d:
                raise ValueError(f"node.{req} 为必填字段")
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
    """根配置实体，对应整个 pipeline.yaml 文件。"""
    name: str
    version: str
    description: str
    defaults: PipelineDefaults
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        if not isinstance(d, dict):
            raise ValueError(f"pipeline 配置必须是 dict，实际类型为 {type(d).__name__}")
        for req in ("name", "version", "description"):
            if req not in d:
                raise ValueError(f"pipeline.{req} 为必填字段")
        if "nodes" not in d or not isinstance(d["nodes"], list):
            raise ValueError("pipeline.nodes 为必填字段且必须是 list")
        if "edges" not in d or not isinstance(d["edges"], list):
            raise ValueError("pipeline.edges 为必填字段且必须是 list")
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
        """按 ID 查找节点，找不到则抛出 ValueError。"""
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise ValueError(f"节点 '{node_id}' 在流水线 '{self.name}' 中不存在")

    def get_outgoing_edges(self, node_id: str) -> list[EdgeConfig]:
        """获取指定节点的所有出边。"""
        return [e for e in self.edges if e.from_node == node_id]

    def get_start_nodes(self) -> list[NodeConfig]:
        """获取入度为 0 的起始节点（仅 ``on_success`` 边计入前向依赖）。"""
        # 仅 on_success 边算作前向依赖；on_condition 边是反馈回路
        #（例如 reviewer FAILED → coder），不应阻止节点成为起始节点。
        has_incoming = {e.to for e in self.edges if e.trigger == TriggerType.ON_SUCCESS}
        return [n for n in self.nodes if n.id not in has_incoming]


# ── 运行时状态实体 ──────────────────────────────────────────────────


@dataclass
class NodeResult:
    """单个节点的执行结果记录。"""
    node_id: str
    status: NodeStatus
    summary: str = ""
    agent_verdict: str = ""    # REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR / ""
    outputs: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        """初始化后自动生成时间戳（如果未提供）。"""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_dict(cls, d: dict) -> "NodeResult":
        if not isinstance(d, dict):
            raise ValueError(f"node_result 必须是 dict，实际类型为 {type(d).__name__}")
        return cls(
            node_id=d.get("node_id", ""),
            status=NodeStatus(d.get("status", "skipped")),
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
    """持久化运行时状态，保存在 pipeline-state.json 中。"""
    pipeline_name: str
    status: PipelineStatus = PipelineStatus.PENDING
    round: int = 0
    current_nodes: list[str] = field(default_factory=list)
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    requirement: str = ""
    started_at: str = ""
    updated_at: str = ""
    run_id: str = ""
    target_dir: str = "."   # 新增：模块根目录，相对于项目根

    def _touch(self):
        """更新 updated_at 时间戳。"""
        self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def start(self):
        """将流水线标记为运行中，记录开始时间。"""
        self.status = PipelineStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.run_id:
            self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-000"
        self._touch()

    def complete(self):
        """将流水线标记为已完成。"""
        self.status = PipelineStatus.COMPLETED
        self.current_nodes = []
        self._touch()

    def error(self):
        """将流水线标记为错误状态。"""
        self.status = PipelineStatus.ERROR
        self.current_nodes = []
        self._touch()

    def set_current_nodes(self, node_ids: list[str]):
        """设置当前待执行的节点列表。"""
        self.current_nodes = node_ids
        self._touch()

    def record_result(self, result: NodeResult):
        """记录一个节点的执行结果，追加到历史记录。"""
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
        """清空当前待执行节点列表。"""
        self.current_nodes = []
        self._touch()

    def increment_round(self):
        """轮次 +1（用于修复循环）。"""
        self.round += 1
        self._touch()

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineState":
        if not isinstance(d, dict):
            raise ValueError(f"pipeline_state 必须是 dict，实际类型为 {type(d).__name__}")
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
            run_id=d.get("run_id", ""),
            target_dir=d.get("target_dir", "."),
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
            "run_id": self.run_id,
            "target_dir": self.target_dir,
        }


# ── CLI 响应实体 ────────────────────────────────────────────────────


@dataclass
class NodeToExecute:
    """`next` 命令返回的单个待执行节点。"""
    node_id: str
    agent_type: str
    prompt: str          # 已渲染完整的 prompt
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
    """`next` 命令的返回值。"""
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
