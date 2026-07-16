#!/usr/bin/env python3
"""code-check CLI — report-only entry point after reviewer refactor."""

import argparse
import json
import sys
from pathlib import Path

from code_check.reporter import generate_report


def load_json(path: Path) -> dict:
    """Load a JSON file, returning {} if missing or malformed."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: Failed to parse '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def cmd_report(args):
    """Merge quality.json + findings.json → final-report.md."""
    quality_path = Path(args.quality)
    findings_path = Path(args.findings) if args.findings else None
    output_path = Path(args.output)

    if findings_path and not findings_path.exists():
        print(f"Error: findings.json not found: {findings_path}", file=sys.stderr)
        sys.exit(1)

    if not quality_path.exists():
        print(f"Warning: quality.json not found: {quality_path} — quality overview will be skipped", file=sys.stderr)

    quality = load_json(quality_path) if quality_path.exists() else None
    findings = load_json(findings_path) if findings_path else {"review_status": "UNKNOWN", "spec_violations": [], "quality_issues": []}

    if not findings:
        print("Warning: findings.json is empty, using defaults", file=sys.stderr)
        findings = {"review_status": "UNKNOWN", "spec_violations": [], "quality_issues": []}

    generate_report(quality, findings, output_path)
    print(f"Final report -> {output_path}")


def main():
    parser = argparse.ArgumentParser(prog="code-check", description="Review report generator")
    sub = parser.add_subparsers(dest="command")

    # report — the only command after refactor
    p_report = sub.add_parser("report", help="Generate final Markdown report")
    p_report.add_argument("--quality", required=True, help="quality.json from fuck-u-code analyze")
    p_report.add_argument("--findings", default=None, help="findings.json from AI unified review (optional)")
    p_report.add_argument("--output", required=True, help="Output Markdown path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
