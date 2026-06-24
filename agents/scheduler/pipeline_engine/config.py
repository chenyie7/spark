"""配置加载器 — 读取 pipeline.yaml 并反序列化为严格校验后的 PipelineConfig。

遵循 Spring Boot @ConfigurationProperties 模式：
1. 使用 PyYAML 加载 YAML
2. 通过 from_dict() 反序列化为类型化 dataclass 树
3. 执行语义校验（边引用、DAG 完整性等）
4. 返回 PipelineConfig，或抛出带精确错误信息的 ConfigLoadError
"""

from pathlib import Path
from pipeline_engine.models import PipelineConfig

try:
    import yaml
except ImportError:
    yaml = None


class ConfigLoadError(Exception):
    """pipeline.yaml 无法加载或校验失败时抛出。"""
    pass


def load_pipeline(pipeline_path: Path) -> PipelineConfig:
    """加载并严格校验 pipeline.yaml 文件。

    Args:
        pipeline_path: pipeline YAML 文件的路径。

    Returns:
        经过完整校验的 PipelineConfig 实例。

    Raises:
        ConfigLoadError: 文件缺失、YAML 无效、必填字段缺失、或语义错误
                         （如边引用了不存在的节点）。
    """
    if yaml is None:
        raise ConfigLoadError(
            "需要 PyYAML。安装命令：pip3 install pyyaml"
        )

    if not pipeline_path.exists():
        raise ConfigLoadError(f"流水线文件不存在: {pipeline_path}")

    # ── 阶段 1：解析 YAML ────────────────────────────────────────────
    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"解析 YAML 失败 {pipeline_path}: {e}")

    if data is None:
        raise ConfigLoadError(f"流水线文件为空: {pipeline_path}")

    if not isinstance(data, dict):
        raise ConfigLoadError(
            f"流水线 YAML 必须是映射类型，实际为 {type(data).__name__}"
        )

    # ── 阶段 2：反序列化为类型化树 ───────────────────────────────────
    try:
        config = PipelineConfig.from_dict(data)
    except (ValueError, KeyError) as e:
        raise ConfigLoadError(f"流水线配置无效 {pipeline_path}: {e}")

    # ── 阶段 3：语义校验 ─────────────────────────────────────────────
    _validate_edges(config)
    _validate_start_nodes(config)

    return config


def _validate_edges(config: PipelineConfig) -> None:
    """确保所有边的 'from' 和 'to'（非 DONE）引用了存在的节点。"""
    node_ids = {n.id for n in config.nodes}
    for edge in config.edges:
        if edge.from_node not in node_ids:
            raise ConfigLoadError(
                f"边引用了未知节点 '{edge.from_node}'（在 'from' 字段中）。"
                f"可用节点: {sorted(node_ids)}"
            )
        if edge.to != "DONE" and edge.to not in node_ids:
            raise ConfigLoadError(
                f"边引用了未知节点 '{edge.to}'（在 'to' 字段中）。"
                f"可用节点: {sorted(node_ids)}"
            )


def _validate_start_nodes(config: PipelineConfig) -> None:
    """确保至少存在一个起始节点（入度为 0）。"""
    start_nodes = config.get_start_nodes()
    if not start_nodes:
        raise ConfigLoadError(
            "未找到起始节点。至少需要一个节点没有入边。"
        )
