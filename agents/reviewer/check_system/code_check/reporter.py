"""Report renderer — merges quality.json (fuck-u-code) and findings.json (AI review)
into a single Markdown report with four sections."""

from pathlib import Path
from typing import Any


def _file_short(full_path: str) -> str:
    """Return the package-relative path (everything after src/main/java/),
    falling back to the bare filename if the marker is not found."""
    marker = "src/main/java/"
    idx = full_path.find(marker)
    if idx != -1:
        return full_path[idx + len(marker):]
    return Path(full_path).name


def render(quality: dict | None, findings: dict) -> str:
    """Merge quality and findings into a complete Markdown report.

    Args:
        quality: Raw quality.json from fuck-u-code (can be None if analysis failed).
        findings: Raw findings.json from the AI unified review.

    Returns:
        Complete Markdown string with four sections.
    """
    sections: list[str] = []

    # -- Header --
    sections.append(_render_header(quality, findings))

    # -- Section 1: Quality overview (from fuck-u-code) --
    if quality:
        sections.append(_render_quality_overview(quality))

    # -- Section 2: Spec compliance (from findings.spec_violations) --
    sections.append(_render_spec_compliance(findings.get("spec_violations", [])))

    # -- Section 3: Quality issues (from findings.quality_issues) --
    sections.append(_render_quality_issues(findings.get("quality_issues", [])))

    # -- Section 4: Summary table --
    sections.append(_render_summary(quality, findings))

    # -- Conclusion --
    sections.append(_render_conclusion(findings))

    return "\n\n".join(sections)


# ── Header ──────────────────────────────────────────────────────

def _render_header(quality: dict | None, findings: dict) -> str:
    status = findings.get("review_status", "UNKNOWN")
    icon = "✅" if status == "PASSED" else ("❌" if status == "FAILED" else "⚠️")

    lines = [
        "# 代码审查报告",
        "",
        f"**状态**: {icon} {status}",
    ]

    if quality:
        scan_path = quality.get("scan_path", "-")
        file_count = quality.get("file_count", 0)
        overall = quality.get("overall_score", "-")
        lines.append(f"**扫描路径**: {scan_path}")
        lines.append(f"**文件数量**: {file_count} 个")
        lines.append(f"**质量评分**: {overall}/100")

    return "\n".join(lines)


# ── Section 1: Quality Overview ─────────────────────────────────

def _render_quality_overview(quality: dict) -> str:
    lines = ["## 静态质量概览", ""]

    overall = quality.get("overall_score", "-")
    lines.append(f"**总体评分**: {overall}/100")
    lines.append("")

    # Metrics table
    metrics = quality.get("metrics", {})
    if metrics:
        lines.append("| 维度 | 得分 |")
        lines.append("|------|------|")
        for dim, score in metrics.items():
            lines.append(f"| {dim} | {score} |")
        lines.append("")

    # Worst files
    worst = quality.get("worst_files", [])
    if worst:
        lines.append("### 最差文件 Top 10")
        lines.append("")
        lines.append("| 文件 | 评分 | Shit-Gas |")
        lines.append("|------|------|------|")
        for w in worst[:10]:
            name = _file_short(w.get("file", ""))
            score = w.get("score", "-")
            sgi = w.get("shit_gas_index", "-")
            lines.append(f"| {name} | {score} | {sgi} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 2: Spec Compliance ──────────────────────────────────

def _render_spec_compliance(violations: list[dict]) -> str:
    lines = ["## 规范合规检查", ""]

    if not violations:
        lines.append("✅ 所有规范合规检查通过，未发现违规。")
        return "\n".join(lines)

    # Group by level
    by_level: dict[str, list[dict]] = {"P0": [], "P1": [], "P2": []}
    for v in violations:
        level = v.get("level", "P2")
        by_level.setdefault(level, []).append(v)

    level_labels = {"P0": "🔴 P0 (阻断级)", "P1": "🟡 P1", "P2": "🟢 P2"}
    for level in ("P0", "P1", "P2"):
        items = by_level.get(level, [])
        if not items:
            lines.append(f"### {level_labels[level]} (0项)")
            lines.append("_ _")
            lines.append("")
            continue

        lines.append(f"### {level_labels[level]} ({len(items)}项)")
        lines.append("")
        lines.append("| 文件 | 行号 | 方法 | 规则 | 问题 | 建议 |")
        lines.append("|------|------|------|------|------|------|")
        for v in items:
            fname = _file_short(v.get("file", "-"))
            line = v.get("line", 0)
            method = v.get("method", "-")
            rule = v.get("rule_id", "-")
            desc = v.get("description", "")
            sug = v.get("suggestion", "-")
            lines.append(f"| {fname} | {line} | {method} | {rule} | {desc} | {sug} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 3: Quality Issues ───────────────────────────────────

def _render_quality_issues(issues: list[dict]) -> str:
    lines = ["## 代码深度问题", ""]

    if not issues:
        lines.append("✅ 未发现深度质量问题。")
        return "\n".join(lines)

    # Group by severity
    by_sev: dict[str, list[dict]] = {"high": [], "medium": [], "low": []}
    for q in issues:
        sev = q.get("severity", "low")
        by_sev.setdefault(sev, []).append(q)

    sev_labels = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}
    for sev in ("high", "medium", "low"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        lines.append(f"### {sev_labels[sev]} ({len(items)}项)")
        lines.append("")
        lines.append("| 文件 | 行号 | 维度 | 详情 | 建议 |")
        lines.append("|------|------|------|------|------|")
        for q in items:
            fname = _file_short(q.get("file", "-"))
            line = q.get("line", 0)
            dim = q.get("dimension", "-")
            detail = q.get("detail", "")
            sug = q.get("suggestion", "-")
            lines.append(f"| {fname} | {line} | {dim} | {detail} | {sug} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 4: Summary ──────────────────────────────────────────

def _render_summary(quality: dict | None, findings: dict) -> str:
    lines = ["## 汇总", ""]

    violations = findings.get("spec_violations", [])
    issues = findings.get("quality_issues", [])

    p0 = sum(1 for v in violations if v.get("level") == "P0")
    p1 = sum(1 for v in violations if v.get("level") == "P1")
    p2 = sum(1 for v in violations if v.get("level") == "P2")
    q_high = sum(1 for q in issues if q.get("severity") == "high")
    q_med = sum(1 for q in issues if q.get("severity") == "medium")
    q_low = sum(1 for q in issues if q.get("severity") == "low")

    lines.append("| 来源 | P0 | P1 | P2 | 高 | 中 | 低 |")
    lines.append("|------|----|----|----|----|----|----|")
    lines.append(f"| 规范合规 | {p0} | {p1} | {p2} | — | — | — |")
    lines.append(f"| 代码质量 | — | — | — | {q_high} | {q_med} | {q_low} |")

    if quality:
        overall = quality.get("overall_score", "-")
        lines.append(f"\n**代码质量评分**: {overall}/100")

    return "\n".join(lines)


# ── Conclusion ──────────────────────────────────────────────────

def _render_conclusion(findings: dict) -> str:
    status = findings.get("review_status", "UNKNOWN")
    violations = findings.get("spec_violations", [])
    summary = findings.get("summary", "")

    lines = ["## 结论", ""]

    p0 = sum(1 for v in violations if v.get("level") == "P0")
    p1 = sum(1 for v in violations if v.get("level") == "P1")

    if status == "PASSED":
        lines.append(f"✅ 通过 — 规范合规检查和代码质量分析均通过。")
    elif status == "FAILED":
        lines.append(f"❌ 未通过 — 存在 P0={p0}, P1={p1} 级问题，需修复后重新提交审查。")
    else:
        lines.append(f"⚠️ {status}")

    if summary:
        lines.append(f"\n{summary}")

    return "\n".join(lines)


# ── Top-level file writer ───────────────────────────────────────

def generate_report(
    quality: dict | None,
    findings: dict,
    output_path: Path,
) -> None:
    """Write the combined Markdown report to *output_path*."""
    md = render(quality, findings)
    output_path.write_text(md, encoding="utf-8")
