# tests/test_models.py
import pytest
from pipeline_engine.models import (
    TriggerType, NodeStatus, PipelineStatus, ActionType,
    PipelineDefaults, EdgeCondition, EdgeConfig, NodeConfig, PipelineConfig,
    NodeResult, PipelineState, NodeToExecute, NextAction,
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

    def test_from_dict_invalid_type(self):
        with pytest.raises(ValueError, match="must be a dict"):
            PipelineDefaults.from_dict("not-a-dict")


class TestEdgeCondition:
    def test_from_dict(self):
        obj = EdgeCondition.from_dict({"status": "REVIEW_FAILED"})
        assert obj.status == "REVIEW_FAILED"

    def test_from_dict_missing_status(self):
        with pytest.raises(ValueError, match="condition.status is required"):
            EdgeCondition.from_dict({})

    def test_to_dict(self):
        obj = EdgeCondition.from_dict({"status": "REVIEW_FAILED"})
        d = obj.to_dict()
        assert d == {"status": "REVIEW_FAILED"}

    def test_from_dict_invalid_type(self):
        with pytest.raises(ValueError, match="must be a dict"):
            EdgeCondition.from_dict("not-a-dict")


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

    def test_invalid_trigger(self):
        d = {"from": "coder", "to": "reviewer", "trigger": "invalid_trigger"}
        with pytest.raises(ValueError):
            EdgeConfig.from_dict(d)

    def test_from_dict_invalid_type(self):
        with pytest.raises(ValueError, match="must be a dict"):
            EdgeConfig.from_dict("not-a-dict")


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

    def test_from_dict_missing_id(self):
        d = {"type": "agent", "agent": "checker", "description": "x",
             "prompt_template": "Check."}
        with pytest.raises(ValueError, match="node.id is required"):
            NodeConfig.from_dict(d)

    def test_from_dict_missing_prompt_template(self):
        d = {"id": "checker", "type": "agent", "agent": "checker",
             "description": "x"}
        with pytest.raises(ValueError, match="node.prompt_template is required"):
            NodeConfig.from_dict(d)

    def test_from_dict_invalid_type(self):
        with pytest.raises(ValueError, match="must be a dict"):
            NodeConfig.from_dict("not-a-dict")


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

    def test_missing_name(self):
        d = {"version": "1", "description": "d",
             "defaults": {}, "nodes": [], "edges": []}
        with pytest.raises(ValueError, match="pipeline.name is required"):
            PipelineConfig.from_dict(d)

    def test_from_dict_invalid_type(self):
        with pytest.raises(ValueError, match="must be a dict"):
            PipelineConfig.from_dict([1, 2, 3])


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
        assert obj.outputs == {}

    def test_timestamp_auto_generated(self):
        obj = NodeResult(node_id="t", status=NodeStatus.SUCCESS)
        assert obj.timestamp != ""
        assert "T" in obj.timestamp


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
        assert obj.current_nodes == []

    def test_error(self):
        obj = PipelineState(pipeline_name="test")
        obj.error()
        assert obj.status == PipelineStatus.ERROR

    def test_record_result(self):
        obj = PipelineState(pipeline_name="test")
        obj.start()
        result = NodeResult(node_id="coder", status=NodeStatus.SUCCESS,
                            summary="5 files")
        obj.record_result(result)
        assert "coder" in obj.node_results
        assert len(obj.history) == 1
        assert obj.history[0]["node"] == "coder"

    def test_increment_round(self):
        obj = PipelineState(pipeline_name="test")
        assert obj.round == 0
        obj.increment_round()
        assert obj.round == 1


class TestNodeToExecute:
    def test_to_dict(self):
        obj = NodeToExecute(node_id="coder", agent_type="coder",
                            prompt="Generate code", timeout="900s",
                            round=1, phase="fix")
        d = obj.to_dict()
        assert d["node_id"] == "coder"
        assert d["prompt"] == "Generate code"
        assert d["phase"] == "fix"
        assert d["round"] == 1
        assert d["timeout"] == "900s"


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

    def test_to_dict_error(self):
        obj = NextAction(action=ActionType.ERROR, message="Something went wrong")
        d = obj.to_dict()
        assert d["action"] == "error"
        assert d["message"] == "Something went wrong"

    def test_to_json(self):
        obj = NextAction(action=ActionType.DONE, message="Done!")
        j = obj.to_json()
        assert '"action": "done"' in j
        assert '"message": "Done!"' in j

    def test_parallel_nodes(self):
        n1 = NodeToExecute(node_id="checker_a", agent_type="reviewer",
                           prompt="Check A", timeout="300s", round=0, phase="review")
        n2 = NodeToExecute(node_id="checker_b", agent_type="reviewer",
                           prompt="Check B", timeout="300s", round=0, phase="review")
        obj = NextAction(action=ActionType.EXECUTE, nodes=[n1, n2],
                         message="Run 2 checks in parallel")
        d = obj.to_dict()
        assert len(d["nodes"]) == 2
