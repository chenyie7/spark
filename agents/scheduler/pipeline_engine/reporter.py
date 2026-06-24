"""State visualization — human-readable pipeline status output.

Provides functions to format PipelineState into readable summaries
for terminal display and progress reporting.
"""

from pipeline_engine.models import PipelineState, PipelineStatus, NodeStatus


def format_status_line(state: PipelineState) -> str:
    """Return a single-line status summary.

    Example: "[◉ RUNNING] coder-reviewer-pipeline — Round 1 — current: reviewer"
    """
    icons = {
        PipelineStatus.PENDING: "○",
        PipelineStatus.RUNNING: "◉",
        PipelineStatus.COMPLETED: "●",
        PipelineStatus.ERROR: "✕",
    }
    icon = icons.get(state.status, "?")
    name = state.pipeline_name
    round_info = f"Round {state.round}"
    current = ", ".join(state.current_nodes) if state.current_nodes else "—"
    return f"[{icon} {state.status.value.upper()}] {name} — {round_info} — current: {current}"


def format_history_table(state: PipelineState) -> str:
    """Return a Markdown table of the execution history."""
    if not state.history:
        return "*No execution history yet.*"

    lines = [
        "| Round | Node | Status | Verdict | Summary |",
        "|-------|------|--------|---------|----------|",
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
    """Return a multi-line status block suitable for terminal display."""
    parts = [
        format_status_line(state),
        "",
        f"Started: {state.started_at or 'N/A'}",
        f"Updated: {state.updated_at or 'N/A'}",
        f"Requirement: {state.requirement or 'N/A'}",
        "",
        "## Execution History",
        format_history_table(state),
    ]
    return "\n".join(parts)
