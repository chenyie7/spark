from code_check.models import (
    FindingsResult,
    SpecViolation,
    QualityIssue,
)


class TestSpecViolation:
    def test_to_dict(self):
        v = SpecViolation(
            rule_id="BE-QL-14", level="P1",
            file="AuthController.java", line=42, method="login",
            description="裸Map", suggestion="用VO",
        )
        d = v.to_dict()
        assert d["rule_id"] == "BE-QL-14"
        assert d["level"] == "P1"
        assert d["file"] == "AuthController.java"
        assert d["line"] == 42

    def test_from_dict(self):
        d = {
            "rule_id": "BE-QL-14", "level": "P1",
            "file": "AuthController.java", "line": 42, "method": "login",
            "description": "裸Map", "suggestion": "用VO",
        }
        v = SpecViolation.from_dict(d)
        assert v.rule_id == "BE-QL-14"
        assert v.line == 42

    def test_from_dict_without_optional_fields(self):
        d = {
            "rule_id": "BE-MP-01", "level": "P0",
            "file": "Mapper.java", "line": 10,
            "description": "用了 @Select",
        }
        v = SpecViolation.from_dict(d)
        assert v.method == "-"
        assert v.suggestion == ""


class TestQualityIssue:
    def test_to_dict(self):
        q = QualityIssue(
            file="UserServiceImpl.java", line=38,
            dimension="N+1查询", severity="high",
            detail="逐条查库", suggestion="批量查询",
        )
        d = q.to_dict()
        assert d["dimension"] == "N+1查询"
        assert d["severity"] == "high"

    def test_from_dict(self):
        d = {
            "file": "UserServiceImpl.java", "line": 38,
            "dimension": "N+1查询", "severity": "high",
            "detail": "逐条查库", "suggestion": "批量查询",
        }
        q = QualityIssue.from_dict(d)
        assert q.file == "UserServiceImpl.java"
        assert q.severity == "high"

    def test_from_dict_without_optional_suggestion(self):
        d = {
            "file": "DeptServiceImpl.java", "line": 50,
            "dimension": "复杂度", "severity": "medium",
            "detail": "方法超过 50 行",
        }
        q = QualityIssue.from_dict(d)
        assert q.suggestion == ""


class TestFindingsResult:
    def test_passed(self, sample_findings_passed):
        r = FindingsResult.from_dict(sample_findings_passed)
        assert r.review_status == "PASSED"
        assert r.p0_count() == 0
        assert not r.has_p0()

    def test_failed(self, sample_findings_failed):
        r = FindingsResult.from_dict(sample_findings_failed)
        assert r.review_status == "FAILED"
        assert r.p0_count() == 1
        assert r.p1_count() == 1
        assert r.p2_count() == 0
        assert r.has_p0()
        assert r.quality_high_count() == 1

    def test_to_dict_roundtrip(self, sample_findings_failed):
        r = FindingsResult.from_dict(sample_findings_failed)
        d = r.to_dict()
        assert d["review_status"] == "FAILED"
        assert len(d["spec_violations"]) == 2
        assert len(d["quality_issues"]) == 1

    def test_empty_findings(self, sample_findings_passed):
        r = FindingsResult.from_dict(sample_findings_passed)
        assert r.p0_count() == 0
        assert r.p1_count() == 0
        assert r.p2_count() == 0
        assert r.quality_high_count() == 0
        assert r.quality_medium_count() == 0
        assert r.quality_low_count() == 0
