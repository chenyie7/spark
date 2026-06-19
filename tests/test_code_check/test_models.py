"""Tests for data models."""

from scripts.code_check.models import (
    Finding,
    FileReport,
    ScanScope,
    ScanMetadata,
    ScanResult,
    ScanSummary,
    ReviewItem,
    ReviewMetadata,
    ReviewResult,
    ReviewSummary,
    HintForAI,
    Level,
    Result,
    BlockingStrategy,
)


class TestFinding:
    def test_create_finding(self):
        f = Finding(
            code="BE-QL-29",
            level=Level.P1,
            line=24,
            method="createUser",
            message="createUser 缺少 @Validated",
            evidence="public Result<Void> createUser(CreateUserDTO dto)",
        )
        assert f.code == "BE-QL-29"
        assert f.level == Level.P1
        assert f.line == 24

    def test_finding_method_optional(self):
        f = Finding(
            code="BE-QL-07",
            level=Level.P1,
            line=15,
            message="使用 System.out.println",
            evidence="System.out.println(\"debug\");",
        )
        assert f.method is None

    def test_finding_to_dict(self):
        f = Finding(
            code="BE-QL-29",
            level=Level.P1,
            line=24,
            method="createUser",
            message="缺少 @Validated",
            evidence="public Result<Void> createUser(CreateUserDTO dto)",
        )
        d = f.to_dict()
        assert d["code"] == "BE-QL-29"
        assert d["level"] == "P1"
        assert d["line"] == 24
        assert d["method"] == "createUser"
        assert d["message"] == "缺少 @Validated"
        assert d["evidence"] == "public Result<Void> createUser(CreateUserDTO dto)"


class TestFileReport:
    def test_create_report(self):
        finding = Finding(
            code="BE-QL-29",
            level=Level.P1,
            line=24,
            method="createUser",
            message="缺少 @Validated",
            evidence="public Result<Void> createUser(CreateUserDTO dto)",
        )
        report = FileReport(file="UserController.java", findings=[finding])
        assert report.file == "UserController.java"
        assert len(report.findings) == 1

    def test_to_dict(self):
        finding = Finding(code="BE-QL-07", level=Level.P1, line=10,
                          message="sysout", evidence="System.out.println()")
        report = FileReport(file="Test.java", findings=[finding])
        d = report.to_dict()
        assert d["file"] == "Test.java"
        assert len(d["findings"]) == 1


class TestScanResult:
    def test_passed_true_when_no_failed(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={"controller": 3})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        result = ScanResult(metadata=meta, file_reports=[], summary=summary, hints_for_ai=[])
        assert result.metadata.passed is True

    def test_passed_false_with_failed(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={"controller": 3})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        summary = ScanSummary(total_checks=25, passed=23,
                              failed=[{"code": "BE-QL-29", "count": 2}])
        result = ScanResult(metadata=meta, file_reports=[], summary=summary, hints_for_ai=[])
        assert result.metadata.passed is False

    def test_scan_result_to_dict(self):
        scope = ScanScope(base_path="src/main/java", file_count=1,
                          breakdown={"controller": 1})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        result = ScanResult(metadata=meta, file_reports=[], summary=summary,
                            hints_for_ai=[])
        d = result.to_dict()
        assert d["metadata"]["module"] == "test"
        assert d["metadata"]["scan_scope"]["base_path"] == "src/main/java"
        assert d["summary"]["total_checks"] == 25


class TestReviewResult:
    def test_create_review_result(self):
        item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                          file="UserServiceImpl.java", line=67,
                          evidence='log.info("更新完成");',
                          suggestion='应改为含 userId')
        meta = ReviewMetadata(module="test", precheck_passed=True, precheck_issues=[])
        summary = ReviewSummary(total=21, pass_=19, fail=2, na=0)
        result = ReviewResult(metadata=meta, items=[item], summary=summary)
        assert len(result.items) == 1
        assert result.items[0].result == Result.FAIL

    def test_review_item_pass_has_null_suggestion(self):
        item = ReviewItem(code="BE-QL-11", category="日志", result=Result.PASS,
                          file="Test.java", line=10, evidence="ok", suggestion=None)
        assert item.suggestion is None

    def test_review_result_to_dict(self):
        item = ReviewItem(code="BE-QL-11", category="日志", result=Result.PASS,
                          file="Test.java", line=10, evidence="ok", suggestion=None)
        meta = ReviewMetadata(module="test", precheck_passed=True, precheck_issues=[])
        summary = ReviewSummary(total=21, pass_=21, fail=0, na=0)
        result = ReviewResult(metadata=meta, items=[item], summary=summary)
        d = result.to_dict()
        assert d["summary"]["total"] == 21
        assert d["summary"]["pass"] == 21


class TestEnums:
    def test_level_values(self):
        assert Level.P0.value == "P0"
        assert Level.P1.value == "P1"
        assert Level.P2.value == "P2"

    def test_result_values(self):
        assert Result.PASS.value == "PASS"
        assert Result.FAIL.value == "FAIL"
        assert Result.NA.value == "NA"

    def test_blocking_strategy_values(self):
        assert BlockingStrategy.STRICT.value == "strict"
        assert BlockingStrategy.NORMAL.value == "normal"
        assert BlockingStrategy.LOOSE.value == "loose"


class TestHintForAI:
    def test_create_hint(self):
        h = HintForAI(file="UserController.java", line=45,
                      code="BE-QL-09",
                      snippet='log.info("用户登录成功，token: {}", token);')
        d = h.to_dict()
        assert d["file"] == "UserController.java"
        assert d["line"] == 45
        assert d["code"] == "BE-QL-09"
        assert "token" in d["snippet"]
