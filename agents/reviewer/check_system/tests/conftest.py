import json
import pytest
from pathlib import Path


@pytest.fixture
def sample_quality() -> dict:
    return {
        "overall_score": 72,
        "scan_path": "admin-test-02/src/main/java",
        "file_count": 99,
        "metrics": {
            "complexity": 8.2,
            "duplication": 6.5,
            "size": 7.0,
            "structure": 7.8,
            "error_handling": 6.0,
            "naming": 8.5,
            "comments": 5.5,
        },
        "worst_files": [
            {"file": "UserServiceImpl.java", "score": 45, "shit_gas_index": 82},
            {"file": "AuthController.java", "score": 52, "shit_gas_index": 70},
        ],
    }


@pytest.fixture
def sample_findings_passed() -> dict:
    return {
        "review_status": "PASSED",
        "spec_violations": [],
        "quality_issues": [],
        "summary": "All checks passed.",
    }


@pytest.fixture
def sample_findings_failed() -> dict:
    return {
        "review_status": "FAILED",
        "spec_violations": [
            {
                "rule_id": "BE-QL-14",
                "level": "P1",
                "file": "auth/controller/AuthController.java",
                "line": 42,
                "method": "login",
                "description": "返回裸 Map<String, Object>",
                "suggestion": "使用 LoginResultVO",
            },
            {
                "rule_id": "BE-AU-07",
                "level": "P0",
                "file": "auth/service/impl/AuthServiceImpl.java",
                "line": 56,
                "method": "login",
                "description": "密码使用 MD5 而非 BCrypt",
                "suggestion": "使用 passwordEncoder.matches()",
            },
        ],
        "quality_issues": [
            {
                "file": "system/service/impl/UserServiceImpl.java",
                "line": 38,
                "dimension": "N+1查询",
                "severity": "high",
                "detail": "在 stream.map() 内逐条查数据库",
                "suggestion": "先收集所有 ID，使用 selectBatchIds 批量查询",
            },
        ],
        "summary": "P0=1, P1=1, 质量高=1",
    }


@pytest.fixture
def sample_findings_empty_quality() -> dict:
    return {
        "review_status": "PASSED",
        "spec_violations": [],
        "quality_issues": [],
        "summary": "",
    }
