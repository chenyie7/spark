"""配置加载模块。

从 benchmarks/config.yaml 加载配置，以 dataclass 形式暴露。
全项目零硬编码路径和阈值。
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RetentionConfig:
    max_days: int = 7


@dataclass
class PathsConfig:
    dumps_dir: str = "benchmarks/dumps"
    output_dir: str = "benchmarks"


@dataclass
class BenchmarkConfig:
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    pipeline_log_template: str = "{run_id}/pipeline-log.jsonl"


def load_config(project_dir: str = ".") -> BenchmarkConfig:
    """从 benchmarks/config.yaml 加载配置。

    Args:
        project_dir: 项目根目录路径

    Returns:
        BenchmarkConfig 实例，缺失字段使用默认值
    """
    config_path = Path(project_dir) / "benchmarks" / "config.yaml"

    if not config_path.exists():
        return BenchmarkConfig()

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    return BenchmarkConfig(
        retention=RetentionConfig(
            max_days=raw.get("retention", {}).get("max_days", 7),
        ),
        paths=PathsConfig(
            dumps_dir=raw.get("paths", {}).get("dumps_dir", "benchmarks/dumps"),
            output_dir=raw.get("paths", {}).get("output_dir", "benchmarks"),
        ),
        pipeline_log_template=raw.get(
            "pipeline_log_template", "{run_id}/pipeline-log.jsonl"
        ),
    )


def resolve_path(project_dir: str, relative_path: str) -> Path:
    """将配置中的相对路径解析为绝对 Path。"""
    return (Path(project_dir) / relative_path).resolve()
