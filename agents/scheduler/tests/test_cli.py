# tests/test_cli.py
import json
import os
import subprocess
import sys
from pathlib import Path

# The scheduler directory (parent of tests/) must be on PYTHONPATH so that
# the subprocess can find the pipeline_engine package.
SCHEDULER_DIR = Path(__file__).resolve().parent.parent

CLI_ENTRY = [sys.executable, "-m", "pipeline_engine.cli"]


def run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCHEDULER_DIR)
    return subprocess.run(
        CLI_ENTRY + args,
        capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )


def _make_minimal_pipeline(tmp_path: Path) -> Path:
    """Create a minimal pipeline.yaml for CLI testing."""
    p = tmp_path / "pipeline.yaml"
    p.write_text("""
name: cli-test
version: "1.0"
description: CLI test
defaults:
  timeout: 300s
  max_retries: 2
  block_on: [P0]
nodes:
  - id: coder
    type: agent
    agent: coder
    description: Generate code
    prompt_template: "Generate: {requirement} to {target_dir}/src/main/java"
    timeout: 500s
  - id: reviewer
    type: agent
    agent: reviewer
    description: Review
    prompt_template: "Review."
    timeout: 300s
edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: go
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: done
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: done
  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: done
""")
    return p


class TestCLIStart:
    def test_start_ok(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "pipeline-state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test feature",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "started"
        assert state_file.exists()

    def test_start_returns_run_id(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "pipeline-state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "run_id" in data
        assert len(data["run_id"]) == 18  # YYYYMMDDHHmmss-NNN

    def test_start_no_pipeline(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(tmp_path / "nonexistent.yaml"),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode != 0

    def test_start_stores_target_dir_in_state(self, tmp_path):
        """start --target-dir admin-test 将值写入状态文件"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
            "--target-dir", "admin-test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data.get("target_dir") == "admin-test"

    def test_start_defaults_target_dir_to_dot(self, tmp_path):
        """start 不传 --target-dir 时默认为 '.'"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data.get("target_dir") == "."


class TestCLINext:
    def test_next_returns_coder(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        result = run_cli(["next", "--state-file", str(state_file),
                          "--pipeline", str(pipeline_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["action"] == "execute"
        assert data["nodes"][0]["node_id"] == "coder"
        assert "test" in data["nodes"][0]["prompt"]

    def test_next_no_state(self, tmp_path: Path):
        result = run_cli(["next", "--state-file", str(tmp_path / "no-state.json")], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["action"] == "error"
        assert "未找到流水线状态" in data["message"]

    def test_next_prompt_contains_target_dir(self, tmp_path):
        """next 返回的 prompt 中包含自定义 target_dir"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test",
                 "--target-dir", "custom-module"], cwd=tmp_path)
        result = run_cli(["next", "--state-file", str(state_file),
                          "--pipeline", str(pipeline_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "custom-module/src/main/java" in data["nodes"][0]["prompt"]


class TestCLIReport:
    def test_report_coder_success(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        run_cli(["next", "--state-file", str(state_file),
                 "--pipeline", str(pipeline_file)], cwd=tmp_path)
        result = run_cli([
            "report", "--state-file", str(state_file),
            "--pipeline", str(pipeline_file),
            "--node", "coder", "--status", "success",
            "--summary", "Generated 3 files",
        ], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["accepted"] is True

    def test_report_with_verdict(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        run_cli(["next", "--state-file", str(state_file),
                 "--pipeline", str(pipeline_file)], cwd=tmp_path)
        run_cli(["report", "--state-file", str(state_file),
                 "--pipeline", str(pipeline_file),
                 "--node", "coder", "--status", "success"], cwd=tmp_path)
        run_cli(["next", "--state-file", str(state_file),
                 "--pipeline", str(pipeline_file)], cwd=tmp_path)
        result = run_cli([
            "report", "--state-file", str(state_file),
            "--pipeline", str(pipeline_file),
            "--node", "reviewer", "--status", "success",
            "--verdict", "REVIEW_PASSED", "--summary", "All good",
        ], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["accepted"] is True


class TestCLIStatus:
    def test_status(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        result = run_cli(["status", "--state-file", str(state_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "running"


class TestCLIReset:
    def test_reset(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test"], cwd=tmp_path)
        assert state_file.exists()
        result = run_cli(["reset", "--state-file", str(state_file)], cwd=tmp_path)
        assert result.returncode == 0
        assert not state_file.exists()
