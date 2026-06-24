"""状态可视化 — 将流水线状态格式化为人类可读的输出。

提供将 PipelineState 格式化为可读摘要的函数，
用于终端显示和进度报告。
"""

from pipeline_engine.models import PipelineState, PipelineStatus, NodeStatus


def format_status_line(state: PipelineState) -> str:
    """返回单行状态摘要。

    示例: "[◉ RUNNING] coder-reviewer-pipeline — Round 1 — current: reviewer"
    """
    icons = {
        PipelineStatus.PENDING: "○",
        PipelineStatus.RUNNING: "◉",
        PipelineStatus.COMPLETED: "●",
        PipelineStatus.ERROR: "✕",
    }
    icon = icons.get(state.status, "?")
    name = state.pipeline_name
    round_info = f"第 {state.round} 轮"
    current = ", ".join(state.current_nodes) if state.current_nodes else "—"
    return f"[{icon} {state.status.value.upper()}] {name} — {round_info} — 当前: {current}"


def format_history_table(state: PipelineState) -> str:
    """返回执行历史的 Markdown 表格。"""
    if not state.history:
        return "*暂无执行历史。*"

    lines = [
        "| 轮次 | 节点 | 状态 | 判定 | 摘要 |",
        "|------|------|------|------|------|",
    ]
    for entry in state.history:
        verdict = entry.get("verdict", "") or "—"
        summary = entry.get("summary", "") or "—"
        lines.append(
            f"| {entry['round']} | {entry['node']} | {entry['status']} "
            f"| {verdict} | {summary} |"
        )
    return "\n".join(lines)


def format_full_status(state: PipelineState) -> str:
    """返回适合终端显示的多行状态块。"""
    parts = [
        format_status_line(state),
        "",
        f"开始时间: {state.started_at or 'N/A'}",
        f"更新时间: {state.updated_at or 'N/A'}",
        f"需求: {state.requirement or 'N/A'}",
        "",
        "## 执行历史",
        format_history_table(state),
    ]
    return "\n".join(parts)
