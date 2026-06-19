"""Tests for report generator (JSON to Markdown)."""

from pathlib import Path
from agents.reviewer.check_system.code_check.reporter import (
    generate_precheck_report,
    generate_final_report,
    level_icon,
    result_icon,
    conclusion_for,
    build_metadata_block,
    build_precheck_section,
    build_ai_section,
    build_summary_section,
    build_conclusion_section,
)
from agents.reviewer.check_system.code_check.models import (
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
    Level,
    Result,
    BlockingStrategy,
)


class TestIcons:
    def test_level_icon(self):
        assert level_icon(Level.P0) == "\U0001f534"
        assert level_icon(Level.P1) == "\U0001f7e1"
        assert level_icon(Level.P2) == "\U0001f7e2"

    def test_result_icon(self):
        assert result_icon(Result.PASS) == "✅"
        assert result_icon(Result.FAIL) == "❌"
        assert result_icon(Result.NA) == "➖"


class TestMetadataBlock:
    def test_build(self):
        scope = ScanScope(base_path="/src/main/java/user", file_count=5,
                          breakdown={"controller": 2, "service": 3})
        meta = ScanMetadata(module="user", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        result = ScanResult(metadata=meta, file_reports=[],
                            summary=ScanSummary(total_checks=10, passed=10),
                            hints_for_ai=[])
        md = build_metadata_block(result, None)
        assert "# 代码审查报告" in md
        assert "user" in md
        assert "/src/main/java/user" in md
        assert "5 个文件" in md
        assert "strict" in md


class TestPrecheckSection:
    def test_all_passed(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        result = ScanResult(metadata=meta, file_reports=[], summary=summary)
        md = build_precheck_section(result)
        assert "全部通过" in md
        assert "25 项" in md

    def test_with_findings(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={"controller": 1})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        finding = Finding(code="BE-QL-29", level=Level.P1, line=24,
                          method="createUser", message="缺少 @Validated",
                          evidence="public Result<Void> createUser(CreateUserDTO dto)")
        report = FileReport(file="UserController.java", findings=[finding])
        summary = ScanSummary(total_checks=25, passed=24,
                              failed=[{"code": "BE-QL-29", "count": 1}])
        result = ScanResult(metadata=meta, file_reports=[report],
                            summary=summary, hints_for_ai=[])
        md = build_precheck_section(result)
        assert "UserController.java" in md
        assert "BE-QL-29" in md
        assert "createUser" in md


class TestAISection:
    def test_all_passed(self):
        meta = ReviewMetadata(module="test", precheck_passed=True)
        summary = ReviewSummary(total=21, pass_=21, fail=0, na=0)
        result = ReviewResult(metadata=meta, items=[], summary=summary)
        md = build_ai_section(result)
        assert "全部通过" in md
        assert "21 项" in md

    def test_with_failures(self):
        item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                          file="UserServiceImpl.java", line=67,
                          evidence='log.info("更新完成");',
                          suggestion='应改为含 userId')
        meta = ReviewMetadata(module="test", precheck_passed=True)
        summary = ReviewSummary(total=21, pass_=20, fail=1, na=0)
        result = ReviewResult(metadata=meta, items=[item], summary=summary)
        md = build_ai_section(result)
        assert "BE-QL-11" in md
        assert "UserServiceImpl.java" in md
        assert "应改为含 userId" in md

    def test_when_ai_result_is_none(self):
        md = build_ai_section(None)
        assert "未执行" in md


class TestSummarySection:
    def test_build(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        finding_p0 = Finding(code="BE-QL-09", level=Level.P0, line=10,
                             message="敏感信息", evidence="log.info(token)")
        finding_p1 = Finding(code="BE-QL-29", level=Level.P1, line=24,
                             method="createUser", message="缺少 @Validated",
                             evidence="public Result<Void> createUser(CreateUserDTO dto)")
        report = FileReport(file="Test.java", findings=[finding_p0, finding_p1])
        summary = ScanSummary(total_checks=25, passed=23,
                              failed=[{"code": "BE-QL-09", "count": 1},
                                      {"code": "BE-QL-29", "count": 1}])
        pre_result = ScanResult(metadata=meta, file_reports=[report],
                                summary=summary, hints_for_ai=[])
        ai_item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                             file="Test.java", line=67, evidence='log.info("ok")',
                             suggestion="含 userId")
        ai_meta = ReviewMetadata(module="test", precheck_passed=False,
                                 precheck_issues=["BE-QL-09 (x1)", "BE-QL-29 (x1)"])
        ai_summary = ReviewSummary(total=21, pass_=20, fail=1, na=0)
        ai_result = ReviewResult(metadata=ai_meta, items=[ai_item], summary=ai_summary)
        md = build_summary_section(pre_result, ai_result)
        assert "程序预检" in md
        assert "AI 检查" in md
        assert "1" in md  # P0 count


class TestConclusion:
    def test_pass(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        pre_result = ScanResult(metadata=meta, file_reports=[], summary=summary)
        ai_meta = ReviewMetadata(module="test", precheck_passed=True)
        ai_summary = ReviewSummary(total=21, pass_=21, fail=0, na=0)
        ai_result = ReviewResult(metadata=ai_meta, items=[], summary=ai_summary)
        conclusion = conclusion_for(pre_result, ai_result)
        assert "✅ 通过" in conclusion

    def test_precheck_blocked(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        finding = Finding(code="BE-QL-29", level=Level.P1, line=24,
                          method="createUser", message="缺少 @Validated",
                          evidence="test")
        report = FileReport(file="Test.java", findings=[finding])
        summary = ScanSummary(total_checks=25, passed=24,
                              failed=[{"code": "BE-QL-29", "count": 1}])
        pre_result = ScanResult(metadata=meta, file_reports=[report],
                                summary=summary, hints_for_ai=[])
        conclusion = conclusion_for(pre_result, None)
        assert "❌ 未通过" in conclusion
        assert "程序预检" in conclusion
        assert "修复" in conclusion

    def test_ai_suggestions_only(self):
        scope = ScanScope(base_path="src/", file_count=3, breakdown={})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        pre_result = ScanResult(metadata=meta, file_reports=[], summary=summary)
        ai_item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                             file="Test.java", line=67, evidence='log.info("ok")',
                             suggestion="含 userId")
        ai_meta = ReviewMetadata(module="test", precheck_passed=True)
        ai_summary = ReviewSummary(total=21, pass_=20, fail=1, na=0)
        ai_result = ReviewResult(metadata=ai_meta, items=[ai_item], summary=ai_summary)
        conclusion = conclusion_for(pre_result, ai_result)
        assert "通过" in conclusion
        assert "建议" in conclusion


class TestGeneratePrecheckReport:
    def test_generates_markdown(self, tmp_path):
        scope = ScanScope(base_path="src/", file_count=1, breakdown={"controller": 1})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=False)
        finding = Finding(code="BE-QL-29", level=Level.P1, line=24,
                          method="createUser", message="缺少 @Validated",
                          evidence="test code")
        report = FileReport(file="TestController.java", findings=[finding])
        summary = ScanSummary(total_checks=25, passed=24,
                              failed=[{"code": "BE-QL-29", "count": 1}])
        result = ScanResult(metadata=meta, file_reports=[report],
                            summary=summary, hints_for_ai=[])
        output = tmp_path / "pre-check-report.md"
        generate_precheck_report(result, output)
        content = output.read_text()
        assert "# 代码审查报告" in content
        assert "TestController.java" in content
        assert "BE-QL-29" in content


class TestGenerateFinalReport:
    def test_generates_markdown(self, tmp_path):
        scope = ScanScope(base_path="src/", file_count=1, breakdown={"controller": 1})
        meta = ScanMetadata(module="test", scan_scope=scope,
                            blocking_strategy=BlockingStrategy.STRICT, passed=True)
        summary = ScanSummary(total_checks=25, passed=25, failed=[])
        pre_result = ScanResult(metadata=meta, file_reports=[], summary=summary, hints_for_ai=[])
        ai_item = ReviewItem(code="BE-QL-11", category="日志", result=Result.FAIL,
                             file="TestServiceImpl.java", line=67,
                             evidence='log.info("ok");',
                             suggestion="含 userId")
        ai_meta = ReviewMetadata(module="test", precheck_passed=True)
        ai_summary = ReviewSummary(total=21, pass_=20, fail=1, na=0)
        ai_result = ReviewResult(metadata=ai_meta, items=[ai_item], summary=ai_summary)
        output = tmp_path / "final-report.md"
        generate_final_report(pre_result, ai_result, output)
        content = output.read_text()
        assert "# 代码审查报告" in content
        assert "程序预检" in content
        assert "AI 检查" in content
        assert "汇总" in content
        assert "结论" in content
        assert "TestServiceImpl.java" in content
