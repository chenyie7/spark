import json
import pytest
from pathlib import Path

SAMPLE_PIPELINE_YAML = """
name: test-pipeline
version: "1.0"
description: "Test pipeline for unit tests"

defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]

nodes:
  - id: coder
    type: agent
    agent: coder
    description: "Generate code"
    prompt_template: |
      Generate code for: {requirement}
      Output: {target_dir}/src/main/java
      {review_context}
    inputs:
      requirement: "${user_input}"
    outputs:
      target_dir: "{target_dir}/src/main/java"
    timeout: 900s

  - id: reviewer
    type: agent
    agent: reviewer
    description: "Review code"
    prompt_template: |
      Review code at {target_dir}/src/main/java.
      Output directory: review-output/{run_id}/
      Return REVIEW_PASSED, REVIEW_FAILED, or REVIEW_ERROR.
    inputs:
      coder_output: "${coder.outputs.target_dir}"
    outputs:
      final_report: "review-output/{run_id}/final-review-report.md"
    timeout: 600s

edges:
  - from: coder
    to: reviewer
    trigger: on_success
    description: "coder done → reviewer"

  - from: reviewer
    to: coder
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: "review FAILED → fix loop"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_PASSED
    description: "review PASSED → done"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_FAILED
    description: "max_retries reached → done"

  - from: reviewer
    to: DONE
    trigger: on_condition
    condition:
      status: REVIEW_ERROR
    description: "review ERROR → done"
"""


@pytest.fixture
def sample_pipeline_yaml() -> str:
    return SAMPLE_PIPELINE_YAML


@pytest.fixture
def sample_pipeline_path(tmp_path: Path) -> Path:
    p = tmp_path / "test-pipeline.yaml"
    p.write_text(SAMPLE_PIPELINE_YAML)
    return p


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "pipeline-state.json"


@pytest.fixture
def sample_pipeline_dict() -> dict:
    return json.loads("""
    {
        "name": "test-pipeline",
        "version": "1.0",
        "description": "Test pipeline",
        "defaults": {"timeout": "600s", "max_retries": 3, "block_on": ["P0"]},
        "nodes": [
            {
                "id": "coder", "type": "agent", "agent": "coder",
                "description": "Generate code",
                "prompt_template": "Generate: {requirement} to {target_dir}/src/main/java",
                "inputs": {"requirement": "${user_input}"},
                "outputs": {"target_dir": "{target_dir}/src/main/java"},
                "timeout": "900s"
            },
            {
                "id": "reviewer", "type": "agent", "agent": "reviewer",
                "description": "Review code",
                "prompt_template": "Review {target_dir}/src/main/java. Output: review-output/{run_id}/",
                "inputs": {"coder_output": "${coder.outputs.target_dir}"},
                "outputs": {"final_report": "review-output/{run_id}/final-review-report.md"},
                "timeout": "600s"
            }
        ],
        "edges": [
            {"from": "coder", "to": "reviewer", "trigger": "on_success", "description": ""},
            {"from": "reviewer", "to": "coder", "trigger": "on_condition", "condition": {"status": "REVIEW_FAILED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_PASSED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_FAILED"}, "description": ""},
            {"from": "reviewer", "to": "DONE", "trigger": "on_condition", "condition": {"status": "REVIEW_ERROR"}, "description": ""}
        ]
    }
    """)
