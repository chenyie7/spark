"""Tests for CLI."""

import json
import subprocess
import sys
from pathlib import Path
from code_check.cli import (
    load_scan_result, load_review_result,
    _parse_scan_result, _parse_review_result,
)
from code_check.models import (
    ScanResult, ScanScope, ScanMetadata, ScanSummary, Finding, FileReport,
    ReviewResult, ReviewMetadata, ReviewSummary, ReviewItem, HintForAI,
    Level, Result, BlockingStrategy,
)


class TestParseScanResult:
    def test_roundtrip(self, tmp_path):
        """Verify a ScanResult can be serialized and deserialized."""
        scope = ScanScope(base_path="/src", file_count=2, breakdown={"controller": 2})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        finding = Finding(code="BE-QL-29", level=Level.P1, line=24, method="createUser",
                          message="缺少 @Validated", evidence="public Result<Void> createUser(CreateUserDTO dto)")
        report = FileReport(file="UserController.java", findings=[finding])
        summary = ScanSummary(total_checks=10, passed=9, failed=[{"code": "BE-QL-29", "count": 1}])
        hint = HintForAI(file="Test.java", line=10, code="BE-QL-09", snippet="log.info(token)")
        original = ScanResult(metadata=meta, file_reports=[report], summary=summary, hints_for_ai=[hint])

        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(original.to_dict(), ensure_ascii=False, indent=2))

        loaded = load_scan_result(json_path)
        assert loaded.metadata.module == "test"
        assert loaded.metadata.scan_scope.file_count == 2
        assert len(loaded.file_reports) == 1
        assert loaded.file_reports[0].findings[0].code == "BE-QL-29"
        assert len(loaded.hints_for_ai) == 1


class TestParseReviewResult:
    def test_roundtrip(self, tmp_path):
        """Verify a ReviewResult can be serialized and deserialized."""
        item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                          file="Test.java", line=67, evidence="log.info(\"ok\")",
                          suggestion="含 userId")
        meta = ReviewMetadata(module="test", precheck_passed=True, precheck_issues=[])
        summary = ReviewSummary(total=21, pass_=20, fail=1, na=0)
        original = ReviewResult(metadata=meta, items=[item], summary=summary)

        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(original.to_dict(), ensure_ascii=False, indent=2))

        loaded = load_review_result(json_path)
        assert loaded.metadata.module == "test"
        assert len(loaded.items) == 1
        assert loaded.items[0].result == Result.FAIL
        assert loaded.summary.pass_ == 20


import os

CHECK_SYSTEM_DIR = str(Path(__file__).resolve().parent.parent)


class TestCLIHelp:
    def test_scan_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "code_check.cli", "scan", "--help"],
            capture_output=True, text=True,
            cwd=CHECK_SYSTEM_DIR,
        )
        assert result.returncode == 0, result.stderr
        assert "scan" in result.stdout

    def test_report_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "code_check.cli", "report", "--help"],
            capture_output=True, text=True,
            cwd=CHECK_SYSTEM_DIR,
        )
        assert result.returncode == 0, result.stderr
        assert "report" in result.stdout
