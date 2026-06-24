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
