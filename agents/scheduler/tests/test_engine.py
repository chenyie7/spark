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
        engine.next()  # returns coder, sets current_nodes=["coder"]
        # coder not reported yet — still in progress
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
        assert "failed" in action.message.lower()
        assert "successfully" not in action.message.lower()

    def test_coder_failed_returns_error_not_success(self, sample_pipeline_path: Path, state_path: Path):
        """Coder returns FAILED -> pipeline should ERROR, not claim success."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # coder
        engine.report("coder", NodeStatus.FAILED, "build failed")
        action = engine.next()
        assert action.action == ActionType.ERROR
        assert "failed" in action.message.lower()
        assert "successfully" not in action.message.lower()

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
        assert "failed" in action.message.lower()
        assert "successfully" not in action.message.lower()


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
        with pytest.raises(ValueError, match="not in current_nodes"):
            engine.report("reviewer", NodeStatus.SUCCESS, "?")

    def test_double_report_raises(self, sample_pipeline_path: Path, state_path: Path):
        """Reporting the same node twice should raise ValueError."""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine.next()  # sets current_nodes=["coder"]
        engine.report("coder", NodeStatus.SUCCESS, "first report")
        with pytest.raises(ValueError, match="already been reported"):
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
