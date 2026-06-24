"""Data models for pipeline-engine — typed bindings for pipeline.yaml and runtime state.

All model classes follow the Spring Boot @ConfigurationProperties pattern:
YAML structure → strict dataclass tree → from_dict() factory with validation.
"""

# NOTE: dataclass, field, datetime, timezone, Optional are forward-declared here
# for upcoming dataclass definitions in Tasks 3 and 4. Do not remove.
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
        has_incoming = {e.to for e in self.edges if e.trigger == TriggerType.ON_SUCCESS}
        return [n for n in self.nodes if n.id not in has_incoming]
