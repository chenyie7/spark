"""Tests for Java file scanner engine."""

import pytest
from pathlib import Path
from code_check.scanner import (
    scan_files,
    scan_single_file,
    TextGrepScanner,
    JavaAnnotationScanner,
    JavaReturnTypeScanner,
    classify_files,
    should_exclude,
    is_blocked,
)
from code_check.models import Level, BlockingStrategy, Finding, ScanResult


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


# ── P0-3: on_class class name matching ─────────────────────────

JAVA_ENTITY_WITHOUT_TABLELOGIC = """
package com.example.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.TableId;

@TableName("users")
public class UserEntity {
    @TableId
    private Long id;
    private String name;
    private Integer deleted;
}
"""

JAVA_MAPPER_WITH_MULTI_PARAM = """
package com.example.mapper;

import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserMapper {
    UserEntity selectByCondition(String name, Integer status);
}
"""


class TestOnClassClassNameMatching:
    """P0-3: on_class should match class names, not just annotations."""

    def test_on_class_matches_entity_class_name(self, tmp_path):
        """BE-QL-27: on_class '*Entity' should match class UserEntity."""
        f = _temp_java_file(tmp_path, JAVA_ENTITY_WITHOUT_TABLELOGIC)
        rules = {
            "BE-QL-27": {
                "description": "Entity 缺少 @TableLogic",
                "level": "P1",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Entity",
                    "required_field_annotation": "@TableLogic",
                },
                "message": "{class} 缺少 @TableLogic 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 1
        assert findings[0].code == "BE-QL-27"

    def test_on_class_matches_mapper_class_name(self, tmp_path):
        """BE-QL-44: on_class '*Mapper' should match interface UserMapper."""
        f = _temp_java_file(tmp_path, JAVA_MAPPER_WITH_MULTI_PARAM)
        rules = {
            "BE-QL-44": {
                "description": "Mapper 多参数缺 @Param",
                "level": "P1",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Mapper",
                    "target": "method_param",
                    "param_count_gte": 2,
                    "missing_annotation": "@Param",
                },
                "message": "{method} 缺少 @Param 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # both params missing @Param

    def test_on_class_still_matches_annotations(self, tmp_path):
        """on_class 'RestController|Controller' should still match annotations."""
        f = _temp_java_file(tmp_path, JAVA_WITHOUT_VALID)
        rules = _mock_rules_for_validated()
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # existing behavior preserved


# ── P1-1 + P1-5: Field-level annotation support ────────────────

JAVA_DTO_WITHOUT_SCHEMA = """
package com.example.dto;

public class CreateUserDTO {
    private String username;
    private String email;
    private Integer age;
}
"""

JAVA_DTO_WITH_SCHEMA = """
package com.example.dto;

import io.swagger.v3.oas.annotations.media.Schema;

public class CreateUserDTO {
    @Schema(description = "用户名")
    private String username;

    private String email;
}
"""


class TestFieldLevelAnnotations:
    """P1-1: target: field support for field-level annotation checks."""

    def test_target_field_reports_missing_schema(self, tmp_path):
        """BE-IN-04: DTO fields missing @Schema."""
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        f = _temp_java_file(dto_dir, JAVA_DTO_WITHOUT_SCHEMA, "CreateUserDTO.java")
        rules = {
            "BE-IN-04": {
                "description": "DTO 字段缺少 @Schema",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_dir": "dto",
                    "target": "field",
                    "missing_annotation": "@Schema",
                },
                "message": "{class}.{field} 缺少 @Schema",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 3  # username, email, age

    def test_target_field_no_findings_when_annotated(self, tmp_path):
        """DTO fields with @Schema should produce no findings for annotated fields."""
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        f = _temp_java_file(dto_dir, JAVA_DTO_WITH_SCHEMA, "CreateUserDTO.java")
        rules = {
            "BE-IN-04": {
                "description": "DTO 字段缺少 @Schema",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_dir": "dto",
                    "target": "field",
                    "missing_annotation": "@Schema",
                },
                "message": "{class}.{field} 缺少 @Schema",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        # username has @Schema, email doesn't → 1 finding
        assert len(findings) == 1

    def test_required_field_annotation_entity(self, tmp_path):
        """P1-5: required_field_annotation on Entity classes."""
        f = _temp_java_file(tmp_path, JAVA_ENTITY_WITHOUT_TABLELOGIC)
        rules = {
            "BE-QL-27": {
                "description": "Entity 缺少 @TableLogic",
                "level": "P1",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Entity",
                    "required_field_annotation": "@TableLogic",
                },
                "message": "{class} 缺少 @TableLogic 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 1
        assert "缺少 @TableLogic" in findings[0].evidence


# ── P1-2: on_dir filtering ─────────────────────────────────────


class TestOnDirFiltering:
    """P1-2: on_dir should filter files by directory."""

    def test_on_dir_matches_correct_directory(self, tmp_path):
        """File in 'dto' directory should match on_dir: 'dto'."""
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        f = _temp_java_file(dto_dir, JAVA_DTO_WITHOUT_SCHEMA, "CreateUserDTO.java")
        rules = {
            "BE-IN-04": {
                "description": "DTO 字段缺少 @Schema",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_dir": "dto",
                    "target": "field",
                    "missing_annotation": "@Schema",
                },
                "message": "{class}.{field} 缺少 @Schema",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 3

    def test_on_dir_skips_non_matching_directory(self, tmp_path):
        """File NOT in 'dto' directory should be skipped."""
        svc_dir = tmp_path / "service"
        svc_dir.mkdir()
        f = _temp_java_file(svc_dir, JAVA_DTO_WITHOUT_SCHEMA, "SomeService.java")
        rules = {
            "BE-IN-04": {
                "description": "DTO 字段缺少 @Schema",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_dir": "dto",
                    "target": "field",
                    "missing_annotation": "@Schema",
                },
                "message": "{class}.{field} 缺少 @Schema",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 0

    def test_on_dir_with_text_grep(self, tmp_path):
        """on_dir should work with text-grep scanner."""
        svc_dir = tmp_path / "service"
        svc_dir.mkdir()
        f = _temp_java_file(svc_dir, JAVA_WITH_AUTOWIRED)
        rules = {
            "BE-AU-15": {
                "description": "权限注解在 Service 层",
                "level": "P1",
                "program": {
                    "scanner": "text-grep",
                    "on_dir": "service",
                    "pattern": "@Autowired",
                },
                "message": "Service 层不应有 @Autowired",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 1

    def test_on_dir_pipe_separated(self, tmp_path):
        """on_dir 'config|security' should match either directory."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        f = _temp_java_file(config_dir, JAVA_WITH_AUTOWIRED)
        rules = {
            "BE-AU-07": {
                "description": "检查 BCrypt",
                "level": "P0",
                "program": {
                    "scanner": "text-grep",
                    "on_dir": "config|security",
                    "pattern": "BCryptPasswordEncoder",
                    "must_match": True,
                },
                "message": "密码未使用 BCryptPasswordEncoder",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        # must_match=True, pattern not found → 1 finding
        assert len(findings) == 1


# ── P1-3: Method-level annotation checks ───────────────────────

JAVA_CONTROLLER_WITHOUT_OPERATION = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public Result getUser(@PathVariable Long id) {
        return Result.success();
    }

    @PostMapping
    public Result createUser(@RequestBody CreateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_CONTROLLER_WITH_GETMAPPING = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public Result getUser(@PathVariable Long id) {
        return Result.success();
    }

    @GetMapping("/search")
    public Result search(@RequestParam String keyword) {
        return Result.success();
    }
}
"""


class TestMethodLevelAnnotations:
    """P1-3: on_public_method and on_method_annotation support."""

    def test_on_public_method_reports_missing_operation(self, tmp_path):
        """BE-IN-02: public methods missing @Operation."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_WITHOUT_OPERATION)
        rules = {
            "BE-IN-02": {
                "description": "Controller 方法缺少 @Operation",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "RestController|Controller",
                    "on_public_method": True,
                    "missing_annotation": "@Operation",
                },
                "message": "{method} 缺少 @Operation 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # getUser and createUser

    def test_on_method_annotation_filters_methods(self, tmp_path):
        """BE-IN-03: only check @GetMapping methods for @Parameter on params."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_WITH_GETMAPPING)
        rules = {
            "BE-IN-03": {
                "description": "@PathVariable/@RequestParam 缺少 @Parameter",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_method_annotation": "GetMapping",
                    "target": "method_param",
                    "match_annotation": "PathVariable|RequestParam",
                    "missing_annotation": "@Parameter",
                },
                "message": "{method} 的 {param} 缺少 @Parameter 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # id (PathVariable) + keyword (RequestParam)

    def test_param_count_gte_filters_methods(self, tmp_path):
        """BE-QL-44: only check methods with >= 2 params."""
        f = _temp_java_file(tmp_path, JAVA_MAPPER_WITH_MULTI_PARAM)
        rules = {
            "BE-QL-44": {
                "description": "Mapper 多参数缺 @Param",
                "level": "P1",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Mapper",
                    "target": "method_param",
                    "param_count_gte": 2,
                    "missing_annotation": "@Param",
                },
                "message": "{method} 缺少 @Param 注解",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 2  # name and status params


# ── P1-4: on_method_name filtering ─────────────────────────────

JAVA_CONTROLLER_WITH_PAGE = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/page")
    public Result<PageResult<UserVO>> pageUsers(@RequestParam int page, @RequestParam int size) {
        return Result.success();
    }

    @GetMapping("/list")
    public List listUsers() {
        return List.of();
    }

    @GetMapping("/{id}")
    public Result<UserVO> getById(@PathVariable Long id) {
        return Result.success();
    }
}
"""


class TestOnMethodNameFiltering:
    """P1-4: on_method_name filtering in JavaReturnTypeScanner."""

    def test_on_method_name_filters_page_list_methods(self, tmp_path):
        """BE-QL-16: only check page|list methods for PageResult<."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_WITH_PAGE)
        rules = {
            "BE-QL-16": {
                "description": "分页查询应返回 Result<PageResult<T>>",
                "level": "P2",
                "program": {
                    "scanner": "java-return-type",
                    "on_class": "RestController|Controller",
                    "on_method_name": "page|list",
                    "required_return_pattern": "PageResult<",
                },
                "message": "{method} 分页查询应返回 Result<PageResult<T>>",
            }
        }
        findings = JavaReturnTypeScanner().scan(f, rules)
        # pageUsers returns PageResult (no issue), listUsers returns List (issue)
        # getById returns Result (but method name doesn't match filter, skipped)
        assert len(findings) == 1
        assert findings[0].method == "listUsers"

    def test_on_method_name_no_match_skips_all(self, tmp_path):
        """Methods not matching on_method_name should be skipped."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_WITH_PAGE)
        rules = {
            "BE-QL-16": {
                "description": "分页查询应返回 Result<PageResult<T>>",
                "level": "P2",
                "program": {
                    "scanner": "java-return-type",
                    "on_class": "RestController|Controller",
                    "on_method_name": "export|download",
                    "required_return_pattern": "Result<",
                },
                "message": "{method} 应返回 Result",
            }
        }
        findings = JavaReturnTypeScanner().scan(f, rules)
        assert len(findings) == 0


# ── P1-6: on_file_pattern + must_match ─────────────────────────


class TestOnFilePatternAndMustMatch:
    """P1-6: on_file_pattern filtering and must_match semantics."""

    def test_must_match_reports_when_pattern_absent(self, tmp_path):
        """must_match=True: report finding when pattern NOT found."""
        f = _temp_java_file(tmp_path, JAVA_WITH_SYSOUT)
        rules = {
            "BE-QL-17": {
                "description": "分页 DTO 应继承 PageQueryDTO",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "pattern": "extends\\s+PageQueryDTO",
                    "must_match": True,
                },
                "message": "分页 DTO 应继承 PageQueryDTO",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 1
        assert "未找到匹配" in findings[0].evidence

    def test_must_match_no_finding_when_pattern_found(self, tmp_path):
        """must_match=True: no finding when pattern IS present."""
        content = """
        package com.example.dto;
        public class UserPageDTO extends PageQueryDTO {
            private String name;
        }
        """
        f = _temp_java_file(tmp_path, content)
        rules = {
            "BE-QL-17": {
                "description": "分页 DTO 应继承 PageQueryDTO",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "pattern": "extends\\s+PageQueryDTO",
                    "must_match": True,
                },
                "message": "分页 DTO 应继承 PageQueryDTO",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 0

    def test_on_file_pattern_filters_by_filename(self, tmp_path):
        """on_file_pattern restricts to files matching the regex."""
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        f = _temp_java_file(
            dto_dir, JAVA_ENTITY_WITHOUT_TABLELOGIC, "UserPageDTO.java"
        )
        rules = {
            "BE-QL-17": {
                "description": "分页 DTO 应继承 PageQueryDTO",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_dir": "dto",
                    "pattern": "extends\\s+PageQueryDTO",
                    "on_file_pattern": ".*(Page|Query|Search).*DTO\\.java",
                    "must_match": True,
                },
                "message": "分页 DTO 应继承 PageQueryDTO",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        # UserPageDTO.java matches the file pattern, and must_match finds no
        # PageQueryDTO → reports finding
        assert len(findings) == 1

    def test_on_file_pattern_skips_non_matching_files(self, tmp_path):
        """Files not matching on_file_pattern should be skipped."""
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        f = _temp_java_file(dto_dir, JAVA_DTO_WITHOUT_SCHEMA, "CreateUserDTO.java")
        rules = {
            "BE-QL-17": {
                "description": "分页 DTO 应继承 PageQueryDTO",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_dir": "dto",
                    "pattern": "extends\\s+PageQueryDTO",
                    "on_file_pattern": ".*(Page|Query|Search).*DTO\\.java",
                    "must_match": True,
                },
                "message": "分页 DTO 应继承 PageQueryDTO",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        # CreateUserDTO.java doesn't match file pattern → skipped
        assert len(findings) == 0


# ── P0-1: New scanner types ────────────────────────────────────

from code_check.scanner import (
    PackageStructureScanner,
    FileNamingScanner,
    ConfigCheckScanner,
)


class TestPackageStructureScanner:
    """P0-1: PackageStructureScanner for directory structure checks."""

    def test_required_dirs_all_present(self, tmp_path):
        """No findings when all required dirs exist."""
        # Create package structure
        pkg = tmp_path / "com" / "example"
        pkg.mkdir(parents=True)
        for d in ["controller", "service", "mapper", "entity", "dto", "vo"]:
            (pkg / d).mkdir()
        (pkg / "service" / "impl").mkdir()
        # Add a Java file so the scanner picks up this directory
        (pkg / "controller" / "TestController.java").write_text("package com.example.controller;")
        (pkg / "Application.java").write_text("package com.example;")

        rules = {
            "BE-ST-01": {
                "description": "包结构检查",
                "level": "P1",
                "program": {
                    "scanner": "package-structure",
                    "required_dirs": "controller|service|mapper|entity|dto|vo",
                    "required_service_impl": True,
                },
                "message": "包结构不符合规范",
            }
        }
        findings = PackageStructureScanner().scan_directory(pkg, rules)
        assert len(findings) == 0

    def test_missing_directories_reported(self, tmp_path):
        """Findings when required dirs are missing."""
        pkg = tmp_path / "com" / "example"
        pkg.mkdir(parents=True)
        for d in ["controller", "service"]:
            (pkg / d).mkdir()
        (pkg / "controller" / "TestController.java").write_text("package com.example.controller;")
        (pkg / "Application.java").write_text("package com.example;")

        rules = {
            "BE-ST-01": {
                "description": "包结构检查",
                "level": "P1",
                "program": {
                    "scanner": "package-structure",
                    "required_dirs": "controller|service|mapper|entity|dto|vo",
                    "required_service_impl": True,
                },
                "message": "包结构不符合规范",
            }
        }
        findings = PackageStructureScanner().scan_directory(pkg, rules)
        # missing: mapper, entity, dto, vo dirs + missing service/impl = 2 findings
        assert len(findings) == 2
        assert "mapper" in findings[0].evidence

    def test_missing_service_impl_reported(self, tmp_path):
        """Finding when service/impl is missing."""
        pkg = tmp_path / "com" / "example"
        pkg.mkdir(parents=True)
        for d in ["controller", "service", "mapper", "entity", "dto", "vo"]:
            (pkg / d).mkdir()
        (pkg / "service" / "SomeService.java").write_text("package com.example.service;")
        (pkg / "Application.java").write_text("package com.example;")

        rules = {
            "BE-ST-02": {
                "description": "缺少 service/impl",
                "level": "P1",
                "program": {
                    "scanner": "package-structure",
                    "check_impl_subdir": True,
                },
                "message": "缺少 service/impl 子包",
            }
        }
        findings = PackageStructureScanner().scan_directory(pkg, rules)
        assert len(findings) == 1
        assert "impl" in findings[0].evidence

    def test_scan_method_returns_empty(self, tmp_path):
        """Per-file scan() returns empty; real logic in scan_directory()."""
        f = _temp_java_file(tmp_path, JAVA_WITH_SYSOUT)
        rules = {
            "BE-ST-01": {
                "description": "包结构检查",
                "level": "P1",
                "program": {
                    "scanner": "package-structure",
                    "required_dirs": "controller",
                },
                "message": "包结构不符合规范",
            }
        }
        findings = PackageStructureScanner().scan(f, rules)
        assert len(findings) == 0


class TestFileNamingScanner:
    """P0-1: FileNamingScanner for file naming conventions."""

    def test_file_matches_naming_pattern(self, tmp_path):
        """No findings when file matches the expected pattern."""
        f = _temp_java_file(tmp_path, JAVA_WITH_VALID_CONTROLLER, "UserController.java")
        rules = {
            "BE-ST-14": {
                "description": "Controller 命名",
                "level": "P2",
                "program": {
                    "scanner": "file-naming",
                    "on_dir": "controller",
                    "pattern": "*Controller.java",
                },
                "message": "不符合 Controller 命名规范",
            }
        }
        findings = FileNamingScanner().scan(f, rules)
        # File is not in a 'controller' directory by default (tmp_path has no
        # controller parent), so on_dir filtering skips it
        assert len(findings) == 0

    def test_file_in_wrong_directory_skipped_by_on_dir(self, tmp_path):
        """File not in the right directory is skipped."""
        ctrl_dir = tmp_path / "controller"
        ctrl_dir.mkdir()
        f = _temp_java_file(ctrl_dir, JAVA_WITH_VALID_CONTROLLER, "UserController.java")
        rules = {
            "BE-ST-14": {
                "description": "Controller 命名",
                "level": "P2",
                "program": {
                    "scanner": "file-naming",
                    "on_dir": "controller",
                    "pattern": "*Controller.java",
                },
                "message": "不符合 Controller 命名规范",
            }
        }
        findings = FileNamingScanner().scan(f, rules)
        assert len(findings) == 0  # Matches pattern and on_dir

    def test_file_naming_mismatch_reported(self, tmp_path):
        """Finding when file doesn't match naming convention."""
        ctrl_dir = tmp_path / "controller"
        ctrl_dir.mkdir()
        f = _temp_java_file(
            ctrl_dir, JAVA_WITH_VALID_CONTROLLER, "UserCtrl.java"
        )
        rules = {
            "BE-ST-14": {
                "description": "Controller 命名",
                "level": "P2",
                "program": {
                    "scanner": "file-naming",
                    "on_dir": "controller",
                    "pattern": "*Controller.java",
                },
                "message": "不符合 Controller 命名规范",
            }
        }
        findings = FileNamingScanner().scan(f, rules)
        assert len(findings) == 1
        assert "命名规范" in findings[0].message

    def test_must_not_match_reports_on_match(self, tmp_path):
        """BE-AU-05: must_not_match reports when pattern IS matched."""
        f = _temp_java_file(
            tmp_path, JAVA_WITH_VALID_CONTROLLER, "SaTokenConfig.java"
        )
        rules = {
            "BE-AU-05": {
                "description": "Sa-Token 配置命名",
                "level": "P0",
                "program": {
                    "scanner": "file-naming",
                    "pattern": "*SaToken*Config*.java",
                    "exclude_pattern": "SaTokenCustomConfig.java",
                    "must_not_match": True,
                },
                "message": "配置类应命名为 SaTokenCustomConfig",
            }
        }
        findings = FileNamingScanner().scan(f, rules)
        assert len(findings) == 1

    def test_exclude_pattern_skips_file(self, tmp_path):
        """Exclude pattern prevents matching."""
        f = _temp_java_file(
            tmp_path, JAVA_WITH_VALID_CONTROLLER, "SaTokenCustomConfig.java"
        )
        rules = {
            "BE-AU-05": {
                "description": "Sa-Token 配置命名",
                "level": "P0",
                "program": {
                    "scanner": "file-naming",
                    "pattern": "*SaToken*Config*.java",
                    "exclude_pattern": "SaTokenCustomConfig.java",
                    "must_not_match": True,
                },
                "message": "配置类应命名为 SaTokenCustomConfig",
            }
        }
        findings = FileNamingScanner().scan(f, rules)
        assert len(findings) == 0  # Excluded


class TestConfigCheckScanner:
    """P0-1: ConfigCheckScanner for config file checks."""

    def test_must_not_match_reports_security_issue(self, tmp_path):
        """BE-IN-08: report plaintext passwords in config files."""
        config_dir = tmp_path / "resources"
        config_dir.mkdir()
        app_yml = config_dir / "application.yml"
        app_yml.write_text("""
spring:
  datasource:
    password: mysecret123
""")

        rules = {
            "BE-IN-08": {
                "description": "配置文件包含明文密码",
                "level": "P0",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml|*.yaml",
                    "pattern": "(password|passwd|secret)\\s*[:=]\\s*(?!\\$\\{)[^\\s]+",
                    "must_not_match": True,
                },
                "message": "配置文件包含明文敏感信息",
            }
        }
        findings = ConfigCheckScanner().scan_directory(tmp_path, rules)
        # tmp_path glob won't find files in subdirs, let's check base path
        # The scanner uses base_path.rglob, so it should find application.yml
        # in the resources subdirectory
        assert len(findings) >= 1
        assert any("password" in f.evidence.lower() for f in findings)

    def test_no_finding_when_using_env_placeholder(self, tmp_path):
        """No finding when password uses ${ENV_VAR} placeholder."""
        config_dir = tmp_path / "resources"
        config_dir.mkdir()
        app_yml = config_dir / "application.yml"
        app_yml.write_text("""
spring:
  datasource:
    password: ${DB_PASSWORD}
""")

        rules = {
            "BE-IN-08": {
                "description": "配置文件包含明文密码",
                "level": "P0",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml|*.yaml",
                    "pattern": "(password|passwd|secret)\\s*[:=]\\s*(?!\\$\\{)[^\\s]+",
                    "must_not_match": True,
                },
                "message": "配置文件包含明文敏感信息",
            }
        }
        findings = ConfigCheckScanner().scan_directory(tmp_path, rules)
        # ${DB_PASSWORD} matches (?!\$\{) negative lookahead? No, it starts with ${
        # So the regex won't match → no finding
        assert len(findings) == 0

    def test_scan_method_returns_empty(self, tmp_path):
        """Per-file scan() returns empty; real logic in scan_directory()."""
        f = _temp_java_file(tmp_path, JAVA_WITH_SYSOUT)
        rules = {
            "BE-IN-08": {
                "description": "明文密码",
                "level": "P0",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml",
                    "pattern": "password",
                    "must_not_match": True,
                },
                "message": "配置文件包含明文敏感信息",
            }
        }
        findings = ConfigCheckScanner().scan(f, rules)
        assert len(findings) == 0


# ── P0-1: re.error crash fix ───────────────────────────────────

from code_check.scanner import _on_class_matches, _any_match, _class_name_matches


class TestReErrorCrashFix:
    """P0-1: _any_match/_class_name_matches must not crash on invalid regex."""

    def test_on_class_with_unbalanced_parens_does_not_crash(self):
        """BE-QL-38 on_class with .*(Constant|Constants|Code|Codes) must not crash."""
        # The pattern .*(Constant|Constants|Code|Codes) split by | produces
        # "Codes)" which is an invalid regex (unbalanced paren).
        # This must not raise re.error.
        result = _on_class_matches(
            ["Component"], "UserService",
            ".*(Constant|Constants|Code|Codes)"
        )
        # Should not crash and should return False (UserService doesn't match)
        assert result is False

    def test_on_class_with_valid_pattern_still_works(self):
        """Normal patterns should still match correctly after the fix."""
        # "RestController|Controller" should match @RestController annotation
        result = _on_class_matches(
            ["RestController"], "UserController",
            "RestController|Controller"
        )
        assert result is True

    def test_class_name_matches_with_invalid_regex_does_not_crash(self):
        """_class_name_matches must handle "Codes)" gracefully."""
        result = _class_name_matches("UserService", ".*(Constant|Constants|Code|Codes)")
        assert result is False

    def test_class_name_matches_with_valid_pattern(self):
        """_class_name_matches should still match valid patterns."""
        result = _class_name_matches("UserMapper", "*Mapper")
        assert result is True


# ── P0-2: _find_methods line number accuracy ────────────────────

JAVA_WITH_COMMENTS = """
package com.example;

/**
 * Javadoc comment block
 * that spans multiple lines
 */
public class TestService {

    // Single line comment
    public void doSomething() {
        System.out.println("hello");
    }

    /*
     * Multi-line block comment
     */
    public String getValue() {
        return "value";
    }
}
"""


class TestFindMethodsLineNumbers:
    """P0-2: _find_methods should return accurate line numbers."""

    def test_method_line_numbers_are_accurate(self):
        """Line numbers should be close to actual source positions."""
        from code_check.scanner import _find_methods
        methods = _find_methods(JAVA_WITH_COMMENTS)
        assert len(methods) == 2
        do_something = [m for m in methods if m["name"] == "doSomething"][0]
        get_value = [m for m in methods if m["name"] == "getValue"][0]
        # getValue must come after doSomething
        assert get_value["line_num"] > do_something["line_num"]
        # Line numbers should be reasonable (not wildly off)
        assert do_something["line_num"] >= 7
        assert get_value["line_num"] > 10

    def test_return_type_does_not_include_modifier(self):
        """P0-3: return_type should be just the type, not 'public Type'."""
        from code_check.scanner import _find_methods
        methods = _find_methods(JAVA_WITH_COMMENTS)
        for m in methods:
            # return_type should NOT start with "public", "private", "protected"
            assert not m["return_type"].startswith("public")
            assert not m["return_type"].startswith("private")
            assert m["return_type"] in ("void", "String")


# ── P0-4: check_group_present ───────────────────────────────────

JAVA_WITH_VALIDATED_NO_GROUP = """
package com.example.controller;

import org.springframework.validation.annotation.Validated;
import jakarta.validation.Valid;

@RestController
public class UserController {

    @PostMapping
    public Result createUser(@Validated CreateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_WITH_VALIDATED_WITH_GROUP = """
package com.example.controller;

import org.springframework.validation.annotation.Validated;
import jakarta.validation.Valid;

@RestController
public class UserController {

    @PostMapping
    public Result createUser(@Validated(Create.class) CreateUserDTO dto) {
        return Result.success();
    }
}
"""


class TestCheckGroupPresent:
    """P0-4: BE-QL-30 check_group_present must detect @Validated without group."""

    def test_validated_without_group_reports_finding(self, tmp_path):
        """@Validated without group parameter should produce a finding."""
        f = _temp_java_file(tmp_path, JAVA_WITH_VALIDATED_NO_GROUP)
        rules = {
            "BE-QL-30": {
                "description": "@Validated 未指定分组",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "RestController|Controller",
                    "target": "method_param",
                    "match_param_type": "DTO|Request|Command",
                    "check_group_present": True,
                },
                "message": "{method} 的 @Validated 未指定分组",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 1
        assert "未指定分组" in findings[0].evidence
        assert findings[0].method == "createUser"

    def test_validated_with_group_no_finding(self, tmp_path):
        """@Validated(Create.class) should NOT produce a finding."""
        f = _temp_java_file(tmp_path, JAVA_WITH_VALIDATED_WITH_GROUP)
        rules = {
            "BE-QL-30": {
                "description": "@Validated 未指定分组",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "RestController|Controller",
                    "target": "method_param",
                    "match_param_type": "DTO|Request|Command",
                    "check_group_present": True,
                },
                "message": "{method} 的 @Validated 未指定分组",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 0


# ── P0-5: required_class_modifier + required_private_constructor ─

JAVA_CONSTANTS_WITHOUT_FINAL = """
package com.example.constant;

public class UserConstants {
    public static final String DEFAULT_NAME = "unknown";
    private UserConstants() {}
}
"""

JAVA_CONSTANTS_WITHOUT_PRIVATE_CTOR = """
package com.example.constant;

public final class UserConstants {
    public static final String DEFAULT_NAME = "unknown";
    public UserConstants() {}
}
"""

JAVA_CONSTANTS_CORRECT = """
package com.example.constant;

public final class UserConstants {
    public static final String DEFAULT_NAME = "unknown";
    private UserConstants() {}
}
"""


class TestRequiredClassModifier:
    """P0-5: BE-QL-38 required_class_modifier and required_private_constructor."""

    def test_missing_final_modifier_reported(self, tmp_path):
        """Class without final modifier should be reported."""
        f = _temp_java_file(tmp_path, JAVA_CONSTANTS_WITHOUT_FINAL)
        rules = {
            "BE-QL-38": {
                "description": "常量类应 final + 私有构造",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Constants",
                    "required_class_modifier": "final",
                },
                "message": "常量类应声明为 final + 私有构造",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 1
        assert "final" in findings[0].evidence

    def test_missing_private_constructor_reported(self, tmp_path):
        """Class without private constructor should be reported."""
        f = _temp_java_file(tmp_path, JAVA_CONSTANTS_WITHOUT_PRIVATE_CTOR)
        rules = {
            "BE-QL-38": {
                "description": "常量类应 final + 私有构造",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Constants",
                    "required_private_constructor": True,
                },
                "message": "常量类应声明为 final + 私有构造",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 1
        assert "私有构造" in findings[0].evidence

    def test_correct_constants_class_no_findings(self, tmp_path):
        """Correct final class with private constructor → no findings."""
        f = _temp_java_file(tmp_path, JAVA_CONSTANTS_CORRECT)
        rules = {
            "BE-QL-38": {
                "description": "常量类应 final + 私有构造",
                "level": "P2",
                "program": {
                    "scanner": "java-annotation",
                    "on_class": "*Constants",
                    "required_class_modifier": "final",
                    "required_private_constructor": True,
                },
                "message": "常量类应声明为 final + 私有构造",
            }
        }
        findings = JavaAnnotationScanner().scan(f, rules)
        assert len(findings) == 0


# ── P0-6: nested YAML matching ──────────────────────────────────

from code_check.scanner import _find_nested_yaml


class TestNestedYamlMatching:
    """P0-6: ConfigCheckScanner should handle nested YAML patterns."""

    def test_nested_yaml_found(self):
        """_find_nested_yaml should find knife4j.enable in nested format."""
        content = """spring:
  application:
    name: myapp
knife4j:
  enable: true
"""
        lineno = _find_nested_yaml(
            content, r"knife4j\.enable\s*:\s*true"
        )
        assert lineno is not None
        assert lineno > 3

    def test_nested_yaml_not_found(self):
        """_find_nested_yaml returns None when nested pattern absent."""
        content = """spring:
  application:
    name: myapp
knife4j:
  enable: false
"""
        lineno = _find_nested_yaml(
            content, r"knife4j\.enable\s*:\s*true"
        )
        assert lineno is None

    def test_flat_format_still_handled(self):
        """The scanner handles flat format (this is not nested, so None)."""
        content = """knife4j.enable: true"""
        # Flat format is not detected by _find_nested_yaml (line-by-line handles it)
        lineno = _find_nested_yaml(
            content, r"knife4j\.enable\s*:\s*true"
        )
        assert lineno is None  # not in nested format

    def test_config_scanner_detects_nested_yaml_must_not_match(self, tmp_path):
        """ConfigCheckScanner should flag knife4j.enable=true in nested format."""
        config_dir = tmp_path / "resources"
        config_dir.mkdir()
        app_yml = config_dir / "application-prod.yml"
        app_yml.write_text("""spring:
  datasource:
    url: jdbc:mysql://localhost/db
knife4j:
  enable: true
""")

        rules = {
            "BE-IN-07": {
                "description": "生产环境 knife4j.enable 应为 false",
                "level": "P1",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml|*.yaml",
                    "pattern": r"knife4j\.enable\s*:\s*true",
                    "must_not_match": True,
                },
                "message": "生产环境 knife4j.enable 应为 false",
            }
        }
        findings = ConfigCheckScanner().scan_directory(tmp_path, rules)
        assert len(findings) >= 1


# ── P1-2: _matches_on_dir exact match ───────────────────────────

from code_check.scanner import _matches_on_dir


class TestMatchesOnDirExact:
    """P1-2: _matches_on_dir should not match substrings."""

    def test_exact_match_works(self):
        """'service' should match directory named 'service'."""
        assert _matches_on_dir(Path("/src/service/Test.java"), "service") is True

    def test_substring_not_matched(self):
        """'service' should NOT match directory named 'webservice'."""
        assert _matches_on_dir(Path("/src/webservice/Test.java"), "service") is False

    def test_pipe_separated_patterns(self):
        """Pipe-separated patterns should each require exact match."""
        assert _matches_on_dir(Path("/src/config/SecurityConfig.java"), "config|security") is True
        assert _matches_on_dir(Path("/src/security/AuthFilter.java"), "config|security") is True
        assert _matches_on_dir(Path("/src/service/UserService.java"), "config|security") is False

    def test_glob_pattern_still_works(self):
        """Glob patterns like '*impl*' should still work."""
        assert _matches_on_dir(Path("/src/impl/UserServiceImpl.java"), "*impl*") is True
        assert _matches_on_dir(Path("/src/service/UserService.java"), "*impl*") is False


# ── P1-3: ConfigCheckScanner exclude ────────────────────────────


class TestConfigCheckExclude:
    """P1-3: ConfigCheckScanner should respect exclude patterns."""

    def test_excluded_directories_skipped(self, tmp_path):
        """Files in excluded directories should not be scanned."""
        config_dir = tmp_path / "target" / "classes"
        config_dir.mkdir(parents=True)
        app_yml = config_dir / "application.yml"
        app_yml.write_text("password: mysecret123")

        rules = {
            "BE-IN-08": {
                "description": "配置文件包含明文密码",
                "level": "P0",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml|*.yaml",
                    "pattern": "(password|passwd)\\s*[:=]\\s*(?!\\$\\{)[^\\s]+",
                    "must_not_match": True,
                },
                "message": "配置文件包含明文敏感信息",
            }
        }
        findings = ConfigCheckScanner().scan_directory(
            tmp_path, rules, exclude_patterns=["**/target/**"]
        )
        assert len(findings) == 0

    def test_non_excluded_directories_still_scanned(self, tmp_path):
        """Files not in excluded dirs should be scanned."""
        config_dir = tmp_path / "resources"
        config_dir.mkdir()
        app_yml = config_dir / "application.yml"
        app_yml.write_text("password: mysecret123")

        rules = {
            "BE-IN-08": {
                "description": "配置文件包含明文密码",
                "level": "P0",
                "program": {
                    "scanner": "config-check",
                    "file_pattern": "*.yml|*.yaml",
                    "pattern": "(password|passwd)\\s*[:=]\\s*(?!\\$\\{)[^\\s]+",
                    "must_not_match": True,
                },
                "message": "配置文件包含明文敏感信息",
            }
        }
        findings = ConfigCheckScanner().scan_directory(
            tmp_path, rules, exclude_patterns=["**/target/**"]
        )
        assert len(findings) >= 1


# ── P1-1: _get_fields line number accuracy ──────────────────────

JAVA_DTO_WITH_COMMENTED_FIELDS = """
package com.example.dto;

/**
 * DTO for creating users.
 */
public class CreateUserDTO {
    // Username field
    private String username;

    /**
     * Email address
     */
    private String email;

    private Integer age;
}
"""


class TestGetFieldsLineNumbers:
    """P1-1: _get_fields should return accurate line numbers."""

    def test_field_line_numbers_are_accurate(self):
        """Field line numbers should be in correct relative order."""
        from code_check.scanner import _get_fields
        fields = _get_fields(JAVA_DTO_WITH_COMMENTED_FIELDS)
        assert len(fields) == 3
        names_and_lines = {f["name"]: f["line_num"] for f in fields}
        # Fields should be in correct order
        assert names_and_lines["username"] < names_and_lines["email"]
        assert names_and_lines["email"] < names_and_lines["age"]
        # Line numbers should be positive and reasonable
        for name, lineno in names_and_lines.items():
            assert lineno > 0, f"{name} line {lineno} should be > 0"


# ── BE-QL-15: TextGrepScanner on_class + on_method_annotation ───

JAVA_CONTROLLER_WRITE_METHODS = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(@RequestBody CreateUserDTO dto) {
        return Result.success();
    }

    @PutMapping("/{id}")
    public Result<Void> updateUser(@PathVariable Long id, @RequestBody UpdateUserDTO dto) {
        return Result.success();
    }

    @DeleteMapping("/{id}")
    public Result<Void> deleteUser(@PathVariable Long id) {
        return Result.success(id);
    }

    @GetMapping("/{id}")
    public Result<UserVO> getUser(@PathVariable Long id) {
        return Result.success(new UserVO());
    }
}
"""

JAVA_CONTROLLER_MISSING_RESULT_SUCCESS = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(@RequestBody CreateUserDTO dto) {
        return Result.success(dto);
    }

    @PutMapping("/{id}")
    public Result<Void> updateUser(@PathVariable Long id, @RequestBody UpdateUserDTO dto) {
        return Result.success("ok");
    }
}
"""


class TestTextGrepOnClassAndMethodAnnotation:
    """BE-QL-15: TextGrepScanner with on_class + on_method_annotation + must_match."""

    def test_on_class_filters_by_annotation(self, tmp_path):
        """on_class should restrict to files with matching class annotations."""
        f = _temp_java_file(tmp_path, JAVA_WITH_AUTOWIRED)
        rules = {
            "BE-QL-15": {
                "description": "写操作应返回 Result.success()",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_class": "RestController|Controller",
                    "pattern": "@Autowired",
                },
                "message": "test",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        # Service class doesn't have @RestController → skipped
        assert len(findings) == 0

    def test_on_method_annotation_must_match_finds_correct_methods(self, tmp_path):
        """must_match with on_method_annotation checks each annotated method."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_WRITE_METHODS)
        rules = {
            "BE-QL-15": {
                "description": "写操作应返回 Result.success() 无 data",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_class": "RestController|Controller",
                    "on_method_annotation": "PostMapping|PutMapping|DeleteMapping",
                    "pattern": r"return\s+Result\.success\(\s*\)",
                    "must_match": True,
                },
                "message": "{method} 应使用 Result.success() 无 data 返回",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        # deleteUser returns Result.success(id) — not empty → finding
        assert len(findings) == 1
        assert findings[0].method == "deleteUser"

    def test_on_method_annotation_must_match_all_pass(self, tmp_path):
        """When all annotated methods have the pattern, no findings."""
        content = """package com.example.controller;
@RestController
public class UserController {
    @PostMapping
    public Result create() {
        return Result.success();
    }
    @DeleteMapping
    public Result delete() {
        return Result.success();
    }
}
"""
        f = _temp_java_file(tmp_path, content)
        rules = {
            "BE-QL-15": {
                "description": "写操作应返回 Result.success() 无 data",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_class": "RestController|Controller",
                    "on_method_annotation": "PostMapping|DeleteMapping",
                    "pattern": r"return\s+Result\.success\(\s*\)",
                    "must_match": True,
                },
                "message": "{method} 应使用 Result.success() 无 data 返回",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 0

    def test_missing_both_patterns_reports_all(self, tmp_path):
        """All annotated methods missing pattern → all reported."""
        f = _temp_java_file(tmp_path, JAVA_CONTROLLER_MISSING_RESULT_SUCCESS)
        rules = {
            "BE-QL-15": {
                "description": "写操作应返回 Result.success() 无 data",
                "level": "P2",
                "program": {
                    "scanner": "text-grep",
                    "on_class": "RestController|Controller",
                    "on_method_annotation": "PostMapping|PutMapping",
                    "pattern": r"return\s+Result\.success\(\s*\)",
                    "must_match": True,
                },
                "message": "{method} 应使用 Result.success() 无 data 返回",
            }
        }
        findings = TextGrepScanner().scan(f, rules)
        assert len(findings) == 2
        method_names = {f.method for f in findings}
        assert "createUser" in method_names
        assert "updateUser" in method_names


# ── P2-8: Generic type params parsing ───────────────────────────

from code_check.scanner import _parse_params


class TestParseParamsGenerics:
    """P2-8: _parse_params should handle generic type parameters."""

    def test_simple_params(self):
        """Simple parameters without generics."""
        params = _parse_params("String name, Integer age")
        assert len(params) == 2
        assert params[0]["type"] == "String"
        assert params[0]["name"] == "name"

    def test_generic_param(self):
        """Single generic parameter."""
        params = _parse_params("List<CreateUserDTO> dtos")
        assert len(params) == 1
        assert params[0]["type"] == "List<CreateUserDTO>"
        assert params[0]["name"] == "dtos"

    def test_nested_generic_param(self):
        """Nested generic parameters with commas inside angle brackets."""
        params = _parse_params("Map<String, Integer> map, String name")
        assert len(params) == 2
        assert params[0]["type"] == "Map<String, Integer>"
        assert params[0]["name"] == "map"
        assert params[1]["name"] == "name"

    def test_annotated_generic_param(self):
        """Generic param with annotations."""
        params = _parse_params("@Valid List<CreateUserDTO> dtos")
        assert len(params) == 1
        assert params[0]["type"] == "List<CreateUserDTO>"
        assert params[0]["name"] == "dtos"
        assert "Valid" in params[0]["annotations"]
