"""Report generator — converts ScanResult / ReviewResult to Markdown.

Provides five report sections that can be composed into either a
pre-check-only report or a full final report.
"""

from pathlib import Path
from scripts.code_check.models import (
    Finding,
    ScanResult,
    ReviewResult,
    Level,
    Result,
    BlockingStrategy,
)


# ── Icon helpers ──────────────────────────────────────────────────


_LEVEL_ICONS = {Level.P0: "🔴", Level.P1: "🟡", Level.P2: "🟢"}
_RESULT_ICONS = {Result.PASS: "✅", Result.FAIL: "❌", Result.NA: "➖"}


def level_icon(level: Level) -> str:
    """Return a coloured circle emoji for the given severity *level*."""
    return _LEVEL_ICONS.get(level, "")


def result_icon(result: Result) -> str:
    """Return a status emoji for the given check *result*."""
    return _RESULT_ICONS.get(result, "❓")


# ── Section builders ─────────────────────────────────────────────


def build_metadata_block(
    pre_result: ScanResult,
    ai_result: ReviewResult | None,
) -> str:
    """Report header: module, scan scope, strategy, timestamp, status."""
    meta = pre_result.metadata
    scope = meta.scan_scope

    status_icon = result_icon(Result.PASS) if meta.passed else result_icon(Result.FAIL)
    lines = [
        "# 代码审查报告",
        "",
        f"**模块**: {meta.module}",
        f"**扫描路径**: {scope.base_path}",
        f"**文件数量**: {scope.file_count} 个文件",
        f"**阻断策略**: {meta.blocking_strategy.value}",
        f"**扫描时间**: {meta.timestamp}",
        f"**状态**: {status_icon}",
    ]

    if scope.breakdown:
        breakdown_str = ", ".join(
            f"{k}: {v}" for k, v in scope.breakdown.items()
        )
        lines.append(f"**文件构成**: {breakdown_str}")

    return "\n".join(lines)


def build_precheck_section(result: ScanResult) -> str:
    """Program pre-check section: pass banner or failures table."""
    lines = ["## 程序预检", ""]  # 程序预检

    # Collect all findings with their file path
    all_findings: list[tuple[str, Finding]] = []
    for report in result.file_reports:
        for finding in report.findings:
            all_findings.append((report.file, finding))

    if not all_findings:
        lines.append(
            f"✅ 检查 {result.summary.total_checks} 项，全部通过"
        )
        return "\n".join(lines)

    # Sort: level desc (P0 first), then code asc
    level_order = {Level.P0: 0, Level.P1: 1, Level.P2: 2}
    all_findings.sort(key=lambda x: (level_order[x[1].level], x[1].code))

    # Table
    lines.append("| 文件 | 行号 | 方法 | 规则 | 级别 | 问题说明 |")
    lines.append("|------|------|------|------|------|----------|")

    for filepath, finding in all_findings:
        method = finding.method or "—"
        icon = level_icon(finding.level)
        lines.append(
            f"| {filepath} | {finding.line} | {method} "
            f"| {finding.code} | {icon} | {finding.message} |"
        )

    lines.append("")
    lines.append(
        f"共检查 {result.summary.total_checks} 项，"
        f"通过 {result.summary.passed} 项，"
        f"发现 {len(all_findings)} 个问题。"
    )

    return "\n".join(lines)


def build_ai_section(result: ReviewResult | None) -> str:
    """AI check section: pass banner or failures table, or skipped notice."""
    lines = ["## AI 检查", ""]

    if result is None:
        lines.append("*AI 检查未执行（程序预检被阻断）。*")
        return "\n".join(lines)

    fail_items = [item for item in result.items if item.result == Result.FAIL]

    if not fail_items:
        lines.append(
            f"✅ 检查 {result.summary.total} 项，全部通过"
        )
        return "\n".join(lines)

    # Sort by category, then code asc
    fail_items.sort(key=lambda x: (x.category, x.code))

    lines.append("| 类别 | 文件 | 行号 | 规则 | 问题说明 | 建议 |")
    lines.append("|------|------|------|------|----------|------|")

    for item in fail_items:
        suggestion = item.suggestion or "—"
        lines.append(
            f"| {item.category} | {item.file} | {item.line} "
            f"| {item.code} | `{item.evidence}` | {suggestion} |"
        )

    return "\n".join(lines)


def build_summary_section(
    pre_result: ScanResult,
    ai_result: ReviewResult | None,
) -> str:
    """Summary table with P0/P1/P2 breakdown from both sources."""
    lines = ["## 汇总", ""]  # 汇总

    # Count P0/P1/P2 from precheck findings
    all_findings: list[Finding] = []
    for report in pre_result.file_reports:
        all_findings.extend(report.findings)

    p0_count = sum(1 for f in all_findings if f.level == Level.P0)
    p1_count = sum(1 for f in all_findings if f.level == Level.P1)
    p2_count = sum(1 for f in all_findings if f.level == Level.P2)

    if ai_result:
        ai_fail = ai_result.summary.fail
        ai_pass = ai_result.summary.pass_
        ai_na = ai_result.summary.na
    else:
        ai_fail = ai_pass = ai_na = 0

    lines.append(
        "| 来源 | \U0001f534 P0 | \U0001f7e1 P1 | \U0001f7e2 P2 "
        "| ❌ FAIL | ✅ PASS | ➖ NA |"
    )
    lines.append(
        "|------|-------|-------|-------|---------|---------|-------|"
    )
    lines.append(
        f"| 程序预检 | {p0_count} | {p1_count} | {p2_count} "
        f"| — | — | — |"
    )
    lines.append(
        f"| AI 检查 | — | — | — "
        f"| {ai_fail} | {ai_pass} | {ai_na} |"
    )

    return "\n".join(lines)


def conclusion_for(
    pre_result: ScanResult,
    ai_result: ReviewResult | None,
) -> str:
    """Determine conclusion text based on pre-check and AI results."""

    # -- Pre-check blocked --
    if not pre_result.metadata.passed:
        all_findings: list[Finding] = []
        for report in pre_result.file_reports:
            all_findings.extend(report.findings)
        total = len(all_findings)

        strategy = pre_result.metadata.blocking_strategy
        if strategy == BlockingStrategy.STRICT:
            blocking = sum(
                1 for f in all_findings if f.level in (Level.P0, Level.P1)
            )
        else:
            blocking = sum(1 for f in all_findings if f.level == Level.P0)

        return (
            f"❌ 未通过 — 程序预检发现 {total} 个问题，"
            f"其中阻断级 {blocking} 个。"
            f"请先修复后再提交 AI 审查。"
        )

    # -- AI has suggestions --
    if ai_result and ai_result.summary.fail > 0:
        return (
            f"⚠️ 通过（有建议） — "
            f"AI 检查发现 {ai_result.summary.fail} 个建议项，"
            f"建议按建议修改以提升代码质量。"
        )

    # -- All clear --
    return (
        "✅ 通过 — 所有检查项通过，"
        "代码质量符合规范。"
    )


def build_conclusion_section(
    pre_result: ScanResult,
    ai_result: ReviewResult | None,
) -> str:
    """Conclusion section wrapping ``conclusion_for`` with a heading."""
    return f"## 结论\n\n{conclusion_for(pre_result, ai_result)}\n"


# ── Top-level generators ─────────────────────────────────────────


def generate_precheck_report(
    result: ScanResult,
    output_path: Path,
) -> None:
    """Write a pre-check-only Markdown report to *output_path*."""
    parts = [
        build_metadata_block(result, None),
        "",
        build_precheck_section(result),
    ]
    output_path.write_text("\n".join(parts))


def generate_final_report(
    pre_result: ScanResult,
    ai_result: ReviewResult | None,
    output_path: Path,
) -> None:
    """Write a complete Markdown report (5 sections) to *output_path*."""
    parts = [
        build_metadata_block(pre_result, ai_result),
        "",
        build_precheck_section(pre_result),
        "",
        build_ai_section(ai_result),
        "",
        build_summary_section(pre_result, ai_result),
        "",
        build_conclusion_section(pre_result, ai_result),
    ]
    output_path.write_text("\n".join(parts))
