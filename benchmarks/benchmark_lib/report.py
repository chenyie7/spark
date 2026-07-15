"""Markdown 报告渲染模块。

从 benchmark.json 数据渲染人类可读的 Markdown 报告。
纯数据驱动，不访问文件系统。
"""


def render_report(data: dict) -> str:
    """将 benchmark JSON 渲染为 Markdown 报告。

    Args:
        data: 符合 schema 2.0 的 benchmark JSON 对象

    Returns:
        Markdown 格式的报告字符串
    """
    meta = data["meta"]
    rounds = data["rounds"]
    conv = data["convergence"]
    summary = data["summary"]

    lines = []
    lines.append("# 流水线性能报告")
    lines.append("")
    lines.append(f"**Run ID**: `{meta['run_id']}`")
    lines.append(f"**时间**: {meta['timestamp_start']} ~ {meta['timestamp_end']}")
    lines.append(f"**Git Commit**: `{meta['git_commit']}`")
    lines.append(f"**配置**: max_retries={meta.get('max_retries', '-')}, strategy={meta.get('block_strategy', '-')}")
    lines.append("")

    # ── 收敛曲线 ──
    lines.append("## 收敛曲线")
    lines.append("")
    lines.append(f"**终止原因**: {conv['termination_reason']}")
    if conv["rounds_to_converge"] is not None:
        lines.append(f"**收敛于第 {conv['rounds_to_converge']} 轮**")
    lines.append("")

    if conv["series"]:
        lines.append("| Round | P0 | P1 | P2 | AI_FAIL |")
        lines.append("|-------|----|----|----|---------|")
        for s in conv["series"]:
            ai = s.get("AI_FAIL", -1)
            ai_str = str(ai) if ai >= 0 else "-"
            lines.append(f"| {s['round']} | {s['P0']} | {s['P1']} | {s['P2']} | {ai_str} |")
        lines.append("")

    # ── 各轮次详情 ──
    lines.append("## 各轮次详情")
    lines.append("")
    lines.append("| Round | Agent | Phase | Duration(s) | Tokens | Tools | Cache Hit | Result |")
    lines.append("|-------|-------|-------|-------------|--------|-------|-----------|--------|")
    for r in rounds:
        rn = r["round"]
        for role_key in ("coder", "reviewer"):
            entry = r.get(role_key)
            if entry is None:
                continue
            dur_s = round(entry["duration_ms"] / 1000, 0)
            tok = entry["total_tokens"]
            tools = entry["total_tool_uses"]
            usage = entry.get("usage", {})
            cache_hit = ""
            inp = usage.get("input_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0)
            total = cr + inp
            if total > 0:
                cache_hit = f"{round(cr / total * 100, 0)}%"
            result = entry.get("result", "-") if role_key == "reviewer" else "-"
            lines.append(
                f"| {rn} | {role_key} | {entry['phase']} | {dur_s} | {tok} | {tools} | {cache_hit} | {result} |"
            )
    lines.append("")

    # ── 汇总 ──
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- **总耗时**: {summary['total_duration_ms'] / 1000:.0f}s")
    lines.append(f"- **总 Token**: {summary['total_tokens']:,}")
    lines.append(f"- **总 Tool Uses**: {summary['total_tool_uses']}")
    lines.append("")
    lines.append("| 维度 | Coder | Reviewer |")
    lines.append("|------|-------|----------|")
    s_coder = summary["coder"]
    s_reviewer = summary["reviewer"]
    lines.append(f"| Tokens | {s_coder['total_tokens']:,} | {s_reviewer['total_tokens']:,} |")
    lines.append(f"| Duration(s) | {s_coder['total_duration_ms'] / 1000:.0f} | {s_reviewer['total_duration_ms'] / 1000:.0f} |")
    lines.append(f"| Avg Tokens/Call | {s_coder['avg_tokens_per_call']:,} | {s_reviewer['avg_tokens_per_call']:,} |")
    lines.append("")

    # ── 缓存与收敛 ──
    ce = summary["cache_efficiency"]
    lines.append(f"- **缓存命中率**: {ce['cache_hit_ratio'] * 100:.1f}%  "
                 f"(cache_read={ce['total_cache_read_tokens']:,}, input={ce['total_input_tokens']:,})")
    lines.append(f"- **是否收敛**: {'✅' if summary['converged'] else '❌'}")

    # ── 模型使用 ──
    models = summary.get("models_used", {})
    if models:
        lines.append("")
        lines.append("## 模型使用")
        lines.append("")
        lines.append("| Model | 调用次数 |")
        lines.append("|-------|---------|")
        for model, count in models.items():
            lines.append(f"| {model} | {count} |")
        lines.append("")

    return "\n".join(lines) + "\n"
