"""DAG state machine — the core of the pipeline scheduler.

PipelineEngine manages the lifecycle of a pipeline execution:
  start  -> initialize state from PipelineConfig
  next   -> evaluate DAG edges, determine next node(s) to execute
  report -> record node execution result, update state
  status -> return current state summary
  reset  -> clear state file

Key design: the engine does NOT execute agents. It only makes routing
decisions. Claude Code Agent handles actual agent execution via the Agent tool.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from pipeline_engine.models import (
    PipelineConfig, PipelineState, NodeResult, NextAction, NodeToExecute,
    PipelineStatus, NodeStatus, ActionType, TriggerType,
)


def load_pipeline_config(pipeline_path: Path) -> "PipelineConfig":
    """Convenience: load config from a YAML path. Uses config.load_pipeline internally."""
    from pipeline_engine.config import load_pipeline
    return load_pipeline(pipeline_path)


class PipelineEngine:
    """DAG state machine that routes pipeline execution.

    Args:
        config: Fully validated PipelineConfig from config.load_pipeline().
        state_path: Path to the persistent state JSON file.
    """

    def __init__(self, config: PipelineConfig, state_path: Path):
        self.config = config
        self.state_path = Path(state_path)
        self.state: PipelineState | None = None

    # -- Public API ----------------------------------------------------

    def start(self, requirement: str) -> PipelineState:
        """Initialize the pipeline and persist state.

        Raises:
            RuntimeError: If a pipeline is already running (state file exists
                          with status running/pending).
        """
        if self.state_path.exists():
            existing = self._load_state()
            if existing.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
                raise RuntimeError(
                    f"Pipeline '{existing.pipeline_name}' is already running "
                    f"(status: {existing.status.value}). Use 'reset' to clear, "
                    f"or call 'next' to continue."
                )
        self.state = PipelineState(pipeline_name=self.config.name)
        self.state.requirement = requirement
        self.state.start()
        self._save_state()
        return self.state

    def next(self) -> NextAction:
        """Determine the next node(s) to execute based on DAG state.

        Returns:
            NextAction with action=EXECUTE and rendered nodes, or
            action=DONE if pipeline is complete, or action=ERROR.
        """
        self._ensure_state()
        state = self.state

        # -- Already completed or errored --
        if state.status == PipelineStatus.COMPLETED:
            return NextAction(action=ActionType.DONE,
                              message="Pipeline already completed.")
        if state.status == PipelineStatus.ERROR:
            return NextAction(action=ActionType.ERROR,
                              message="Pipeline is in error state. Use 'reset' to restart.")

        # -- PENDING -> find start nodes --
        if state.status == PipelineStatus.PENDING:
            start_nodes = self.config.get_start_nodes()
            state.set_current_nodes([n.id for n in start_nodes])
            state.status = PipelineStatus.RUNNING
            self._save_state()
            rendered = self._render_nodes(start_nodes)
            return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                              message=f"Starting pipeline with {len(rendered)} node(s)")

        # -- RUNNING with no current nodes -> first dispatch (start was just called) --
        if state.status == PipelineStatus.RUNNING and not state.current_nodes:
            start_nodes = self.config.get_start_nodes()
            state.set_current_nodes([n.id for n in start_nodes])
            self._save_state()
            rendered = self._render_nodes(start_nodes)
            return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                              message=f"Starting pipeline with {len(rendered)} node(s)")

        # -- RUNNING: check if current nodes still in progress --
        pending = [nid for nid in state.current_nodes
                   if nid not in state.node_results]
        if pending:
            return NextAction(
                action=ActionType.ERROR,
                message=f"Cannot advance: nodes still in progress: {pending}. "
                        f"Report results for these nodes first."
            )

        # -- Remember previous current nodes before evaluating edges --
        prev_current_nodes = list(state.current_nodes)

        # -- Evaluate edges from completed current nodes --
        next_node_configs = []
        for nid in state.current_nodes:
            result = state.node_results[nid]
            next_node_configs.extend(self._evaluate_edges(nid, result))

        state.clear_current_nodes()

        # -- No more nodes -> check for terminal conditions --
        if not next_node_configs:
            # Determine why we're done by checking the previous node's verdict
            done_message = ""
            for nid in prev_current_nodes:
                if nid in state.node_results:
                    r = state.node_results[nid]
                    if r.agent_verdict == "REVIEW_FAILED":
                        state.complete()
                        self._save_state()
                        return NextAction(
                            action=ActionType.DONE,
                            message=f"Max retries ({self.config.defaults.max_retries}) exhausted. "
                                    f"Pipeline stopped after {state.round + 1} round(s)."
                        )
                    if r.agent_verdict == "REVIEW_ERROR":
                        state.complete()
                        self._save_state()
                        return NextAction(
                            action=ActionType.DONE,
                            message=f"Pipeline terminated due to error in node '{nid}'."
                        )
            state.complete()
            self._save_state()
            return NextAction(action=ActionType.DONE,
                              message=f"Pipeline completed successfully after {state.round + 1} round(s).")

        # -- Check for fix loop (re-entry to a start node) -> increment round --
        node_ids = [n.id for n in next_node_configs]
        start_node_ids = {n.id for n in self.config.get_start_nodes()}
        already_executed = [nid for nid in node_ids
                            if nid in start_node_ids and nid in state.node_results]
        if already_executed:
            # Going back to a previously-executed start node = fix round
            if state.round + 1 >= self.config.defaults.max_retries:
                state.complete()
                self._save_state()
                return NextAction(
                    action=ActionType.DONE,
                    message=f"Max retries ({self.config.defaults.max_retries}) exhausted. "
                            f"Pipeline stopped after {state.round + 1} round(s)."
                )
            state.increment_round()

        state.set_current_nodes(node_ids)
        self._save_state()
        rendered = self._render_nodes(next_node_configs)
        return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                          message=f"Execute {len(rendered)} node(s)")

    def report(self, node_id: str, status: NodeStatus, summary: str = "",
               agent_verdict: str = "") -> PipelineState:
        """Record the result of a node execution.

        Args:
            node_id: The node that completed.
            status: Execution status (success/failed/error/skipped).
            summary: Human-readable summary.
            agent_verdict: Agent's verdict (REVIEW_PASSED/REVIEW_FAILED/
                           REVIEW_ERROR), empty for non-reviewer nodes.

        Raises:
            ValueError: If node_id is not in current_nodes.
        """
        self._ensure_state()
        if node_id not in self.state.current_nodes:
            raise ValueError(
                f"Node '{node_id}' is not in current_nodes {self.state.current_nodes}. "
                f"Did you already report it?"
            )
        result = NodeResult(
            node_id=node_id,
            status=status,
            summary=summary,
            agent_verdict=agent_verdict,
        )
        self.state.record_result(result)
        self._save_state()
        return self.state

    def status(self) -> PipelineState:
        """Return the current pipeline state."""
        self._ensure_state()
        return self.state

    def reset(self) -> None:
        """Delete the state file and reset in-memory state."""
        self.state = None
        if self.state_path.exists():
            self.state_path.unlink()

    # -- Internal helpers ----------------------------------------------

    def _ensure_state(self):
        if self.state is None:
            if self.state_path.exists():
                self.state = self._load_state()
            else:
                raise RuntimeError(
                    "No pipeline state found. Call 'start' first, "
                    "or ensure a state file exists."
                )

    def _load_state(self) -> PipelineState:
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineState.from_dict(data)

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)

    def _evaluate_edges(self, node_id: str, result: NodeResult) -> list:
        """Evaluate outgoing edges from a completed node.

        Returns list of NodeConfig for the next step(s).
        """
        edges = self.config.get_outgoing_edges(node_id)
        next_nodes = []

        for edge in edges:
            if edge.to == "DONE":
                continue  # Terminal edges don't produce next nodes

            if edge.trigger == TriggerType.ON_SUCCESS:
                if result.status == NodeStatus.SUCCESS:
                    next_nodes.append(self.config.get_node(edge.to))

            elif edge.trigger == TriggerType.ON_CONDITION:
                if edge.condition is None:
                    continue
                if self._check_condition(edge.condition.status, result):
                    next_nodes.append(self.config.get_node(edge.to))

        return next_nodes

    def _check_condition(self, condition_status: str, result: NodeResult) -> bool:
        """Check if a condition edge matches the node result."""
        if condition_status == "REVIEW_PASSED":
            return result.agent_verdict == "REVIEW_PASSED"
        if condition_status == "REVIEW_FAILED":
            return (result.agent_verdict == "REVIEW_FAILED"
                    and self.state.round + 1 < self.config.defaults.max_retries)
        if condition_status == "REVIEW_ERROR":
            return result.agent_verdict == "REVIEW_ERROR"
        return False

    def _render_nodes(self, node_configs: list) -> list[NodeToExecute]:
        """Render prompt templates for each node into executable form."""
        rendered = []
        for node in node_configs:
            prompt = self._render_prompt(node)
            phase = self._determine_phase(node)
            timeout = node.timeout or self.config.defaults.timeout
            rendered.append(NodeToExecute(
                node_id=node.id,
                agent_type=node.agent,
                prompt=prompt,
                timeout=timeout,
                round=self.state.round,
                phase=phase,
            ))
        return rendered

    def _render_prompt(self, node) -> str:
        """Render a single node's prompt_template with current state variables."""
        review_context = ""
        if self.state.round > 0 and node.id == "coder":
            review_context = (
                "\n\n⚠️ 这是第 {round}/{max_retries} 轮修复。\n\n"
                "请先读取以下文件，了解上一轮审查发现的问题：\n"
                "1. review-output/pre-check-result.json — 程序预检结果\n"
                "2. review-output/review-result.json — AI 语义检查结果（如存在）\n"
                "3. review-output/pre-check-report.md — 预检报告\n\n"
                "然后逐个修复所有阻断级问题。\n\n"
                "修复原则：\n"
                "- 只修改有问题的文件和行\n"
                "- 修复后必须符合 agents/coder/ 下的所有规范\n"
                "- 不确定的改动，加注释说明原因"
            ).format(round=self.state.round,
                     max_retries=self.config.defaults.max_retries)

        variables = {
            "requirement": self.state.requirement,
            "review_context": review_context,
            "round": str(self.state.round),
            "max_retries": str(self.config.defaults.max_retries),
        }

        try:
            return node.prompt_template.format(**variables)
        except KeyError as e:
            import sys
            print(f"Warning: unknown variable {e} in prompt_template for node '{node.id}'",
                  file=sys.stderr)
            return node.prompt_template

    def _determine_phase(self, node) -> str:
        """Determine the execution phase label for a node."""
        if node.id == "coder":
            if self.state.round > 0:
                return "fix"
            return "code_generation"
        if node.id == "reviewer":
            return "review"
        return node.id
