"""Shared fixtures for code-check tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_config_dict():
    """A valid CLI config dict for testing."""
    return {
        "rules_dir": "check-rules/",
        "strategy": "strict",
        "output_dir": "./review-output/",
        "format": "json",
        "exclude": ["**/test/**", "**/target/**"],
    }


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project structure with config and Java files."""
    project = tmp_path / "test-project"
    project.mkdir()

    # Create config
    config_file = project / "code-check-config.yaml"
    config_file.write_text("""
rules_dir: check-rules/
strategy: strict
output_dir: ./review-output/
format: json
exclude:
  - "**/test/**"
""")

    # Create rules dir
    rules_dir = project / "check-rules"
    rules_dir.mkdir()
    (rules_dir / "program-checks.yaml").write_text("""
BE-QL-29:
  description: "Controller DTO 参数缺少 @Validated"
  level: P1
  program:
    scanner: java-annotation
    on_class: "RestController|Controller"
    target: method_param
    match_param_type: "DTO|Request|Command"
    missing_annotation: "@Validated|@Valid"
  message: "{method} 缺少 @Validated/@Valid 注解 DTO 参数"
""")

    (rules_dir / "ai-checklist.yaml").write_text("""
BE-QL-11:
  description: "log.info 是否包含关键业务信息"
  level: P2
  ai:
    prompt_hint: "检查 log.info 是否包含关键业务标识"
""")

    return project
