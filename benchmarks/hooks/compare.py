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


def _compute_baselines(runs: list[dict]) -> dict:
    """从所有历史运行计算基线（均值 + 标准差）。"""
    import statistics

    p0_values = []
    token_values = []
    rounds_values = []
    cache_values = []

    for r in runs:
        summary = r.get("summary", {})
        conv = r.get("convergence", {})
        series = conv.get("series", [])

        if series:
            p0_values.append(series[0].get("P0", 0))

        token_values.append(summary.get("total_tokens", 0))
        rounds_values.append(len(r.get("rounds", [])))

        ce = summary.get("cache_efficiency", {})
        cache_values.append(ce.get("cache_hit_ratio", 0))

    def safe_stats(values):
        if len(values) < 2:
            return sum(values) / len(values) if values else 0, 0
        return statistics.mean(values), statistics.stdev(values)

    avg_p0, p0_std = safe_stats(p0_values)
    avg_tokens, tokens_std = safe_stats(token_values)
    avg_rounds, rounds_std = safe_stats(rounds_values)
    avg_cache, cache_std = safe_stats(cache_values)

    return {
        "avg_p0": round(avg_p0, 1), "p0_std": round(p0_std, 1),
        "avg_tokens": int(avg_tokens), "tokens_std": int(tokens_std),
        "avg_rounds": round(avg_rounds, 1), "rounds_std": round(rounds_std, 1),
        "avg_cache_hit": round(avg_cache, 3), "cache_std": round(cache_std, 3),
        "sample_count": len(runs),
    }


def _detect_anomalies(runs: list[dict], baselines: dict) -> list[dict]:
    """检测当前运行是否偏离基线超过 2σ。"""
    alerts_per_run = []

    for r in runs:
        meta = r.get("meta", {})
        summary = r.get("summary", {})
        conv = r.get("convergence", {})
        ce = summary.get("cache_efficiency", {})
        series = conv.get("series", [])

        alerts = []

        # Token 检查
        if baselines.get("tokens_std", 0) > 0:
            tokens = summary.get("total_tokens", 0)
            dev = (tokens - baselines["avg_tokens"]) / baselines["tokens_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "tokens", "current": tokens,
                    "baseline": baselines["avg_tokens"],
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })

        # P0 检查
        if baselines.get("p0_std", 0) > 0 and series:
            p0 = series[0].get("P0", 0)
            dev = (p0 - baselines["avg_p0"]) / baselines["p0_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "p0", "current": p0,
                    "baseline": round(baselines["avg_p0"], 1),
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })

        # 收敛轮次检查
        if baselines.get("rounds_std", 0) > 0:
            rnd = len(r.get("rounds", []))
            dev = (rnd - baselines["avg_rounds"]) / baselines["rounds_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "rounds", "current": rnd,
                    "baseline": baselines["avg_rounds"],
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })

        alerts_per_run.append({
            "run_id": meta.get("run_id", ""),
            "alerts": alerts,
        })

    return alerts_per_run


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

    # ── 基线计算 ──
    baselines = _compute_baselines(runs)
    anomalies = _detect_anomalies(runs, baselines)

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
        # 检查是否有异常
        run_anomaly = next((a for a in anomalies if a["run_id"] == meta["run_id"]), None)
        flag = ""
        if run_anomaly and run_anomaly["alerts"]:
            has_critical = any(a["severity"] == "critical" for a in run_anomaly["alerts"])
            flag = " 🔴" if has_critical else " ⚠️"

        lines.append(
            f"| `{meta['run_id']}`{flag} | {meta['timestamp_start'][:10]} "
            f"| {meta.get('requirement_slug', '')[:20]} "
            f"| {rounds_count} | {converged} "
            f"| {summary['total_duration_ms'] / 1000:.0f} "
            f"| {summary['total_tokens']:,} |"
        )
    lines.append("")

    # ── 基线概览 ──
    if baselines.get("sample_count", 0) >= 2:
        lines.append("## 基线概览")
        lines.append("")
        lines.append(f"**样本数**: {baselines['sample_count']} 次运行")
        lines.append("")
        lines.append("| 指标 | 均值 | 标准差 |")
        lines.append("|------|------|--------|")
        lines.append(f"| 起始 P0 | {baselines['avg_p0']} | ±{baselines['p0_std']} |")
        lines.append(f"| 总 Token | {baselines['avg_tokens']:,} | ±{baselines['tokens_std']:,} |")
        lines.append(f"| 收敛轮次 | {baselines['avg_rounds']} | ±{baselines['rounds_std']} |")
        lines.append(f"| 缓存命中率 | {baselines['avg_cache_hit']*100:.1f}% | ±{baselines['cache_std']*100:.1f}% |")
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

    # ── 异常告警 ──
    any_alerts = any(a["alerts"] for a in anomalies)
    if any_alerts:
        lines.append("## 异常告警")
        lines.append("")
        lines.append("| Run ID | 指标 | 当前值 | 基线均值 | 偏离(σ) | 严重度 |")
        lines.append("|--------|------|--------|---------|---------|--------|")
        for run_anomaly in anomalies:
            for alert in run_anomaly["alerts"]:
                severity_icon = "🔴" if alert["severity"] == "critical" else "⚠️"
                lines.append(
                    f"| `{run_anomaly['run_id']}` | {alert['metric']} "
                    f"| {alert['current']:,} | {alert['baseline']} "
                    f"| {alert['deviation']}σ | {severity_icon} {alert['severity']} |"
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
