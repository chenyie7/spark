"""DAG 状态机 — 流水线调度器的核心引擎。

PipelineEngine 管理流水线执行的完整生命周期：
  start  → 从 PipelineConfig 初始化状态
  next   → 评估 DAG 边，确定下一个要执行的节点
  report → 记录节点执行结果，更新状态
  status → 返回当前状态摘要
  reset  → 清除状态文件

核心设计原则：引擎不执行 Agent。它只做路由决策。
Claude Code Agent 通过 Agent 工具完成实际的 Agent 执行。
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from pipeline_engine.models import (
    PipelineConfig, PipelineState, NodeResult, NextAction, NodeToExecute,
    PipelineStatus, NodeStatus, ActionType, TriggerType,
)


def load_pipeline_config(pipeline_path: Path) -> "PipelineConfig":
    """便捷函数：从 YAML 路径加载配置，内部调用 config.load_pipeline。"""
    from pipeline_engine.config import load_pipeline
    return load_pipeline(pipeline_path)


class PipelineEngine:
    """DAG 状态机，负责流水线执行的路由决策。

    Args:
        config: 经过完整校验的 PipelineConfig。
        state_path: 持久化状态 JSON 文件的路径。
    """

    def __init__(self, config: PipelineConfig, state_path: Path):
        self.config = config
        self.state_path = Path(state_path)
        self.state: PipelineState | None = None

    # ── 公开 API ────────────────────────────────────────────────────

    def start(self, requirement: str) -> PipelineState:
        """初始化流水线并持久化状态。

        Raises:
            RuntimeError: 如果已有流水线在运行中（状态文件存在且状态为
                          running 或 pending）。
        """
        if self.state_path.exists():
            existing = self._load_state()
            if existing.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
                raise RuntimeError(
                    f"流水线 '{existing.pipeline_name}' 已在运行中 "
                    f"（状态: {existing.status.value}）。使用 'reset' 清除，"
                    f"或调用 'next' 继续。"
                )
        self.state = PipelineState(pipeline_name=self.config.name)
        self.state.requirement = requirement
        self.state.start()
        self._save_state()
        return self.state

    def next(self) -> NextAction:
        """根据 DAG 状态确定下一个要执行的节点。

        Returns:
            NextAction，其中 action=EXECUTE 表示有待执行的已渲染节点，
            action=DONE 表示流水线已完成，action=ERROR 表示出错。
        """
        self._ensure_state()
        state = self.state

        # ── 已完成或已出错 ──
        if state.status == PipelineStatus.COMPLETED:
            return NextAction(action=ActionType.DONE,
                              message="流水线已完成。")
        if state.status == PipelineStatus.ERROR:
            return NextAction(action=ActionType.ERROR,
                              message="流水线处于错误状态。使用 'reset' 重新开始。")

        # ── PENDING → 查找起始节点 ──
        if state.status == PipelineStatus.PENDING:
            start_nodes = self.config.get_start_nodes()
            state.set_current_nodes([n.id for n in start_nodes])
            state.status = PipelineStatus.RUNNING
            self._save_state()
            rendered = self._render_nodes(start_nodes)
            return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                              message=f"启动流水线，共 {len(rendered)} 个节点")

        # ── RUNNING 且无当前节点 → 首次派发（start 刚被调用） ──
        if state.status == PipelineStatus.RUNNING and not state.current_nodes:
            start_nodes = self.config.get_start_nodes()
            state.set_current_nodes([n.id for n in start_nodes])
            self._save_state()
            rendered = self._render_nodes(start_nodes)
            return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                              message=f"启动流水线，共 {len(rendered)} 个节点")

        # ── RUNNING：检查当前节点是否仍在执行中 ──
        pending = [nid for nid in state.current_nodes
                   if nid not in state.node_results]
        if pending:
            return NextAction(
                action=ActionType.ERROR,
                message=f"无法推进：以下节点仍在执行中: {pending}。"
                        f"请先上报这些节点的结果。"
            )

        # ── 保存当前节点列表以备后续判断 ──
        prev_current_nodes = list(state.current_nodes)

        # ── 评估已完成节点的出边 ──
        next_node_configs = []
        for nid in state.current_nodes:
            result = state.node_results[nid]
            next_node_configs.extend(self._evaluate_edges(nid, result))

        state.clear_current_nodes()

        # ── 无后续节点 → 检查终止条件 ──
        if not next_node_configs:
            for nid in prev_current_nodes:
                if nid in state.node_results:
                    r = state.node_results[nid]
                    if r.agent_verdict == "REVIEW_FAILED":
                        state.complete()
                        self._save_state()
                        return NextAction(
                            action=ActionType.DONE,
                            message=f"已达最大重试次数（{self.config.defaults.max_retries}）。"
                                    f"流水线在 {state.round + 1} 轮后停止。"
                        )
                    if r.agent_verdict == "REVIEW_ERROR":
                        state.complete()
                        self._save_state()
                        return NextAction(
                            action=ActionType.DONE,
                            message=f"流水线因节点 '{nid}' 的错误而终止。"
                        )
                    # 非 reviewer 节点执行失败（如 coder 崩溃）：不谎报成功
                    if r.status != NodeStatus.SUCCESS:
                        state.error()
                        self._save_state()
                        return NextAction(
                            action=ActionType.ERROR,
                            message=f"流水线失败：节点 '{nid}' 以状态 "
                                    f"'{r.status.value}' 终止。"
                        )
            state.complete()
            self._save_state()
            return NextAction(action=ActionType.DONE,
                              message=f"流水线成功完成，共 {state.round + 1} 轮。")

        # ── 检查是否为修复循环（重新进入起始节点）→ 轮次 +1 ──
        node_ids = [n.id for n in next_node_configs]
        start_node_ids = {n.id for n in self.config.get_start_nodes()}
        already_executed = [nid for nid in node_ids
                            if nid in start_node_ids and nid in state.node_results]
        if already_executed:
            # 回到已执行过的起始节点 = 修复轮
            if state.round + 1 >= self.config.defaults.max_retries:
                state.complete()
                self._save_state()
                return NextAction(
                    action=ActionType.DONE,
                    message=f"已达最大重试次数（{self.config.defaults.max_retries}）。"
                            f"流水线在 {state.round + 1} 轮后停止。"
                )
            state.increment_round()

        state.set_current_nodes(node_ids)
        self._save_state()
        rendered = self._render_nodes(next_node_configs)
        return NextAction(action=ActionType.EXECUTE, nodes=rendered,
                          message=f"执行 {len(rendered)} 个节点")

    def report(self, node_id: str, status: NodeStatus, summary: str = "",
               agent_verdict: str = "") -> PipelineState:
        """记录节点的执行结果。

        Args:
            node_id: 已完成的节点 ID。
            status: 执行状态（success/failed/error/skipped）。
            summary: 人类可读的摘要。
            agent_verdict: Agent 的判定结果（REVIEW_PASSED/REVIEW_FAILED/
                           REVIEW_ERROR），非 reviewer 节点留空。

        Raises:
            ValueError: 如果 node_id 不在 current_nodes 中或同轮重复上报。
        """
        self._ensure_state()
        if node_id not in self.state.current_nodes:
            raise ValueError(
                f"节点 '{node_id}' 不在 current_nodes {self.state.current_nodes} 中。"
                f"是否已经上报过了？"
            )
        if node_id in self.state.node_results:
            # 仅阻止同轮内的重复上报（跨轮允许——如 coder 在修复轮 1 时
            # 也被轮 0 上报过）
            already_in_round = any(
                entry["node"] == node_id and entry["round"] == self.state.round
                for entry in self.state.history
            )
            if already_in_round:
                prev = self.state.node_results[node_id]
                raise ValueError(
                    f"节点 '{node_id}' 在第 {self.state.round} 轮已上报过 "
                    f"（状态={prev.status.value}）。不允许重复上报。"
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
        """返回当前流水线状态。"""
        self._ensure_state()
        return self.state

    def reset(self) -> None:
        """删除状态文件并重置内存状态。"""
        self.state = None
        if self.state_path.exists():
            self.state_path.unlink()

    # ── 内部辅助方法 ────────────────────────────────────────────────

    def _ensure_state(self):
        """确保 state 已加载；如内存中为空则从磁盘恢复。"""
        if self.state is None:
            if self.state_path.exists():
                self.state = self._load_state()
            else:
                raise RuntimeError(
                    "未找到流水线状态。请先调用 'start'，"
                    "或确保状态文件存在。"
                )

    def _load_state(self) -> PipelineState:
        """从磁盘加载持久化状态。"""
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineState.from_dict(data)

    def _save_state(self):
        """将当前状态持久化到磁盘。"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)

    def _evaluate_edges(self, node_id: str, result: NodeResult) -> list:
        """评估已完成节点的出边，返回下一步要执行的 NodeConfig 列表。"""
        edges = self.config.get_outgoing_edges(node_id)
        next_nodes = []

        for edge in edges:
            if edge.to == "DONE":
                continue  # 终止边不产生后续节点

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
        """检查条件边是否匹配节点结果。"""
        if condition_status == "REVIEW_PASSED":
            return result.agent_verdict == "REVIEW_PASSED"
        if condition_status == "REVIEW_FAILED":
            return (result.agent_verdict == "REVIEW_FAILED"
                    and self.state.round + 1 < self.config.defaults.max_retries)
        if condition_status == "REVIEW_ERROR":
            return result.agent_verdict == "REVIEW_ERROR"
        return False

    def _render_nodes(self, node_configs: list) -> list[NodeToExecute]:
        """将节点配置渲染为可执行的 NodeToExecute 列表。"""
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
        """渲染单个节点的 prompt_template，替换其中的状态变量。"""
        review_context = ""
        if self.state.round > 0 and node.id == "coder":
            review_context = (
                "\n\n⚠️ 这是第 {round}/{max_retries} 轮修复。\n\n"
                "请先读取以下文件，了解上一轮审查发现的问题：\n"
                "1. review-output/{run_id}/pre-check-result.json — 程序预检结果\n"
                "2. review-output/{run_id}/review-result.json — AI 语义检查结果（如存在）\n"
                "3. review-output/{run_id}/pre-check-report.md — 预检报告\n\n"
                "然后逐个修复所有阻断级问题。\n\n"
                "修复原则：\n"
                "- 只修改有问题的文件和行\n"
                "- 修复后必须符合 agents/coder/ 下的所有规范\n"
                "- 不确定的改动，加注释说明原因"
            ).format(round=self.state.round,
                     max_retries=self.config.defaults.max_retries,
                     run_id=self.state.run_id)

        variables = {
            "requirement": self.state.requirement,
            "review_context": review_context,
            "round": str(self.state.round),
            "max_retries": str(self.config.defaults.max_retries),
            "run_id": self.state.run_id,
            "target_dir": self.state.target_dir,
        }

        try:
            return node.prompt_template.format(**variables)
        except KeyError:
            # 对存在未知变量的模板做部分替换（如 {coder_output} 来自上游节点输出）
            import re
            result = node.prompt_template
            for key, value in variables.items():
                result = result.replace("{" + key + "}", str(value))
            import sys
            print(f"警告: 节点 '{node.id}' 的 prompt_template 中存在引擎未识别的变量",
                  file=sys.stderr)
            return result

    def _determine_phase(self, node) -> str:
        """确定节点的执行阶段标签。"""
        if node.id == "coder":
            if self.state.round > 0:
                return "fix"
            return "code_generation"
        if node.id == "reviewer":
            return "review"
        return node.id
