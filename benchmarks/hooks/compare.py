#!/usr/bin/env python3
"""跨运行性能对比工具。

从 benchmarks/ 目录下所有 run-*.json 文件生成横向对比 Markdown 报告。
用法: python3 compare.py [benchmarks_dir] [-o output.md]
"""

import json
import os
import sys
from pathlib import Path


def load_all_benchmarks(bench_dir: str) -> list[dict]:
    """加载所有 benchmark JSON 文件，按文件名排序（即按时间排序）。"""
    results = []
    for fname in sorted(os.listdir(bench_dir)):
        if fname.endswith(".json") and fname.startswith("run-"):
            fpath = os.path.join(bench_dir, fname)
            try:
                with open(fpath, "r") as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return results


def render_comparison_md(runs: list[dict]) -> str:
    """从多份 benchmark JSON 渲染横向对比 Markdown 报告。"""
    if not runs:
        return "# 跨运行对比报告\n\n*暂无运行数据。*\n"

    lines = [
        "# 跨运行对比报告",
        "",
        f"**对比运行数**: {len(runs)}",
        "",
    ]

    # ── 运行概览表 ──
    lines.append("## 运行概览")
    lines.append("")
    lines.append("| Run ID | 时间 | 需求 | 轮次 | 收敛 | 总耗时(s) | 总 Token |")
    lines.append("|--------|------|------|------|------|-----------|----------|")
    for r in runs:
        meta = r["meta"]
        summary = r["summary"]
        converged = "✅" if summary.get("converged") else "❌"
        rounds_count = len(r.get("rounds", []))
        lines.append(
            f"| `{meta['run_id']}` | {meta['timestamp_start'][:10]} "
            f"| {meta.get('requirement_slug', '')[:20]} "
            f"| {rounds_count} | {converged} "
            f"| {summary['total_duration_ms'] / 1000:.0f} "
            f"| {summary['total_tokens']:,} |"
        )
    lines.append("")

    # ── 趋势：Token 消耗 ──
    lines.append("## Token 消耗趋势")
    lines.append("")
    lines.append("| Run ID | 总 Token | Coder | Reviewer | 缓存命中率 |")
    lines.append("|--------|----------|-------|----------|-----------|")
    for r in runs:
        meta = r["meta"]
        s = r["summary"]
        ce = s.get("cache_efficiency", {})
        ch = ce.get("cache_hit_ratio", 0) * 100
        lines.append(
            f"| `{meta['run_id']}` | {s['total_tokens']:,} "
            f"| {s['coder']['total_tokens']:,} "
            f"| {s['reviewer']['total_tokens']:,} "
            f"| {ch:.1f}% |"
        )
    lines.append("")

    # ── 趋势：收敛性 ──
    lines.append("## 收敛趋势")
    lines.append("")
    conv_runs = [r for r in runs if r["convergence"].get("series")]
    if conv_runs:
        lines.append("| Run ID | 起始 P0 | 最终 P0 | 收敛轮次 | 终止原因 |")
        lines.append("|--------|---------|---------|----------|----------|")
        for r in runs:
            meta = r["meta"]
            conv = r["convergence"]
            series = conv.get("series", [])
            if series:
                start_p0 = series[0].get("P0", "-")
                end_p0 = series[-1].get("P0", "-")
                lines.append(
                    f"| `{meta['run_id']}` | {start_p0} | {end_p0} "
                    f"| {conv.get('rounds_to_converge', '-')} "
                    f"| {conv.get('termination_reason', '-')} |"
                )
            else:
                lines.append(
                    f"| `{meta['run_id']}` | - | - | - "
                    f"| {conv.get('termination_reason', '-')} |"
                )
        lines.append("")

    # ── 修复效率对比 ──
    lines.append("## 修复效率对比")
    lines.append("")
    lines.append("| Run ID | Tokens/P0-Fixed | P0 减少率 |")
    lines.append("|--------|----------------|-----------|")
    for r in runs:
        meta = r["meta"]
        fe = r.get("fix_efficiency", {})
        tpp = fe.get("tokens_per_p0_fixed")
        prr = fe.get("p0_reduction_rate_pct")
        tpp_str = f"{tpp:,}" if tpp is not None else "-"
        prr_str = f"{prr}%" if prr is not None else "-"
        lines.append(
            f"| `{meta['run_id']}` | {tpp_str} | {prr_str} |"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    bench_dir = sys.argv[1] if len(sys.argv) > 1 else "benchmarks"
    output = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "-o" else None

    if not os.path.isdir(bench_dir):
        print(f"Error: benchmarks directory not found: {bench_dir}", file=sys.stderr)
        sys.exit(1)

    data = load_all_benchmarks(bench_dir)

    if output:
        md = render_comparison_md(data)
        with open(output, "w") as f:
            f.write(md)
        print(f"Comparison report saved: {output}", file=sys.stderr)
    else:
        print(render_comparison_md(data))
