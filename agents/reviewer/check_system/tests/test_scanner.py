"""Tests for JavaAstScanner and retained scanners."""

import pytest
from pathlib import Path
from code_check.scanner import (
    scan_files,
    scan_single_file,
    JavaAstScanner,
    PackageStructureScanner,
    FileNamingScanner,
    ConfigCheckScanner,
    classify_files,
    should_exclude,
    is_blocked,
    SCANNERS,
    _any_match,
    _find_nested_yaml,
    _matches_on_dir,
)
from code_check.models import Level, BlockingStrategy, Finding


# ── Test Java Sources ──

JAVA_CONTROLLER_WITH_AUTOWIRED = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.example.service.UserService;

@RestController
@RequestMapping("/users")
public class UserController {

    @Autowired
    private UserService userService;
}
"""

JAVA_INTERFACE_SERVICE = """
package com.example.service;

import com.example.vo.UserVO;

public interface UserService {
    UserVO getUser(Long id);
}
"""

JAVA_SERVICE_WITH_SLF4J = """
package com.example.service.impl;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserServiceImpl {
    public void doSomething() {
        log.info("processing");
    }
}
"""

JAVA_SERVICE_WITHOUT_SLF4J = """
package com.example.service.impl;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserServiceImpl {
    public void doSomething() {
    }
}
"""

JAVA_DTO_WITH_SCHEMA = """
package com.example.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

public class RegisterDTO {

    @Schema(description = "用户名")
    @NotBlank
    private String username;

    @Schema(description = "密码")
    @NotBlank
    private String password;

    private static final int USERNAME_MIN_LENGTH = 3;
}
"""

JAVA_DTO_WITHOUT_SCHEMA = """
package com.example.dto;

import jakarta.validation.constraints.NotBlank;

public class LoginDTO {

    @NotBlank
    private String username;

    @NotBlank
    private String password;
}
"""

JAVA_WITH_SYSOUT = """
package com.example;

public class DebugService {
    public void debug() {
        System.out.println("debug info");
        System.err.println("error info");
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

JAVA_WITH_RESULT_RETURN = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import com.example.dto.UserVO;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public Result<UserVO> getUser(@PathVariable Long id) {
        return Result.success(new UserVO());
    }
}
"""

JAVA_ENTITY_WITH_TABLE_LOGIC = """
package com.example.entity;

import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("user")
public class UserEntity {
    private Long id;
    private String username;

    @TableLogic
    private Integer deleted;
}
"""

JAVA_ENTITY_WITHOUT_TABLE_LOGIC = """
package com.example.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("user")
public class UserEntity {
    private Long id;
    private String username;
    private Integer deleted;
}
"""

JAVA_WITH_BCRYPT = """
package com.example.service.impl;

import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserServiceImpl {

    private final BCryptPasswordEncoder passwordEncoder;

    public void register(String password) {
        String encoded = passwordEncoder.encode(password);
    }
}
"""

JAVA_WITHOUT_BCRYPT = """
package com.example.service.impl;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserServiceImpl {
    public void register(String password) {
        String encoded = password;
    }
}
"""

JAVA_CONSTANT_CLASS = """
package com.example.common;

public final class ErrorCodes {
    private ErrorCodes() {}

    public static final String USER_NOT_FOUND = "USER_NOT_FOUND";
    public static final String PASSWORD_ERROR = "PASSWORD_ERROR";
}
"""

JAVA_BAD_CONSTANT_CLASS = """
package com.example.common;

public class ErrorCodes {
    public static final String USER_NOT_FOUND = "USER_NOT_FOUND";
}
"""

JAVA_MAPPER_WITH_PARAM = """
package com.example.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.entity.UserEntity;
import org.apache.ibatis.annotations.Param;

public interface UserMapper extends BaseMapper<UserEntity> {
    UserEntity selectByUsernameAndStatus(
        @Param("username") String username,
        @Param("status") Integer status
    );
}
"""

JAVA_MAPPER_WITHOUT_PARAM = """
package com.example.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.entity.UserEntity;

public interface UserMapper extends BaseMapper<UserEntity> {
    UserEntity selectByUsernameAndStatus(String username, Integer status);
}
"""

JAVA_CONTROLLER_WITH_TAG = """
package com.example.controller;

import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

@Tag(name = "用户管理")
@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public String getUser(@PathVariable Long id) {
        return "user";
    }
}
"""

JAVA_WITH_VALUE_ANNOTATION = """
package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class AppConfig {
    @Value("${app.secret}")
    private String secret;
}
"""

JAVA_CONTROLLER_POST_RESULT = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import com.example.dto.CreateUserDTO;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(@Valid CreateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_CONTROLLER_POST_BAD_RESULT = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import com.example.dto.CreateUserDTO;

@RestController
@RequestMapping("/users")
public class UserController {

    @PostMapping
    public Result<Void> createUser(CreateUserDTO dto) {
        return Result.success("创建成功");
    }
}
"""


# ── Helper ─────────────────────────────────────────────────────

def _temp_java_file(tmp_path, content, name="Test.java"):
    """Write content to a temp Java file and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ═══════════════════════════════════════════════════════════════
# JavaAstScanner Tests
# ═══════════════════════════════════════════════════════════════

class TestJavaAstClassChecks:

    def test_autowired_field_detected(self, tmp_path):
        """BE-ST-22: @Autowired field injection should be detected."""
        rules = {
            "BE-ST-22": {
                "level": "P1",
                "message": "{class} 使用了 @Autowired",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "forbid_field_annotation": "@Autowired"
                }
            }
        }
        file_path = tmp_path / "UserController.java"
        file_path.write_text(JAVA_CONTROLLER_WITH_AUTOWIRED)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
        assert findings[0].code == "BE-ST-22"

    def test_required_args_constructor_skips_interface(self, tmp_path):
        """BE-ST-23: Interface should NOT be flagged for @RequiredArgsConstructor."""
        rules = {
            "BE-ST-23": {
                "level": "P1",
                "message": "{class} 应使用 @RequiredArgsConstructor",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "skip_interface": True,
                    "required_class_annotation": "@RequiredArgsConstructor"
                }
            }
        }
        iface_path = tmp_path / "UserService.java"
        iface_path.write_text(JAVA_INTERFACE_SERVICE)
        scanner = JavaAstScanner()
        findings = scanner.scan(iface_path, rules)
        assert len(findings) == 0, f"Interface should not be flagged, got {findings}"

    def test_slf4j_present_on_service(self, tmp_path):
        """BE-QL-08: Service with @Slf4j should pass."""
        rules = {
            "BE-QL-08": {
                "level": "P2",
                "message": "{class} 缺少 @Slf4j",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "skip_interface": True,
                    "required_class_annotation": "@Slf4j"
                }
            }
        }
        file_path = tmp_path / "UserServiceImpl.java"
        file_path.write_text(JAVA_SERVICE_WITH_SLF4J)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0

    def test_slf4j_missing_on_service(self, tmp_path):
        """BE-QL-08: Service without @Slf4j should be flagged."""
        rules = {
            "BE-QL-08": {
                "level": "P2",
                "message": "{class} 缺少 @Slf4j",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "skip_interface": True,
                    "required_class_annotation": "@Slf4j"
                }
            }
        }
        file_path = tmp_path / "UserServiceImpl.java"
        file_path.write_text(JAVA_SERVICE_WITHOUT_SLF4J)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1

    def test_bcrypt_present_in_service(self, tmp_path):
        """BE-AU-07: Service with BCryptPasswordEncoder should pass."""
        rules = {
            "BE-AU-07": {
                "level": "P0",
                "message": "密码未使用 BCrypt",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "require_pattern": "BCryptPasswordEncoder"
                }
            }
        }
        file_path = tmp_path / "UserServiceImpl.java"
        file_path.write_text(JAVA_WITH_BCRYPT)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0

    def test_bcrypt_missing_in_service(self, tmp_path):
        """BE-AU-07: Service without BCryptPasswordEncoder should be flagged."""
        rules = {
            "BE-AU-07": {
                "level": "P0",
                "message": "密码未使用 BCrypt",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "require_pattern": "BCryptPasswordEncoder"
                }
            }
        }
        file_path = tmp_path / "UserServiceImpl.java"
        file_path.write_text(JAVA_WITHOUT_BCRYPT)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1

    def test_constant_class_final_private_ctor(self, tmp_path):
        """BE-QL-38: Constant class with final + private ctor should pass."""
        rules = {
            "BE-QL-38": {
                "level": "P2",
                "message": "常量类应声明为 final + 私有构造",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": ".*(Constant|Constants|Code|Codes)",
                    "required_class_modifier": "final",
                    "required_private_constructor": True
                }
            }
        }
        file_path = tmp_path / "ErrorCodes.java"
        file_path.write_text(JAVA_CONSTANT_CLASS)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0

    def test_constant_class_missing_final(self, tmp_path):
        """BE-QL-38: Constant class without final/private ctor should fail."""
        rules = {
            "BE-QL-38": {
                "level": "P2",
                "message": "常量类应声明为 final + 私有构造",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": ".*(Constant|Constants|Code|Codes)",
                    "required_class_modifier": "final",
                    "required_private_constructor": True
                }
            }
        }
        file_path = tmp_path / "ErrorCodes.java"
        file_path.write_text(JAVA_BAD_CONSTANT_CLASS)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) >= 1


class TestJavaAstFieldChecks:

    def test_schema_on_dto_fields_skips_static_final(self, tmp_path):
        """BE-IN-04: @Schema check skips static final constants on DTO fields."""
        rules = {
            "BE-IN-04": {
                "level": "P2",
                "message": "{class}.{field} 缺少 @Schema",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "on_dir": "dto",
                    "skip_static_final": True,
                    "required_field_annotation": "@Schema"
                }
            }
        }
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        file_path = dto_dir / "RegisterDTO.java"
        file_path.write_text(JAVA_DTO_WITH_SCHEMA)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0, f"All instance fields have @Schema, static final skipped. Got {findings}"

    def test_schema_missing_on_dto_fields(self, tmp_path):
        """BE-IN-04: DTO fields without @Schema should be flagged."""
        rules = {
            "BE-IN-04": {
                "level": "P2",
                "message": "{class}.{field} 缺少 @Schema",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "on_dir": "dto",
                    "skip_static_final": True,
                    "required_field_annotation": "@Schema"
                }
            }
        }
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        file_path = dto_dir / "LoginDTO.java"
        file_path.write_text(JAVA_DTO_WITHOUT_SCHEMA)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 2  # username and password both missing @Schema


class TestJavaAstMethodChecks:

    def test_result_return_type_missing(self, tmp_path):
        """BE-QL-13: Controller method without Result<T> should be flagged."""
        rules = {
            "BE-QL-13": {
                "level": "P1",
                "message": "{method} 返回值未使用 Result<T> 包裹",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "RestController|Controller",
                    "required_return_pattern": "Result<"
                }
            }
        }
        file_path = tmp_path / "UserController.java"
        file_path.write_text(JAVA_NO_RESULT_RETURN)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
        assert findings[0].method == "getUser"

    def test_result_return_type_present(self, tmp_path):
        """BE-QL-13: Controller method with Result<T> should pass."""
        rules = {
            "BE-QL-13": {
                "level": "P1",
                "message": "{method} 返回值未使用 Result<T> 包裹",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "RestController|Controller",
                    "required_return_pattern": "Result<"
                }
            }
        }
        file_path = tmp_path / "UserController.java"
        file_path.write_text(JAVA_WITH_RESULT_RETURN)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0

    def test_mapper_multi_param_with_param_annotation(self, tmp_path):
        """BE-QL-44: Mapper method with 2+ params all having @Param should pass."""
        rules = {
            "BE-QL-44": {
                "level": "P1",
                "message": "{method} 缺少 @Param 注解",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "*Mapper",
                    "param_missing_annotation": "@Param",
                    "param_count_gte": 2
                }
            }
        }
        file_path = tmp_path / "UserMapper.java"
        file_path.write_text(JAVA_MAPPER_WITH_PARAM)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0

    def test_mapper_multi_param_missing_param_annotation(self, tmp_path):
        """BE-QL-44: Mapper method with 2+ params missing @Param should fail."""
        rules = {
            "BE-QL-44": {
                "level": "P1",
                "message": "{method} 缺少 @Param 注解",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "*Mapper",
                    "param_missing_annotation": "@Param",
                    "param_count_gte": 2
                }
            }
        }
        file_path = tmp_path / "UserMapper.java"
        file_path.write_text(JAVA_MAPPER_WITHOUT_PARAM)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) >= 2


class TestJavaAstAllChecks:

    def test_system_out_detected(self, tmp_path):
        """BE-QL-07: System.out.println should be detected."""
        rules = {
            "BE-QL-07": {
                "level": "P1",
                "message": "使用 System.out/err",
                "program": {
                    "scanner": "java-ast",
                    "target": "all",
                    "forbid_pattern": "System\\.(out|err)\\.print"
                }
            }
        }
        file_path = tmp_path / "DebugService.java"
        file_path.write_text(JAVA_WITH_SYSOUT)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) >= 2  # Two println lines

    def test_value_annotation_detected(self, tmp_path):
        """BE-IN-10: @Value annotation should be detected."""
        rules = {
            "BE-IN-10": {
                "level": "P1",
                "message": "应使用 @ConfigurationProperties",
                "program": {
                    "scanner": "java-ast",
                    "target": "all",
                    "forbid_pattern": '@Value\\(\\"\\$\\{'
                }
            }
        }
        file_path = tmp_path / "AppConfig.java"
        file_path.write_text(JAVA_WITH_VALUE_ANNOTATION)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) >= 1


class TestJavaAstDirectoryFilter:

    def test_on_dir_filter(self, tmp_path):
        """Directory filter should work for field checks."""
        rules = {
            "BE-IN-04": {
                "level": "P2",
                "message": "{class}.{field} 缺少 @Schema",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "on_dir": "vo",
                    "skip_static_final": True,
                    "required_field_annotation": "@Schema"
                }
            }
        }
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        file_path = dto_dir / "LoginDTO.java"
        file_path.write_text(JAVA_DTO_WITHOUT_SCHEMA)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        # on_dir is "vo", but the file is in "dto" dir -- should NOT trigger
        assert len(findings) == 0


# ═══════════════════════════════════════════════════════════════
# Retained Scanner Tests
# ═══════════════════════════════════════════════════════════════

class TestScannerRegistry:

    def test_scanner_registry(self):
        """Verify SCANNERS contains the right scanners."""
        assert "java-ast" in SCANNERS
        assert "package-structure" in SCANNERS
        assert "file-naming" in SCANNERS
        assert "config-check" in SCANNERS

    def test_old_scanners_removed(self):
        """Verify old scanners are gone."""
        assert "text-grep" not in SCANNERS
        assert "java-annotation" not in SCANNERS
        assert "java-return-type" not in SCANNERS


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


# ── Package Structure Scanner Tests ────────────────────────────

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


# ── File Naming Scanner Tests ──────────────────────────────────

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


# ── Config Check Scanner Tests ─────────────────────────────────

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
        # So the regex won't match -- no finding
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


# ── _any_match crash fix Tests ────────────────────────────────


class TestAnyMatchCrashFix:
    """_any_match must not crash on invalid regex."""

    def test_any_match_with_unbalanced_parens_does_not_crash(self):
        """Pattern .*(Constant|Constants|Code|Codes) split on | must not crash."""
        # The pattern .*(Constant|Constants|Code|Codes) split by | produces
        # "Codes)" which is an invalid regex (unbalanced paren).
        # _any_match must not raise re.error.
        result = _any_match(
            ["Component"], ".*(Constant|Constants|Code|Codes)"
        )
        # Should not crash and should return False (Component doesn't match)
        assert result is False

    def test_any_match_with_valid_pattern_still_works(self):
        """Normal patterns should still match correctly after the fix."""
        result = _any_match(
            ["RestController"], "RestController|Controller"
        )
        assert result is True

    def test_any_match_with_glob_pattern(self):
        """Glob patterns like *Mapper should match."""
        result = _any_match(["UserMapper"], "*Mapper")
        assert result is True


# ── Nested YAML Matching Tests ─────────────────────────────────


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


# ── _matches_on_dir Tests ──────────────────────────────────────


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


# ── ConfigCheck Exclude Tests ──────────────────────────────────

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


