"""Configuration loader — reads yaml configs for code-check."""

from pathlib import Path
from typing import Any
from scripts.code_check.models import BlockingStrategy

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
    "rules_dir": "check-rules/",
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

    # exclude: ensure list
    if "exclude" in file_data:
        config["exclude"] = file_data["exclude"]

    return config


# ── Rule Loaders ────────────────────────────────────────────────

def load_program_checks(rules_dir: Path | None = None) -> dict:
    """Load program check rules from program-checks.yaml.

    Returns dict keyed by check code (e.g. 'BE-QL-29').
    """
    if rules_dir is None:
        rules_dir = Path("check-rules")

    rules_dir = Path(rules_dir)
    if not rules_dir.exists():
        raise ConfigLoadError(f"Rules directory not found: {rules_dir}")

    file_path = rules_dir / "program-checks.yaml"
    if not file_path.exists():
        return {}

    data = _read_yaml(file_path)
    if data is None:
        return {}
    return data


def load_ai_checklist(rules_dir: Path | None = None) -> dict:
    """Load AI checklist rules from ai-checklist.yaml.

    Returns dict keyed by check code (e.g. 'BE-QL-11').
    """
    if rules_dir is None:
        rules_dir = Path("check-rules")

    rules_dir = Path(rules_dir)
    if not rules_dir.exists():
        raise ConfigLoadError(f"Rules directory not found: {rules_dir}")

    file_path = rules_dir / "ai-checklist.yaml"
    if not file_path.exists():
        return {}

    data = _read_yaml(file_path)
    if data is None:
        return {}
    return data
