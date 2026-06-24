"""Data models for pipeline-engine — typed bindings for pipeline.yaml and runtime state.

All model classes follow the Spring Boot @ConfigurationProperties pattern:
YAML structure → strict dataclass tree → from_dict() factory with validation.
"""

# Imports required by the model classes in this module.
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
        """Nodes with zero incoming ``on_success`` edges (no forward dependency)."""
        # Only on_success edges count as forward dependencies; on_condition edges
        # are feedback loops (e.g. review FAILED -> coder) and should not block
        # a node from being considered a start node.
        has_incoming = {e.to for e in self.edges if e.trigger == TriggerType.ON_SUCCESS}
        return [n for n in self.nodes if n.id not in has_incoming]


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
        if not isinstance(d, dict):
            raise ValueError(f"node_result must be a dict, got {type(d).__name__}")
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
        if not isinstance(d, dict):
            raise ValueError(f"pipeline_state must be a dict, got {type(d).__name__}")
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
