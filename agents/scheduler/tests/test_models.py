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
