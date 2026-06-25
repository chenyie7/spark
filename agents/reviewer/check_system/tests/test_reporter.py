from code_check.reporter import render


class TestRender:
    def test_passed_report(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "PASSED" in md
        assert "静态质量概览" in md
        assert "规范合规检查" in md
        assert "代码深度问题" in md
        assert "汇总" in md

    def test_failed_report(self, sample_quality, sample_findings_failed):
        md = render(sample_quality, sample_findings_failed)
        assert "FAILED" in md
        assert "BE-QL-14" in md
        assert "BE-AU-07" in md
        assert "N+1查询" in md
        assert "P0" in md

    def test_no_quality(self, sample_findings_passed):
        md = render(None, sample_findings_passed)
        assert "PASSED" in md
        assert "静态质量概览" not in md

    def test_empty_violations_shows_pass_banner(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "所有规范合规检查通过" in md

    def test_empty_issues_shows_pass_banner(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "未发现深度质量问题" in md

    def test_quality_overview_has_metrics_table(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "complexity" in md
        assert "8.2" in md
        assert "最差文件" in md
