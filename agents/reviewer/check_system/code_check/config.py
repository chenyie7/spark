"""Configuration loader — reads yaml configs for code-check."""

from pathlib import Path
from typing import Any
from agents.reviewer.check_system.code_check.models import BlockingStrategy

# PyYAML is the only external dependency. Fall back gracefully if missing.
try:
    import yaml
except ImportError:
    yaml = None


class ConfigLoadError(Exception):
    """Raised when a required config file cannot be loaded."""
    pass


# ── default config ──────────────────────────────────────────────

DEFAULT_CLI_CONFIG: dict[str, Any] = {
    "rules_dir": "agents/reviewer/check_system/rules/",
    "strategy": BlockingStrategy.STRICT,
    "output_dir": "./review-output/",
    "format": "json",
    "exclude": [],
}


def _read_yaml(path: Path) -> dict:
    """Read a YAML file, returning empty dict if file missing."""
    if yaml is None:
        raise ConfigLoadError(
            "PyYAML is required. Install with: pip3 install pyyaml"
        )
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if data else {}


# ── CLI Config ──────────────────────────────────────────────────

def load_cli_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load CLI config from code-check-config.yaml, falling back to defaults.

    Returns a mutable dict that can be overridden by CLI args.
    """
    config = dict(DEFAULT_CLI_CONFIG)

    if config_path is None:
        config_path = Path("code-check-config.yaml")

    file_data = _read_yaml(config_path)
    if not file_data:
        return config

    # Map yaml values — only override if present
    for key in ("rules_dir", "output_dir", "format"):
        if key in file_data:
            config[key] = file_data[key]

    # strategy: map string to enum
    if "strategy" in file_data:
        strat = file_data["strategy"]
        if isinstance(strat, str):
            config["strategy"] = BlockingStrategy(strat)

    # exclude: ensure list type
    if "exclude" in file_data:
        raw = file_data["exclude"]
        config["exclude"] = raw if isinstance(raw, list) else [raw]

    return config


# ── Rule Loaders ────────────────────────────────────────────────

def _load_rule_file(filename: str, rules_dir: Path | None = None) -> dict:
    """Load a single rule file from the rules directory.

    Args:
        filename: Name of the yaml file (e.g. 'program-checks.yaml').
        rules_dir: Path to the check-rules directory.

    Returns:
        Dict keyed by check code, or empty dict if file not found.

    Raises:
        ConfigLoadError: If the rules directory does not exist.
    """
    if rules_dir is None:
        rules_dir = Path("agents/reviewer/check_system/rules")

    rules_dir = Path(rules_dir)
    if not rules_dir.exists():
        raise ConfigLoadError(f"Rules directory not found: {rules_dir}")

    file_path = rules_dir / filename
    if not file_path.exists():
        return {}

    return _read_yaml(file_path)


def load_program_checks(rules_dir: Path | None = None) -> dict:
    """Load program check rules from program-checks.yaml.

    Returns dict keyed by check code (e.g. 'BE-QL-29').
    """
    return _load_rule_file("program-checks.yaml", rules_dir)


def load_ai_checklist(rules_dir: Path | None = None) -> dict:
    """Load AI checklist rules from ai-checklist.yaml.

    Returns dict keyed by check code (e.g. 'BE-QL-11').
    """
    return _load_rule_file("ai-checklist.yaml", rules_dir)
