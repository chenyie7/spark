"""Tests for Java file scanner engine."""

import pytest
from pathlib import Path
from agents.reviewer.check_system.code_check.scanner import (
    scan_files,
    scan_single_file,
    TextGrepScanner,
    JavaAnnotationScanner,
    JavaReturnTypeScanner,
    classify_files,
    should_exclude,
    is_blocked,
)
from agents.reviewer.check_system.code_check.models import Level, BlockingStrategy, Finding, ScanResult


# ── Test Data ───────────────────────────────────────────────────

JAVA_WITH_SYSOUT = """
package com.example;

public class UserService {
    public void doSomething() {
        System.out.println("debug info");
        System.err.println("error debug");
    }
}
"""

JAVA_WITH_VALID_CONTROLLER = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import jakarta.validation.Valid;
import com.example.dto.CreateUserDTO;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(@Valid CreateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_WITHOUT_VALID = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import com.example.dto.CreateUserDTO;
import com.example.dto.UpdateUserDTO;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(CreateUserDTO dto) {
        return Result.success();
    }

    @PutMapping
    public Result<Void> updateUser(UpdateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_NO_RESULT_RETURN = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.dto.UserVO;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public UserVO getUser(@PathVariable Long id) {
        return new UserVO();
    }
}
"""

JAVA_WITH_AUTOWIRED = """
package com.example.service.impl;

import com.example.mapper.UserMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class UserServiceImpl {

    @Autowired
    private UserMapper userMapper;

    public void process() {
        userMapper.selectById(1L);
    }
}
"""

JAVA_WITH_FORBIDDEN_LOMBOK = """
package com.example.service;

import lombok.SneakyThrows;
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class FileService {

    @SneakyThrows
    public void readFile() {
        throw new Exception("fail");
    }
}
"""


# ── Helper ─────────────────────────────────────────────────────

def _temp_java_file(tmp_path, content, name="Test.java"):
    """Write content to a temp Java file and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


def _mock_rules_for_sysout():
    return {
        "BE-QL-07": {
            "description": "System.out/err",
            "level": "P1",
            "program": {
                "scanner": "text-grep",
                "pattern": "System\\.(out|err)\\.print",
            },
            "message": "{method} 使用 System.out/err，应使用 @Slf4j log",
        }
    }


def _mock_rules_for_validated():
    return {
        "BE-QL-29": {
            "description": "DTO 参数缺少 @Validated",
            "level": "P1",
            "program": {
                "scanner": "java-annotation",
                "on_class": "RestController|Controller",
                "target": "method_param",
                "match_param_type": "DTO",
                "missing_annotation": "@Validated|@Valid",
            },
            "message": "{method} 缺少 @Validated/@Valid 注解 DTO 参数",
        }
    }


def _mock_rules_for_result():
    return {
        "BE-QL-13": {
            "description": "返回值不是 Result<T>",
            "level": "P1",
            "program": {
                "scanner": "java-return-type",
                "on_class": "RestController|Controller",
                "required_return_pattern": "Result<",
            },
            "message": "{method} 返回值未使用 Result<T> 包裹",
        }
    }


def _mock_rules_for_autowired():
    return {
        "BE-QL-DUMMY": {
            "description": "@Autowired 字段注入",
            "level": "P1",
            "program": {
                "scanner": "text-grep",
                "pattern": "@Autowired",
            },
            "message": "{class} 使用了 @Autowired 字段注入，应改为构造注入",
        }
    }


def _mock_rules_for_forbidden_lombok():
    return {
        "BE-QL-33": {
            "description": "禁止的 Lombok 注解",
            "level": "P1",
            "program": {
                "scanner": "text-grep",
                "pattern": "@SneakyThrows|@Cleanup|@Synchronized",
            },
            "message": "{class} 使用了禁止的 Lombok 注解",
        }
    }


# ── Text Grep Tests ─────────────────────────────────────────────

class TestTextGrepScanner:
    def test_finds_sysout(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_SYSOUT)
        rules = _mock_rules_for_sysout()
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 2  # both System.out and System.err

    def test_no_match_returns_empty(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_VALID_CONTROLLER)
        rules = _mock_rules_for_sysout()
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 0

    def test_finding_has_correct_fields(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_SYSOUT)
        rules = _mock_rules_for_sysout()
        findings = TextGrepScanner().scan(f, rules)
        finding = findings[0]
        assert finding.code == "BE-QL-07"
        assert finding.level == Level.P1
        assert "System.out" in finding.evidence or "System.err" in finding.evidence


# ── Java Annotation Tests ──────────────────────────────────────

class TestJavaAnnotationScanner:
    def test_all_valid_no_findings(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_VALID_CONTROLLER)
        rules = _mock_rules_for_validated()
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 0

    def test_missing_valid_finds_issues(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITHOUT_VALID)
        rules = _mock_rules_for_validated()
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # createUser and updateUser

    def test_finding_includes_method_name(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITHOUT_VALID)
        rules = _mock_rules_for_validated()
        findings = JavaAnnotationScanner().scan(f, rules)
        method_names = [fi.method for fi in findings]
        assert "createUser" in method_names
        assert "updateUser" in method_names


# ── Return Type Tests ──────────────────────────────────────────

class TestJavaReturnTypeScanner:
    def test_no_result_wrapper(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_NO_RESULT_RETURN)
        rules = _mock_rules_for_result()
        findings = JavaReturnTypeScanner().scan(f, rules)
        assert len(findings) == 1
        assert findings[0].method == "getUser"

    def test_with_result_wrapper_no_findings(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_VALID_CONTROLLER)
        rules = _mock_rules_for_result()
        findings = JavaReturnTypeScanner().scan(f, rules)
        assert all(fi.code != "BE-QL-13" for fi in findings) or len(findings) == 0


# ── File Classification Tests ──────────────────────────────────

class TestFileClassification:
    def test_classify_controller(self):
        assert classify_files(["UserController.java"]) == {"controller": 1}

    def test_classify_service(self):
        assert classify_files(["UserServiceImpl.java", "UserService.java"]) == {"service": 2}

    def test_classify_mapper(self):
        assert classify_files(["UserMapper.java"]) == {"mapper": 1}

    def test_classify_entity(self):
        assert classify_files(["UserEntity.java"]) == {"entity": 1}

    def test_classify_dto(self):
        assert classify_files(["CreateUserDTO.java", "UserVO.java"]) == {"dto": 2}

    def test_classify_mixed(self):
        files = [
            "UserController.java",
            "UserServiceImpl.java",
            "UserMapper.java",
            "UserEntity.java",
            "UserDTO.java",
        ]
        result = classify_files(files)
        assert result["controller"] == 1
        assert result["service"] == 1
        assert result["mapper"] == 1
        assert result["entity"] == 1
        assert result["dto"] == 1


# ── Exclude Tests ──────────────────────────────────────────────

class TestShouldExclude:
    def test_exclude_test_directory(self):
        assert should_exclude("src/test/java/Test.java", ["**/test/**"]) is True

    def test_not_exclude_main_source(self):
        assert should_exclude("src/main/java/UserController.java", ["**/test/**"]) is False

    def test_fnmatch_wildcards(self):
        assert should_exclude("target/classes/Foo.class", ["**/target/**"]) is True


# ── Blocking Tests ──────────────────────────────────────────────

class TestIsBlocked:
    def test_strict_p1_is_blocked(self):
        findings = [Finding(code="BE-QL-29", level=Level.P1, line=10,
                            message="test", evidence="test")]
        assert is_blocked(findings, BlockingStrategy.STRICT) is True

    def test_strict_p2_is_blocked(self):
        findings = [Finding(code="BE-QL-08", level=Level.P2, line=10,
                            message="test", evidence="test")]
        assert is_blocked(findings, BlockingStrategy.STRICT) is False

    def test_normal_p1_not_blocked(self):
        findings = [Finding(code="BE-QL-29", level=Level.P1, line=10,
                            message="test", evidence="test")]
        assert is_blocked(findings, BlockingStrategy.NORMAL) is False

    def test_normal_p0_is_blocked(self):
        findings = [Finding(code="BE-QL-09", level=Level.P0, line=10,
                            message="test", evidence="test")]
        assert is_blocked(findings, BlockingStrategy.NORMAL) is True

    def test_loose_p1_not_blocked(self):
        findings = [Finding(code="BE-QL-29", level=Level.P1, line=10,
                            message="test", evidence="test")]
        assert is_blocked(findings, BlockingStrategy.LOOSE) is False

    def test_no_findings_not_blocked(self):
        assert is_blocked([], BlockingStrategy.STRICT) is False


# ── Integration Test ───────────────────────────────────────────

class TestScanSingleFile:
    def test_scan_with_multiple_rule_types(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITHOUT_VALID)
        rules = {
            **_mock_rules_for_sysout(),
            **_mock_rules_for_validated(),
        }
        findings = scan_single_file(f, rules)
        assert len(findings) == 2
        assert all(fi.code == "BE-QL-29" for fi in findings)

    def test_scan_autowired(self, tmp_path):
        f = _temp_java_file(tmp_path, JAVA_WITH_AUTOWIRED)
        rules = _mock_rules_for_autowired()
        findings = scan_single_file(f, rules)
        assert len(findings) == 1
        assert findings[0].evidence.strip() == "@Autowired"
