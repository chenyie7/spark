"""Data models for code-check system."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime, timezone
from typing import Optional


class Level(str, Enum):
    """检查级别."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Result(str, Enum):
    """AI 检查结果."""
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


class BlockingStrategy(str, Enum):
    """阻断策略."""
    STRICT = "strict"
    NORMAL = "normal"
    LOOSE = "loose"


@dataclass
class Finding:
    """程序预检发现的问题."""
    code: str
    level: Level
    line: int
    message: str
    evidence: str
    method: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "level": self.level.value,
             "line": self.line, "message": self.message,
             "evidence": self.evidence}
        if self.method:
            d["method"] = self.method
        return d


@dataclass
class FileReport:
    """单个文件的预检报告."""
    file: str
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class ScanScope:
    """扫描范围统计."""
    base_path: str
    file_count: int
    breakdown: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "base_path": self.base_path,
            "file_count": self.file_count,
            "breakdown": self.breakdown,
        }


@dataclass
class ScanMetadata:
    """扫描元信息."""
    module: str
    scan_scope: ScanScope
    blocking_strategy: BlockingStrategy
    passed: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "scan_scope": self.scan_scope.to_dict(),
            "timestamp": self.timestamp,
            "blocking_strategy": self.blocking_strategy.value,
            "passed": self.passed,
        }


@dataclass
class ScanSummary:
    """扫描结果汇总."""
    total_checks: int
    passed: int
    failed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
        }


@dataclass
class HintForAI:
    """给 AI 的注意力线索."""
    file: str
    line: int
    code: str
    snippet: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "code": self.code,
            "snippet": self.snippet,
        }


@dataclass
class ScanResult:
    """程序预检完整结果."""
    metadata: ScanMetadata
    file_reports: list[FileReport] = field(default_factory=list)
    summary: ScanSummary = field(default_factory=lambda: ScanSummary(total_checks=0, passed=0))
    hints_for_ai: list[HintForAI] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "file_reports": [r.to_dict() for r in self.file_reports],
            "summary": self.summary.to_dict(),
            "hints_for_ai": [h.to_dict() for h in self.hints_for_ai],
        }


@dataclass
class ReviewItem:
    """AI 检查清单中的单条结果."""
    code: str
    category: str
    result: Result
    file: str
    line: int
    evidence: str
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "category": self.category,
            "result": self.result.value,
            "file": self.file,
            "line": self.line,
            "evidence": self.evidence,
        }
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class ReviewMetadata:
    """AI 检查元信息."""
    module: str
    precheck_passed: bool
    precheck_issues: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "timestamp": self.timestamp,
            "precheck_passed": self.precheck_passed,
            "precheck_issues": self.precheck_issues,
        }


@dataclass
class ReviewSummary:
    """AI 检查结果汇总."""
    total: int
    pass_: int = 0
    fail: int = 0
    na: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "pass": self.pass_,
            "fail": self.fail,
            "na": self.na,
        }


@dataclass
class ReviewResult:
    """AI 检查完整结果."""
    metadata: ReviewMetadata
    items: list[ReviewItem] = field(default_factory=list)
    summary: ReviewSummary = field(default_factory=lambda: ReviewSummary(total=0))

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "items": [i.to_dict() for i in self.items],
            "summary": self.summary.to_dict(),
        }
