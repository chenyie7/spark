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

    def test_start_when_already_running_raises(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("first")
        with pytest.raises(RuntimeError, match="已在运行"):
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
        engine.next()  # returns coder, sets current_nodes=["coder"]
        # coder not reported yet — still in progress
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "仍在执行中" in action.message

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
        assert "成功完成" in action.message

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
        # Fix prompt should reference review-output
        assert "review-output" in action.nodes[0].prompt.lower()

    def test_max_retries_exhausted(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        # Simulate 3 rounds of failure (round 0, 1, 2 → 3 rounds)
        for round_num in range(3):
            engine.next()  # coder
            engine.report("coder", NodeStatus.SUCCESS, f"fix round {round_num}")
            engine.next()  # reviewer
            engine.report("reviewer", NodeStatus.SUCCESS, "still failing", agent_verdict="REVIEW_FAILED")
        # After 3rd FAILED, max_retries exhausted
        action = engine.next()
        assert action.action == ActionType.DONE
        assert "最大重试" in action.message

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
        assert "错误" in action.message
    # ── Non-reviewer node failure tests (C1) ─────────────────────────

    def test_coder_error_returns_error_not_success(self, sample_pipeline_path: Path, state_path: Path):
        """Coder returns ERROR (agent crash) -> pipeline should ERROR, not claim success."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.ERROR, "process crashed")
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "失败" in action.message
        assert "成功" not in action.message

    def test_coder_failed_returns_error_not_success(self, sample_pipeline_path: Path, state_path: Path):
        """Coder returns FAILED -> pipeline should ERROR, not claim success."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.FAILED, "build failed")
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "失败" in action.message
        assert "成功" not in action.message

    def test_reviewer_failed_empty_verdict_returns_error(self, sample_pipeline_path: Path, state_path: Path):
        """Reviewer returns FAILED status with empty verdict -> pipeline should ERROR."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        engine.next()  # reviewer
        engine.report("reviewer", NodeStatus.FAILED, "crashed without verdict", agent_verdict="")
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "失败" in action.message
        assert "成功" not in action.message


    def test_coder_prompt_contains_target_dir(self, sample_pipeline_path, state_path):
        """coder prompt 中包含自定义 target_dir"""
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine._ensure_state()
        engine.state.target_dir = "admin-test"
        engine._save_state()
        action = engine.next()
        assert action.nodes[0].node_id == "coder"
        assert "admin-test/src/main/java" in action.nodes[0].prompt

    def test_reviewer_prompt_contains_target_dir(self, sample_pipeline_path, state_path):
        """reviewer prompt 中包含自定义 target_dir"""
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine
        from pipeline_engine.models import NodeStatus
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine._ensure_state()
        engine.state.target_dir = "modules/user"
        engine._save_state()
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()  # reviewer
        assert action.nodes[0].node_id == "reviewer"
        assert "modules/user/src/main/java" in action.nodes[0].prompt

    def test_prompt_contains_run_id(self, sample_pipeline_path: Path, state_path: Path):
        """reviewer prompt should include run_id from state."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        # Manually set run_id on state (simulating what CLI start does)
        engine._ensure_state()
        engine.state.run_id = "20260624103000-001"
        engine._save_state()
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()  # reviewer
        assert action.nodes[0].node_id == "reviewer"
        assert "20260624103000-001" in action.nodes[0].prompt


class TestPipelineEngineReport:
    def test_report_with_verdict(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # sets current_nodes=["coder"]
        state = engine.report("coder", NodeStatus.SUCCESS, "ok")
        assert "coder" in state.node_results
        assert state.node_results["coder"].status == NodeStatus.SUCCESS

    def test_report_unknown_node(self, sample_pipeline_path: Path, state_path: Path):
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        with pytest.raises(ValueError, match="不在 current_nodes"):
            engine.report("reviewer", NodeStatus.SUCCESS, "?")

    def test_double_report_raises(self, sample_pipeline_path: Path, state_path: Path):
        """Reporting the same node twice should raise ValueError."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # sets current_nodes=["coder"]
        engine.report("coder", NodeStatus.SUCCESS, "first report")
        with pytest.raises(ValueError, match="已上报过"):
            engine.report("coder", NodeStatus.SUCCESS, "duplicate report")


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


class TestPipelineEngineStateRecovery:
    def test_next_after_state_reload(self, sample_pipeline_path: Path, state_path: Path):
        """Verify that re-creating engine from persisted state continues correctly."""
        config = load_pipeline(sample_pipeline_path)
        # First session
        engine1 = PipelineEngine(config, state_path)
        engine1.start("test")
        engine1.next()  # coder
        engine1.report("coder", NodeStatus.SUCCESS, "ok")

        # Simulate restart — create new engine from same state file
        engine2 = PipelineEngine(config, state_path)
        action = engine2.next()
        assert action.action == ActionType.EXECUTE
        assert action.nodes[0].node_id == "reviewer"
