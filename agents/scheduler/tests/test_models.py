# tests/test_models.py
import pytest
from pipeline_engine.models import (
    TriggerType, NodeStatus, PipelineStatus, ActionType,
    PipelineDefaults, EdgeCondition, EdgeConfig, NodeConfig, PipelineConfig,
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
        assert len(edges) == 4  # -> coder, DONEx3

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


class TestPipelineConfigValidation:
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
