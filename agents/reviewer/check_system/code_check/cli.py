#!/usr/bin/env python3
"""code-check CLI — 双层代码校验系统入口."""

import argparse
import json
import sys
from pathlib import Path

from code_check.config import load_cli_config, load_program_checks, ConfigLoadError
from code_check.scanner import scan_files
from code_check.reporter import generate_precheck_report, generate_final_report
from code_check.models import (
    ScanResult, ReviewResult, Finding, FileReport, ScanScope, ScanMetadata, ScanSummary,
    ReviewItem, ReviewMetadata, ReviewSummary, HintForAI,
    Level, Result, BlockingStrategy,
)


def load_scan_result(json_path: Path) -> ScanResult:
    """Load a ScanResult from a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _parse_scan_result(data)


def load_review_result(json_path: Path) -> ReviewResult:
    """Load a ReviewResult from a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _parse_review_result(data)


def _parse_scan_result(data: dict) -> ScanResult:
    meta = data["metadata"]
    scope_data = meta["scan_scope"]
    scope = ScanScope(
        base_path=scope_data["base_path"],
        file_count=scope_data["file_count"],
        breakdown=scope_data.get("breakdown", {}),
    )
    metadata = ScanMetadata(
        module=meta["module"],
        scan_scope=scope,
        blocking_strategy=BlockingStrategy(meta["blocking_strategy"]),
        passed=meta["passed"],
        timestamp=meta.get("timestamp", ""),
    )
    reports = []
    for r in data.get("file_reports", []):
        findings = []
        for f in r.get("findings", []):
            findings.append(Finding(
                code=f["code"], level=Level(f["level"]), line=f["line"],
                method=f.get("method"), message=f["message"], evidence=f["evidence"],
            ))
        reports.append(FileReport(file=r["file"], findings=findings))
    summary = ScanSummary(
        total_checks=data["summary"]["total_checks"],
        passed=data["summary"]["passed"],
        failed=data["summary"].get("failed", []),
    )
    hints = []
    for h in data.get("hints_for_ai", []):
        hints.append(HintForAI(file=h["file"], line=h["line"], code=h["code"], snippet=h["snippet"]))
    return ScanResult(metadata=metadata, file_reports=reports, summary=summary, hints_for_ai=hints)


def _parse_review_result(data: dict) -> ReviewResult:
    meta = data["metadata"]
    metadata = ReviewMetadata(
        module=meta["module"],
        precheck_passed=meta.get("precheck_passed", True),
        precheck_issues=meta.get("precheck_issues", []),
        timestamp=meta.get("timestamp", ""),
    )
    items = []
    for i in data.get("items", []):
        items.append(ReviewItem(
            code=i["code"], category=i["category"], result=Result(i["result"]),
            file=i.get("file", "-"), line=i.get("line", 0),
            evidence=i.get("evidence", ""), suggestion=i.get("suggestion"),
        ))
    summary = ReviewSummary(
        total=data["summary"]["total"], pass_=data["summary"]["pass"],
        fail=data["summary"]["fail"], na=data["summary"]["na"],
    )
    return ReviewResult(metadata=metadata, items=items, summary=summary)


def cmd_scan(args):
    """Run program pre-check scan."""
    config_path = Path(args.config) if args.config else None
    config = load_cli_config(config_path)
    rules_dir = args.rules_dir or config["rules_dir"]
    strategy = args.strategy or config["strategy"]
    if isinstance(strategy, str):
        strategy = BlockingStrategy(strategy)
    output_dir = Path(args.output_dir or config["output_dir"])
    output_format = args.format or config["format"]
    config["strategy"] = strategy
    rules_dir = Path(rules_dir)

    scan_path = args.path or config.get("default_scan_path", "src/main/java")
    target = Path(scan_path)

    if not target.exists():
        print(f"Error: path not found: {target}", file=sys.stderr)
        sys.exit(1)

    try:
        rules = load_program_checks(rules_dir)
    except ConfigLoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not rules:
        print("Warning: No program check rules found.", file=sys.stderr)

    result = scan_files(target, rules, config)
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        json_path = output_dir / "pre-check-result.json"
        json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Pre-check result → {json_path}")

    if output_format == "md" or not result.metadata.passed:
        md_path = output_dir / "pre-check-report.md"
        generate_precheck_report(result, md_path)
        print(f"Pre-check report → {md_path}")

    if not result.metadata.passed:
        print(f"\nPre-check FAILED — {len(result.file_reports)} file(s) with issues.")
        sys.exit(1)
    else:
        print(f"\nPre-check PASSED — {result.summary.total_checks} checks, all clear.")
        sys.exit(0)


def cmd_report(args):
    """Generate final Markdown report."""
    pre_path = Path(args.pre)
    if not pre_path.exists():
        print(f"Error: pre-check result not found: {pre_path}", file=sys.stderr)
        sys.exit(1)

    pre_result = load_scan_result(pre_path)
    ai_result = None
    if args.ai:
        ai_path = Path(args.ai)
        if ai_path.exists():
            ai_result = load_review_result(ai_path)
        else:
            print(f"Warning: AI result not found: {ai_path}", file=sys.stderr)

    output_path = Path(args.output)
    generate_final_report(pre_result, ai_result, output_path)
    print(f"Final report → {output_path}")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(prog="code-check", description="双层代码校验系统")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Run program pre-check scan")
    p_scan.add_argument("path", nargs="?", default=None, help="Target directory to scan (default: from config)")
    p_scan.add_argument("--rules-dir", help="Path to check-rules/ directory")
    p_scan.add_argument("--strategy", choices=["strict", "normal", "loose"], help="Blocking strategy")
    p_scan.add_argument("--format", choices=["json", "md"], help="Output format")
    p_scan.add_argument("--output-dir", help="Output directory")
    p_scan.add_argument("--config", help="Config file path")

    p_report = sub.add_parser("report", help="Generate final Markdown report")
    p_report.add_argument("--pre", required=True, help="Pre-check result JSON path")
    p_report.add_argument("--ai", help="AI check result JSON path (optional)")
    p_report.add_argument("--output", required=True, help="Output Markdown path")
    p_report.add_argument("--config", help="Config file path")

    args = parser.parse_args()
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
