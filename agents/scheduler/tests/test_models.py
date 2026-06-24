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

    def test_count(self):
        assert len(TriggerType) == 2


class TestNodeStatus:
    def test_values(self):
        assert NodeStatus.SUCCESS == "success"
        assert NodeStatus.FAILED == "failed"
        assert NodeStatus.ERROR == "error"
        assert NodeStatus.SKIPPED == "skipped"

    def test_from_str(self):
        assert NodeStatus("success") == NodeStatus.SUCCESS
        assert NodeStatus("failed") == NodeStatus.FAILED
        assert NodeStatus("error") == NodeStatus.ERROR
        assert NodeStatus("skipped") == NodeStatus.SKIPPED

    def test_invalid_status(self):
        with pytest.raises(ValueError):
            NodeStatus("unknown_status")

    def test_count(self):
        assert len(NodeStatus) == 4


class TestPipelineStatus:
    def test_values(self):
        assert PipelineStatus.PENDING == "pending"
        assert PipelineStatus.RUNNING == "running"
        assert PipelineStatus.COMPLETED == "completed"
        assert PipelineStatus.ERROR == "error"

    def test_from_str(self):
        assert PipelineStatus("pending") == PipelineStatus.PENDING
        assert PipelineStatus("running") == PipelineStatus.RUNNING
        assert PipelineStatus("completed") == PipelineStatus.COMPLETED
        assert PipelineStatus("error") == PipelineStatus.ERROR

    def test_invalid_status(self):
        with pytest.raises(ValueError):
            PipelineStatus("unknown_status")

    def test_count(self):
        assert len(PipelineStatus) == 4


class TestActionType:
    def test_values(self):
        assert ActionType.EXECUTE == "execute"
        assert ActionType.DONE == "done"
        assert ActionType.ERROR == "error"

    def test_from_str(self):
        assert ActionType("execute") == ActionType.EXECUTE
        assert ActionType("done") == ActionType.DONE
        assert ActionType("error") == ActionType.ERROR

    def test_invalid_action(self):
        with pytest.raises(ValueError):
            ActionType("unknown_action")

    def test_count(self):
        assert len(ActionType) == 3
