# tests/test_config.py
import pytest
from pathlib import Path
from pipeline_engine.config import load_pipeline, ConfigLoadError
from pipeline_engine.models import PipelineConfig, TriggerType


class TestLoadPipeline:
    def test_load_valid_pipeline(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        assert isinstance(config, PipelineConfig)
        assert config.name == "test-pipeline"
        assert len(config.nodes) == 2
        assert len(config.edges) == 5

    def test_load_defaults(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        assert config.defaults.timeout == "600s"
        assert config.defaults.max_retries == 3

    def test_load_nodes(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        coder = config.get_node("coder")
        assert coder.agent == "coder"
        assert "Generate code for:" in coder.prompt_template
        assert coder.timeout == "900s"

    def test_load_edges(self, sample_pipeline_path: Path):
        config = load_pipeline(sample_pipeline_path)
        edges = config.get_outgoing_edges("reviewer")
        assert len(edges) == 4
        on_cond_edges = [e for e in edges if e.trigger == TriggerType.ON_CONDITION]
        assert len(on_cond_edges) == 4


class TestLoadPipelineErrors:
    def test_file_not_found(self):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_pipeline(Path("/nonexistent/pipeline.yaml"))

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        with pytest.raises(ConfigLoadError, match="empty"):
            load_pipeline(p)

    def test_not_a_mapping(self, tmp_path: Path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2")
        with pytest.raises(ConfigLoadError):
            load_pipeline(p)

    def test_missing_name(self, tmp_path: Path):
        p = tmp_path / "no_name.yaml"
        p.write_text("version: '1.0'\ndescription: test\nnodes: []\nedges: []")
        with pytest.raises(ConfigLoadError, match="name"):
            load_pipeline(p)

    def test_edge_references_missing_node(self, tmp_path: Path):
        p = tmp_path / "bad_edge.yaml"
        p.write_text("""
name: test
version: "1.0"
description: test
defaults: {}
nodes:
  - id: coder
    type: agent
    agent: coder
    description: "d"
    prompt_template: "p"
edges:
  - from: nonexistent
    to: coder
    trigger: on_success
    description: ""
""")
        with pytest.raises(ConfigLoadError, match="unknown node"):
            load_pipeline(p)

    def test_no_start_nodes(self, tmp_path: Path):
        p = tmp_path / "no_start.yaml"
        p.write_text("""
name: test
version: "1.0"
description: test
defaults: {}
nodes:
  - id: node_a
    type: agent
    agent: coder
    description: "d"
    prompt_template: "p"
  - id: node_b
    type: agent
    agent: reviewer
    description: "d"
    prompt_template: "p"
edges:
  - from: node_a
    to: node_b
    trigger: on_success
    description: ""
  - from: node_b
    to: node_a
    trigger: on_success
    description: ""
""")
        with pytest.raises(ConfigLoadError, match="start"):
            load_pipeline(p)
