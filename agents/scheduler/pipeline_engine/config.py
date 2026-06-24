"""Configuration loader -- reads pipeline.yaml into typed PipelineConfig with strict validation.

Follows the Spring Boot @ConfigurationProperties pattern:
1. Load YAML with PyYAML
2. Deserialize into typed dataclass tree via from_dict()
3. Run semantic validations (edge references, DAG integrity, etc.)
4. Return immutable PipelineConfig or raise ConfigLoadError with precise message
"""

from pathlib import Path
from pipeline_engine.models import PipelineConfig

try:
    import yaml
except ImportError:
    yaml = None


class ConfigLoadError(Exception):
    """Raised when a pipeline.yaml cannot be loaded or fails validation."""
    pass


def load_pipeline(pipeline_path: Path) -> PipelineConfig:
    """Load and strictly validate a pipeline.yaml file.

    Args:
        pipeline_path: Path to the pipeline YAML file.

    Returns:
        A fully validated PipelineConfig instance.

    Raises:
        ConfigLoadError: If the file is missing, invalid YAML, missing required
                         fields, or contains semantic errors (e.g. edge references
                         to non-existent nodes).
    """
    if yaml is None:
        raise ConfigLoadError(
            "PyYAML is required. Install with: pip3 install pyyaml"
        )

    if not pipeline_path.exists():
        raise ConfigLoadError(f"Pipeline file not found: {pipeline_path}")

    # -- Phase 1: Parse YAML --------------------------------------------------
    try:
        with open(pipeline_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"Failed to parse YAML in {pipeline_path}: {e}")

    if data is None:
        raise ConfigLoadError(f"Pipeline file is empty: {pipeline_path}")

    if not isinstance(data, dict):
        raise ConfigLoadError(
            f"Pipeline YAML must be a mapping, got {type(data).__name__}"
        )

    # -- Phase 2: Deserialize to typed tree -----------------------------------
    try:
        config = PipelineConfig.from_dict(data)
    except (ValueError, KeyError) as e:
        raise ConfigLoadError(f"Invalid pipeline config in {pipeline_path}: {e}")

    # -- Phase 3: Semantic validation -----------------------------------------
    _validate_edges(config)
    _validate_start_nodes(config)

    return config


def _validate_edges(config: PipelineConfig) -> None:
    """Ensure all edge 'from' and 'to' (non-DONE) nodes exist."""
    node_ids = {n.id for n in config.nodes}
    for edge in config.edges:
        if edge.from_node not in node_ids:
            raise ConfigLoadError(
                f"Edge references unknown node '{edge.from_node}' in 'from' field. "
                f"Available nodes: {sorted(node_ids)}"
            )
        if edge.to != "DONE" and edge.to not in node_ids:
            raise ConfigLoadError(
                f"Edge references unknown node '{edge.to}' in 'to' field. "
                f"Available nodes: {sorted(node_ids)}"
            )


def _validate_start_nodes(config: PipelineConfig) -> None:
    """Ensure there is at least one start node (in-degree = 0)."""
    start_nodes = config.get_start_nodes()
    if not start_nodes:
        raise ConfigLoadError(
            "No start nodes found. At least one node must have no incoming edges."
        )
