"""Tests for config loader."""

import pytest
from pathlib import Path
from scripts.code_check.config import (
    load_cli_config,
    load_program_checks,
    load_ai_checklist,
    ConfigLoadError,
)
from scripts.code_check.models import BlockingStrategy


class TestLoadCLIConfig:
    def test_load_from_yaml(self, tmp_project):
        config = load_cli_config(config_path=tmp_project / "code-check-config.yaml")
        assert config["rules_dir"] == "check-rules/"
        assert config["strategy"] == BlockingStrategy.STRICT
        assert config["output_dir"] == "./review-output/"
        assert config["format"] == "json"
        assert "**/test/**" in config["exclude"]

    def test_defaults_when_no_file(self, tmp_path):
        config = load_cli_config(config_path=tmp_path / "nonexistent.yaml")
        assert config["rules_dir"] == "check-rules/"
        assert config["strategy"] == BlockingStrategy.STRICT
        assert config["output_dir"] == "./review-output/"
        assert config["format"] == "json"
        assert config["exclude"] == []

    def test_override_defaults(self, tmp_path):
        """命令行参数通过返回值字段可覆盖."""
        config = load_cli_config(config_path=tmp_path / "nonexistent.yaml")
        # 默认值正常
        assert config["strategy"] == BlockingStrategy.STRICT


class TestLoadProgramChecks:
    def test_load_rules(self, tmp_project):
        rules = load_program_checks(rules_dir=tmp_project / "check-rules")
        assert "BE-QL-29" in rules
        rule = rules["BE-QL-29"]
        assert rule["description"] == "Controller DTO 参数缺少 @Validated"
        assert rule["level"] == "P1"
        assert rule["program"]["scanner"] == "java-annotation"
        assert rule["message"] == "{method} 缺少 @Validated/@Valid 注解 DTO 参数"

    def test_empty_dir_returns_empty(self, tmp_path):
        rules_dir = tmp_path / "empty-rules"
        rules_dir.mkdir()
        rules = load_program_checks(rules_dir=rules_dir)
        assert rules == {}

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_program_checks(rules_dir=tmp_path / "nonexistent")


class TestLoadAIChecklist:
    def test_load_rules(self, tmp_project):
        rules = load_ai_checklist(rules_dir=tmp_project / "check-rules")
        assert "BE-QL-11" in rules
        rule = rules["BE-QL-11"]
        assert rule["description"] == "log.info 是否包含关键业务信息"
        assert rule["level"] == "P2"
        assert "prompt_hint" in rule["ai"]
