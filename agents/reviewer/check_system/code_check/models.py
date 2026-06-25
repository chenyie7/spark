"""Data models for the review system — findings schema only.

After the refactor, this module only defines the structured output
that the AI reviewer must produce (findings.json).  Quality data
from fuck-u-code is passed through as a raw dict — no model needed.
"""

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class SpecViolation:
    """A single spec-compliance violation found by the AI reviewer."""

    rule_id: str          # e.g. "BE-QL-14"
    level: str            # "P0" | "P1" | "P2"
    file: str             # relative path, e.g. "auth/controller/AuthController.java"
    line: int             # line number where the violation occurs
    method: str           # method name, e.g. "login"
    description: str      # what the violation is
    suggestion: str       # how to fix it

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "file": self.file,
            "line": self.line,
            "method": self.method,
            "description": self.description,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpecViolation":
        return cls(
            rule_id=d["rule_id"],
            level=d["level"],
            file=d["file"],
            line=d["line"],
            method=d.get("method", "-"),
            description=d["description"],
            suggestion=d.get("suggestion", ""),
        )


@dataclass
class QualityIssue:
    """A code-quality issue found by the AI reviewer (often guided by fuck-u-code scores)."""

    file: str             # relative path
    line: int             # line number
    dimension: str        # "N+1查询" | "复杂度" | "重复代码" | "异常处理" | "命名" | ...
    severity: str         # "high" | "medium" | "low"
    detail: str           # description of the issue
    suggestion: str       # how to fix it

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "dimension": self.dimension,
            "severity": self.severity,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QualityIssue":
        return cls(
            file=d["file"],
            line=d["line"],
            dimension=d["dimension"],
            severity=d["severity"],
            detail=d["detail"],
            suggestion=d.get("suggestion", ""),
        )


@dataclass
class FindingsResult:
    """Top-level result produced by the AI unified review."""

    review_status: str   # "PASSED" | "FAILED"
    spec_violations: list[dict] = field(default_factory=list)
    quality_issues: list[dict] = field(default_factory=list)
    summary: str = ""

    def has_p0(self) -> bool:
        return any(v.get("level") == "P0" for v in self.spec_violations)

    def has_p1(self) -> bool:
        return any(v.get("level") == "P1" for v in self.spec_violations)

    def p0_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P0")

    def p1_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P1")

    def p2_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P2")

    def quality_high_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "high")

    def quality_medium_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "medium")

    def quality_low_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "low")

    def to_dict(self) -> dict:
        return {
            "review_status": self.review_status,
            "spec_violations": self.spec_violations,
            "quality_issues": self.quality_issues,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FindingsResult":
        return cls(
            review_status=d["review_status"],
            spec_violations=d.get("spec_violations", []),
            quality_issues=d.get("quality_issues", []),
            summary=d.get("summary", ""),
        )
