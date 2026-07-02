# 后台管理系统 Demo — 实现计划

**目标:** 从零构建 Spring Boot 3 后台管理系统 API，含认证、RBAC、日志、字典四大模块，29 个接口，9 张表。

**架构:** 单体应用 + 领域分包（common/auth/system/log/dict），Sa-Token + JWT 认证，MyBatis-Plus ORM，Knife4j 文档，Spring AOP 操作日志。

**技术栈:** Spring Boot 3, Sa-Token, MyBatis-Plus, MySQL, Knife4j, Lombok, BCrypt, JSR 303

**Spec:** `docs/superpowers/specs/2026-06-26-admin-system-design.md`

---

## 预期产出清单

```
admin-test-04/
├── pom.xml
├── README.md
└── src/main/
    ├── java/cn/xxx/admin/
    │   ├── AdminApplication.java
    │   ├── common/
    │   │   ├── config/
    │   │   │   ├── SaTokenConfig.java
    │   │   │   ├── MybatisPlusConfig.java
    │   │   │   ├── Knife4jConfig.java
    │   │   │   └── GlobalExceptionHandler.java
    │   │   ├── exception/
    │   │   │   ├── BusinessException.java
    │   │   │   └── BusinessErrorEnum.java
    │   │   ├── result/
    │   │   │   └── Result.java
    │   │   └── base/
    │   │       └── BaseEntity.java
    │   ├── auth/
    │   │   ├── controller/AuthController.java
    │   │   ├── service/AuthService.java
    │   │   ├── service/impl/AuthServiceImpl.java
    │   │   └── dto/
    │   │       ├── RegisterReq.java
    │   │       ├── LoginReq.java
    │   │       └── LoginResp.java
    │   ├── system/
    │   │   ├── controller/
    │   │   │   ├── UserController.java
    │   │   │   ├── RoleController.java
    │   │   │   └── PermissionController.java
    │   │   ├── service/
    │   │   │   ├── UserService.java
    │   │   │   ├── RoleService.java
    │   │   │   └── PermissionService.java
    │   │   ├── service/impl/
    │   │   │   ├── UserServiceImpl.java
    │   │   │   ├── RoleServiceImpl.java
    │   │   │   └── PermissionServiceImpl.java
    │   │   ├── mapper/
    │   │   │   ├── UserMapper.java
    │   │   │   ├── RoleMapper.java
    │   │   │   ├── PermissionMapper.java
    │   │   │   ├── UserRoleMapper.java
    │   │   │   └── RolePermissionMapper.java
    │   │   ├── entity/
    │   │   │   ├── User.java
    │   │   │   ├── Role.java
    │   │   │   ├── Permission.java
    │   │   │   ├── UserRole.java
    │   │   │   └── RolePermission.java
    │   │   └── dto/
    │   │       ├── UserQueryReq.java
    │   │       ├── UserSaveReq.java
    │   │       ├── RoleQueryReq.java
    │   │       ├── RoleSaveReq.java
    │   │       ├── PermissionQueryReq.java
    │   │       ├── PermissionSaveReq.java
    │   │       ├── AssignRolesReq.java
    │   │       └── AssignPermsReq.java
    │   ├── log/
    │   │   ├── controller/
    │   │   │   ├── LoginLogController.java
    │   │   │   └── OperationLogController.java
    │   │   ├── service/
    │   │   │   ├── LoginLogService.java
    │   │   │   └── OperationLogService.java
    │   │   ├── service/impl/
    │   │   │   ├── LoginLogServiceImpl.java
    │   │   │   └── OperationLogServiceImpl.java
    │   │   ├── mapper/
    │   │   │   ├── LoginLogMapper.java
    │   │   │   └── OperationLogMapper.java
    │   │   ├── entity/
    │   │   │   ├── LoginLog.java
    │   │   │   └── OperationLog.java
    │   │   ├── aspect/
    │   │   │   ├── Log.java
    │   │   │   └── LogAspect.java
    │   │   └── dto/
    │   │       ├── LoginLogQueryReq.java
    │   │       └── OperationLogQueryReq.java
    │   └── dict/
    │       ├── controller/
    │       │   ├── DictTypeController.java
    │       │   └── DictItemController.java
    │       ├── service/
    │       │   ├── DictTypeService.java
    │       │   └── DictItemService.java
    │       ├── service/impl/
    │       │   ├── DictTypeServiceImpl.java
    │       │   └── DictItemServiceImpl.java
    │       ├── mapper/
    │       │   ├── DictTypeMapper.java
    │       │   └── DictItemMapper.java
    │       ├── entity/
    │       │   ├── DictType.java
    │       │   └── DictItem.java
    │       └── dto/
    │           ├── DictTypeSaveReq.java
    │           └── DictItemSaveReq.java
    └── resources/
        ├── application.yml
        ├── logback-spring.xml
        └── db/
            └── init.sql
```

**预计 57 个 Java 文件 + 4 个资源文件。**

---

## Phase 1: 项目基础 & 配置文件

### Task 1.1: pom.xml

**文件:** `admin-test-04/pom.xml`

创建 Spring Boot 3 项目，包含所有依赖：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>cn.xxx</groupId>
    <artifactId>admin-demo</artifactId>
    <version>1.0.0</version>
    <name>admin-demo</name>
    <description>后台管理系统 Demo</description>

    <properties>
        <java.version>17</java.version>
        <mybatis-plus.version>3.5.5</mybatis-plus.version>
        <sa-token.version>1.37.0</sa-token.version>
        <knife4j.version>4.5.0</knife4j.version>
    </properties>

    <dependencies>
        <!-- Spring Boot Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Spring Boot AOP -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>

        <!-- Spring Boot Validation -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <!-- MyBatis-Plus -->
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
            <version>${mybatis-plus.version}</version>
        </dependency>

        <!-- MySQL Connector -->
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- Sa-Token + JWT -->
        <dependency>
            <groupId>cn.dev33</groupId>
            <artifactId>sa-token-spring-boot3-starter</artifactId>
            <version>${sa-token.version}</version>
        </dependency>
        <dependency>
            <groupId>cn.dev33</groupId>
            <artifactId>sa-token-jwt</artifactId>
            <version>${sa-token.version}</version>
        </dependency>

        <!-- Knife4j -->
        <dependency>
            <groupId>com.github.xiaoymin</groupId>
            <artifactId>knife4j-openapi3-jakarta-spring-boot-starter</artifactId>
            <version>${knife4j.version}</version>
        </dependency>

        <!-- Lombok -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- Spring Security Crypto (BCrypt) -->
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>

        <!-- Jackson (JSON 序列化) -->
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>

        <!-- Test -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### Task 1.2: application.yml

**文件:** `admin-test-04/src/main/resources/application.yml`

```yaml
server:
  port: 8080

spring:
  datasource:
    url: jdbc:mysql://localhost:3306/admin_demo?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai
    username: root
    password: root
    driver-class-name: com.mysql.cj.jdbc.Driver
  jackson:
    date-format: yyyy-MM-dd HH:mm:ss
    time-zone: GMT+8

mybatis-plus:
  configuration:
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl
    map-underscore-to-camel-case: true
  mapper-locations: classpath:mapper/**/*.xml
  global-config:
    db-config:
      id-type: auto
      logic-delete-field: deleted
      logic-delete-value: 1
      logic-not-delete-value: 0

sa-token:
  token-name: Authorization
  timeout: 2592000
  active-timeout: -1
  is-concurrent: true
  is-share: true
  token-style: tik
  is-log: true
  jwt-secret-key: admin-demo-jwt-secret-key-2026

knife4j:
  enable: true
  setting:
    language: zh_cn

springdoc:
  swagger-ui:
    path: /swagger-ui.html
  api-docs:
    path: /v3/api-docs
```

### Task 1.3: logback-spring.xml

**文件:** `admin-test-04/src/main/resources/logback-spring.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <property name="LOG_PATTERN" value="%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{50} - %msg%n"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>${LOG_PATTERN}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

    <logger name="cn.xxx.admin" level="DEBUG"/>
</configuration>
```

### Task 1.4: AdminApplication.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/AdminApplication.java`

```java
package cn.xxx.admin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AdminApplication {
    public static void main(String[] args) {
        SpringApplication.run(AdminApplication.class, args);
    }
}
```

---

## Phase 2: Common 基础设施

### Task 2.1: Result.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/result/Result.java`

```java
package cn.xxx.admin.common.result;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class Result<T> {
    private int code;
    private T data;
    private String message;

    public static <T> Result<T> success(T data) {
        return new Result<>(200, data, "success");
    }

    public static <T> Result<T> success() {
        return new Result<>(200, null, "success");
    }

    public static <T> Result<T> error(int code, String message) {
        return new Result<>(code, null, message);
    }
}
```

### Task 2.2: BusinessException.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/exception/BusinessException.java`

```java
package cn.xxx.admin.common.exception;

import lombok.Getter;

@Getter
public class BusinessException extends RuntimeException {
    private final int code;

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public BusinessException(BusinessErrorEnum errorEnum) {
        super(errorEnum.getMessage());
        this.code = errorEnum.getCode();
    }
}
```

### Task 2.3: BusinessErrorEnum.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/exception/BusinessErrorEnum.java`

```java
package cn.xxx.admin.common.exception;

import lombok.Getter;

@Getter
public enum BusinessErrorEnum {
    // 1000-1999 用户/认证
    USERNAME_EXISTS(1001, "用户名已存在"),
    USERNAME_OR_PASSWORD_ERROR(1002, "用户名或密码错误"),
    NOT_LOGIN(1003, "未登录，请先登录"),
    PASSWORD_NOT_MATCH(1004, "两次密码不一致"),
    USER_NOT_FOUND(1005, "用户不存在"),

    // 2000-2999 RBAC
    ROLE_NOT_FOUND(2001, "角色不存在"),
    PERM_CODE_EXISTS(2002, "权限标识已存在"),
    NO_PERMISSION(2003, "无权限"),

    // 4000-4999 字典
    DICT_TYPE_EXISTS(4001, "字典类型已存在"),
    DICT_ITEM_VALUE_DUPLICATE(4002, "字典项值重复"),

    // 9000-9999 通用
    PARAM_VALID_FAIL(9001, "参数校验失败"),
    SYSTEM_ERROR(9999, "系统未知错误");

    private final int code;
    private final String message;

    BusinessErrorEnum(int code, String message) {
        this.code = code;
        this.message = message;
    }
}
```

### Task 2.4: BaseEntity.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/base/BaseEntity.java`

```java
package cn.xxx.admin.common.base;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import lombok.Data;

import java.time.LocalDateTime;

@Data
public abstract class BaseEntity {
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
}
```

### Task 2.5: GlobalExceptionHandler.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/config/GlobalExceptionHandler.java`

```java
package cn.xxx.admin.common.config;

import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.common.result.Result;
import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.exception.NotPermissionException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public Result<?> handleBusinessException(BusinessException e) {
        log.warn("业务异常: code={}, message={}", e.getCode(), e.getMessage());
        return Result.error(e.getCode(), e.getMessage());
    }

    @ExceptionHandler(NotLoginException.class)
    public Result<?> handleNotLoginException(NotLoginException e) {
        return Result.error(1003, "未登录，请先登录");
    }

    @ExceptionHandler(NotPermissionException.class)
    public Result<?> handleNotPermissionException(NotPermissionException e) {
        return Result.error(2003, "无权限");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result<?> handleValidException(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .reduce((a, b) -> a + "; " + b)
                .orElse("参数校验失败");
        return Result.error(9001, msg);
    }

    @ExceptionHandler(Exception.class)
    public Result<?> handleException(Exception e) {
        log.error("系统异常", e);
        return Result.error(9999, "系统未知错误");
    }
}
```

### Task 2.6: SaTokenConfig.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/config/SaTokenConfig.java`

```java
package cn.xxx.admin.common.config;

import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.stp.StpUtil;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class SaTokenConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SaInterceptor(handle -> StpUtil.checkLogin()))
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/auth/login", "/api/auth/register")
                .excludePathPatterns("/v3/api-docs/**", "/swagger-ui/**", "/doc.html");
    }
}
```

### Task 2.7: MybatisPlusConfig.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/config/MybatisPlusConfig.java`

```java
package cn.xxx.admin.common.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MybatisPlusConfig {

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }
}
```

### Task 2.8: Knife4jConfig.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/config/Knife4jConfig.java`

```java
package cn.xxx.admin.common.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Knife4jConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("后台管理系统 API")
                        .version("1.0.0")
                        .description("后台管理系统 Demo 接口文档")
                        .contact(new Contact().name("admin")));
    }
}
```

### Task 2.9: StpInterfaceImpl.java — 权限加载

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/common/config/StpInterfaceImpl.java`

实现 `StpInterface` 从数据库加载用户权限标识和角色标识：

```java
package cn.xxx.admin.common.config;

import cn.dev33.satoken.stp.StpInterface;
import cn.xxx.admin.system.entity.UserRole;
import cn.xxx.admin.system.entity.RolePermission;
import cn.xxx.admin.system.entity.Permission;
import cn.xxx.admin.system.mapper.*;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

@Component
@RequiredArgsConstructor
public class StpInterfaceImpl implements StpInterface {

    private final UserRoleMapper userRoleMapper;
    private final RolePermissionMapper rolePermissionMapper;
    private final PermissionMapper permissionMapper;

    @Override
    public List<String> getPermissionList(Object loginId, String loginType) {
        Long userId = Long.valueOf(loginId.toString());
        // 查出用户的所有角色
        List<Long> roleIds = userRoleMapper.selectList(
                new LambdaQueryWrapper<UserRole>().eq(UserRole::getUserId, userId)
        ).stream().map(UserRole::getRoleId).collect(Collectors.toList());

        if (roleIds.isEmpty()) {
            return new ArrayList<>();
        }

        // 查出角色关联的所有权限
        List<Long> permIds = rolePermissionMapper.selectList(
                new LambdaQueryWrapper<RolePermission>().in(RolePermission::getRoleId, roleIds)
        ).stream().map(RolePermission::getPermissionId).distinct().collect(Collectors.toList());

        if (permIds.isEmpty()) {
            return new ArrayList<>();
        }

        // 查出权限标识
        return permissionMapper.selectList(
                new LambdaQueryWrapper<Permission>().in(Permission::getId, permIds)
        ).stream().map(Permission::getPermCode).collect(Collectors.toList());
    }

    @Override
    public List<String> getRoleList(Object loginId, String loginType) {
        Long userId = Long.valueOf(loginId.toString());
        // 由于角色名不在关联查询中，这里返回角色 ID 列表
        // 实际角色名可以从 UserRole + Role 联表查出，简化处理返回 role_id 的字符串
        List<Long> roleIds = userRoleMapper.selectList(
                new LambdaQueryWrapper<UserRole>().eq(UserRole::getUserId, userId)
        ).stream().map(UserRole::getRoleId).collect(Collectors.toList());

        return roleIds.stream().map(String::valueOf).collect(Collectors.toList());
    }
}
```

---

## Phase 3: Auth 认证模块

### Task 3.1: RegisterReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/dto/RegisterReq.java`

```java
package cn.xxx.admin.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class RegisterReq {
    @NotBlank(message = "用户名不能为空")
    private String username;

    @NotBlank(message = "密码不能为空")
    private String password;

    @NotBlank(message = "确认密码不能为空")
    private String confirmPassword;
}
```

### Task 3.2: LoginReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/dto/LoginReq.java`

```java
package cn.xxx.admin.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class LoginReq {
    @NotBlank(message = "用户名不能为空")
    private String username;

    @NotBlank(message = "密码不能为空")
    private String password;
}
```

### Task 3.3: LoginResp.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/dto/LoginResp.java`

```java
package cn.xxx.admin.auth.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class LoginResp {
    private String token;
    private Long userId;
    private String username;
    private List<String> roles;
    private List<String> permissions;
}
```

### Task 3.4: AuthService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/service/AuthService.java`

```java
package cn.xxx.admin.auth.service;

import cn.xxx.admin.auth.dto.LoginReq;
import cn.xxx.admin.auth.dto.LoginResp;
import cn.xxx.admin.auth.dto.RegisterReq;

public interface AuthService {
    LoginResp register(RegisterReq req, String ip, String userAgent);
    LoginResp login(LoginReq req, String ip, String userAgent);
    void logout();
    LoginResp info();
}
```

### Task 3.5: AuthServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/service/impl/AuthServiceImpl.java`

```java
package cn.xxx.admin.auth.service.impl;

import cn.dev33.satoken.stp.StpUtil;
import cn.xxx.admin.auth.dto.LoginReq;
import cn.xxx.admin.auth.dto.LoginResp;
import cn.xxx.admin.auth.dto.RegisterReq;
import cn.xxx.admin.auth.service.AuthService;
import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.log.entity.LoginLog;
import cn.xxx.admin.log.mapper.LoginLogMapper;
import cn.xxx.admin.system.entity.User;
import cn.xxx.admin.system.mapper.UserMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final UserMapper userMapper;
    private final LoginLogMapper loginLogMapper;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    @Override
    public LoginResp register(RegisterReq req, String ip, String userAgent) {
        if (!req.getPassword().equals(req.getConfirmPassword())) {
            throw new BusinessException(BusinessErrorEnum.PASSWORD_NOT_MATCH);
        }

        boolean exists = userMapper.exists(new LambdaQueryWrapper<User>()
                .eq(User::getUsername, req.getUsername()));
        if (exists) {
            throw new BusinessException(BusinessErrorEnum.USERNAME_EXISTS);
        }

        User user = new User();
        user.setUsername(req.getUsername());
        user.setPassword(passwordEncoder.encode(req.getPassword()));
        user.setStatus(1);
        userMapper.insert(user);

        log.info("用户注册成功: username={}", req.getUsername());

        // 注册成功自动登录
        LoginReq loginReq = new LoginReq();
        loginReq.setUsername(req.getUsername());
        loginReq.setPassword(req.getPassword());
        return login(loginReq, ip, userAgent);
    }

    @Override
    public LoginResp login(LoginReq req, String ip, String userAgent) {
        User user = userMapper.selectOne(new LambdaQueryWrapper<User>()
                .eq(User::getUsername, req.getUsername()));

        if (user == null || !passwordEncoder.matches(req.getPassword(), user.getPassword())) {
            // 记录失败日志
            saveLoginLog(req.getUsername(), ip, userAgent, 0);
            throw new BusinessException(BusinessErrorEnum.USERNAME_OR_PASSWORD_ERROR);
        }

        // 登录
        StpUtil.login(user.getId());
        String token = StpUtil.getTokenValue();

        // 记录成功日志
        saveLoginLog(req.getUsername(), ip, userAgent, 1);

        log.info("用户登录成功: username={}", req.getUsername());

        return LoginResp.builder()
                .token(token)
                .userId(user.getId())
                .username(user.getUsername())
                .roles(StpUtil.getRoleList())
                .permissions(StpUtil.getPermissionList())
                .build();
    }

    @Override
    public void logout() {
        Long userId = StpUtil.getLoginIdAsLong();
        log.info("用户登出: userId={}", userId);
        StpUtil.logout();
    }

    @Override
    public LoginResp info() {
        Long userId = StpUtil.getLoginIdAsLong();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }

        // 转换为 Long 列表后逐个转为 String
        List<String> roleIds = StpUtil.getRoleList();
        List<String> permCodes = StpUtil.getPermissionList();

        return LoginResp.builder()
                .token(StpUtil.getTokenValue())
                .userId(user.getId())
                .username(user.getUsername())
                .roles(roleIds)
                .permissions(permCodes)
                .build();
    }

    private void saveLoginLog(String username, String ip, String userAgent, int status) {
        LoginLog loginLog = new LoginLog();
        loginLog.setUsername(username);
        loginLog.setIp(ip);
        loginLog.setLoginTime(LocalDateTime.now());
        loginLog.setStatus(status);
        loginLog.setUserAgent(userAgent);
        loginLogMapper.insert(loginLog);
    }
}
```

### Task 3.6: AuthController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/auth/controller/AuthController.java`

```java
package cn.xxx.admin.auth.controller;

import cn.dev33.satoken.annotation.SaCheckLogin;
import cn.xxx.admin.auth.dto.LoginReq;
import cn.xxx.admin.auth.dto.LoginResp;
import cn.xxx.admin.auth.dto.RegisterReq;
import cn.xxx.admin.auth.service.AuthService;
import cn.xxx.admin.common.result.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "认证")
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @Operation(summary = "用户注册")
    @PostMapping("/register")
    public Result<LoginResp> register(@Valid @RequestBody RegisterReq req, HttpServletRequest request) {
        String ip = getClientIp(request);
        String userAgent = request.getHeader("User-Agent");
        LoginResp resp = authService.register(req, ip, userAgent);
        return Result.success(resp);
    }

    @Operation(summary = "用户登录")
    @PostMapping("/login")
    public Result<LoginResp> login(@Valid @RequestBody LoginReq req, HttpServletRequest request) {
        String ip = getClientIp(request);
        String userAgent = request.getHeader("User-Agent");
        LoginResp resp = authService.login(req, ip, userAgent);
        return Result.success(resp);
    }

    @Operation(summary = "登出")
    @PostMapping("/logout")
    public Result<?> logout() {
        authService.logout();
        return Result.success();
    }

    @Operation(summary = "获取当前用户信息")
    @GetMapping("/info")
    public Result<LoginResp> info() {
        LoginResp resp = authService.info();
        return Result.success(resp);
    }

    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        return ip;
    }
}
```

---

## Phase 4: System RBAC 模块

### Task 4.1: User.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/entity/User.java`

```java
package cn.xxx.admin.system.entity;

import cn.xxx.admin.common.base.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("sys_user")
public class User extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String username;
    private String password;
    private Integer status;
}
```

### Task 4.2: Role.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/entity/Role.java`

```java
package cn.xxx.admin.system.entity;

import cn.xxx.admin.common.base.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("sys_role")
public class Role extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String roleName;
    private String roleCode;
    private String description;
    private Integer status;
}
```

### Task 4.3: Permission.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/entity/Permission.java`

```java
package cn.xxx.admin.system.entity;

import cn.xxx.admin.common.base.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("sys_permission")
public class Permission extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String permName;
    private String permCode;
    private String url;
    private String method;
    private String description;
}
```

### Task 4.4: UserRole.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/entity/UserRole.java`

```java
package cn.xxx.admin.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("sys_user_role")
public class UserRole {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long roleId;
}
```

### Task 4.5: RolePermission.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/entity/RolePermission.java`

```java
package cn.xxx.admin.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("sys_role_permission")
public class RolePermission {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long roleId;
    private Long permissionId;
}
```

### Task 4.6: UserMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/mapper/UserMapper.java`

```java
package cn.xxx.admin.system.mapper;

import cn.xxx.admin.system.entity.User;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserMapper extends BaseMapper<User> {
}
```

### Task 4.7: RoleMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/mapper/RoleMapper.java`

```java
package cn.xxx.admin.system.mapper;

import cn.xxx.admin.system.entity.Role;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface RoleMapper extends BaseMapper<Role> {
}
```

### Task 4.8: PermissionMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/mapper/PermissionMapper.java`

```java
package cn.xxx.admin.system.mapper;

import cn.xxx.admin.system.entity.Permission;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface PermissionMapper extends BaseMapper<Permission> {
}
```

### Task 4.9: UserRoleMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/mapper/UserRoleMapper.java`

```java
package cn.xxx.admin.system.mapper;

import cn.xxx.admin.system.entity.UserRole;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserRoleMapper extends BaseMapper<UserRole> {
}
```

### Task 4.10: RolePermissionMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/mapper/RolePermissionMapper.java`

```java
package cn.xxx.admin.system.mapper;

import cn.xxx.admin.system.entity.RolePermission;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface RolePermissionMapper extends BaseMapper<RolePermission> {
}
```

### Task 4.11: UserQueryReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/UserQueryReq.java`

```java
package cn.xxx.admin.system.dto;

import lombok.Data;

@Data
public class UserQueryReq {
    private String username;
    private Integer status;
    private Integer pageNum = 1;
    private Integer pageSize = 10;
}
```

### Task 4.12: UserSaveReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/UserSaveReq.java`

```java
package cn.xxx.admin.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class UserSaveReq {
    private Long id;
    @NotBlank(message = "用户名不能为空")
    private String username;
    private String password;
    private Integer status;
}
```

### Task 4.13: RoleQueryReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/RoleQueryReq.java`

```java
package cn.xxx.admin.system.dto;

import lombok.Data;

@Data
public class RoleQueryReq {
    private String roleName;
    private String roleCode;
    private Integer status;
    private Integer pageNum = 1;
    private Integer pageSize = 10;
}
```

### Task 4.14: RoleSaveReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/RoleSaveReq.java`

```java
package cn.xxx.admin.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class RoleSaveReq {
    private Long id;
    @NotBlank(message = "角色名称不能为空")
    private String roleName;
    @NotBlank(message = "角色编码不能为空")
    private String roleCode;
    private String description;
    private Integer status;
}
```

### Task 4.15: PermissionQueryReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/PermissionQueryReq.java`

```java
package cn.xxx.admin.system.dto;

import lombok.Data;

@Data
public class PermissionQueryReq {
    private String permName;
    private String permCode;
    private Integer pageNum = 1;
    private Integer pageSize = 10;
}
```

### Task 4.16: PermissionSaveReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/PermissionSaveReq.java`

```java
package cn.xxx.admin.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class PermissionSaveReq {
    private Long id;
    @NotBlank(message = "权限名称不能为空")
    private String permName;
    @NotBlank(message = "权限标识不能为空")
    private String permCode;
    private String url;
    private String method;
    private String description;
}
```

### Task 4.17: AssignRolesReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/AssignRolesReq.java`

```java
package cn.xxx.admin.system.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;
import java.util.List;

@Data
public class AssignRolesReq {
    @NotNull(message = "角色ID列表不能为空")
    private List<Long> roleIds;
}
```

### Task 4.18: AssignPermsReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/dto/AssignPermsReq.java`

```java
package cn.xxx.admin.system.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;
import java.util.List;

@Data
public class AssignPermsReq {
    @NotNull(message = "权限ID列表不能为空")
    private List<Long> permissionIds;
}
```

### Task 4.19: UserService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/UserService.java`

```java
package cn.xxx.admin.system.service;

import cn.xxx.admin.system.dto.AssignRolesReq;
import cn.xxx.admin.system.dto.UserQueryReq;
import cn.xxx.admin.system.dto.UserSaveReq;
import cn.xxx.admin.system.entity.User;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface UserService {
    Page<User> page(UserQueryReq req);
    User getById(Long id);
    void save(UserSaveReq req);
    void update(UserSaveReq req);
    void delete(Long id);
    void assignRoles(Long userId, AssignRolesReq req);
}
```

### Task 4.20: UserServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/impl/UserServiceImpl.java`

```java
package cn.xxx.admin.system.service.impl;

import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.system.dto.AssignRolesReq;
import cn.xxx.admin.system.dto.UserQueryReq;
import cn.xxx.admin.system.dto.UserSaveReq;
import cn.xxx.admin.system.entity.User;
import cn.xxx.admin.system.entity.UserRole;
import cn.xxx.admin.system.mapper.UserMapper;
import cn.xxx.admin.system.mapper.UserRoleMapper;
import cn.xxx.admin.system.service.UserService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {

    private final UserMapper userMapper;
    private final UserRoleMapper userRoleMapper;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    @Override
    public Page<User> page(UserQueryReq req) {
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(req.getUsername())) {
            wrapper.like(User::getUsername, req.getUsername());
        }
        if (req.getStatus() != null) {
            wrapper.eq(User::getStatus, req.getStatus());
        }
        wrapper.orderByDesc(User::getCreateTime);
        return userMapper.selectPage(new Page<>(req.getPageNum(), req.getPageSize()), wrapper);
    }

    @Override
    public User getById(Long id) {
        User user = userMapper.selectById(id);
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }
        return user;
    }

    @Override
    @Transactional
    public void save(UserSaveReq req) {
        boolean exists = userMapper.exists(new LambdaQueryWrapper<User>()
                .eq(User::getUsername, req.getUsername()));
        if (exists) {
            throw new BusinessException(BusinessErrorEnum.USERNAME_EXISTS);
        }
        User user = new User();
        user.setUsername(req.getUsername());
        if (StringUtils.hasText(req.getPassword())) {
            user.setPassword(passwordEncoder.encode(req.getPassword()));
        }
        user.setStatus(req.getStatus() != null ? req.getStatus() : 1);
        userMapper.insert(user);
    }

    @Override
    @Transactional
    public void update(UserSaveReq req) {
        User user = userMapper.selectById(req.getId());
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }
        user.setUsername(req.getUsername());
        if (StringUtils.hasText(req.getPassword())) {
            user.setPassword(passwordEncoder.encode(req.getPassword()));
        }
        if (req.getStatus() != null) {
            user.setStatus(req.getStatus());
        }
        userMapper.updateById(user);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        User user = userMapper.selectById(id);
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }
        userMapper.deleteById(id);
        // 同时删除用户角色关联
        userRoleMapper.delete(new LambdaQueryWrapper<UserRole>().eq(UserRole::getUserId, id));
    }

    @Override
    @Transactional
    public void assignRoles(Long userId, AssignRolesReq req) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }
        // 删除旧关联
        userRoleMapper.delete(new LambdaQueryWrapper<UserRole>().eq(UserRole::getUserId, userId));
        // 插入新关联
        List<UserRole> userRoles = req.getRoleIds().stream().map(roleId -> {
            UserRole ur = new UserRole();
            ur.setUserId(userId);
            ur.setRoleId(roleId);
            return ur;
        }).collect(Collectors.toList());
        if (!userRoles.isEmpty()) {
            userRoles.forEach(userRoleMapper::insert);
        }
    }
}
```

### Task 4.21: RoleService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/RoleService.java`

```java
package cn.xxx.admin.system.service;

import cn.xxx.admin.system.dto.AssignPermsReq;
import cn.xxx.admin.system.dto.RoleQueryReq;
import cn.xxx.admin.system.dto.RoleSaveReq;
import cn.xxx.admin.system.entity.Role;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface RoleService {
    Page<Role> page(RoleQueryReq req);
    Role getById(Long id);
    void save(RoleSaveReq req);
    void update(RoleSaveReq req);
    void delete(Long id);
    void assignPermissions(Long roleId, AssignPermsReq req);
}
```

### Task 4.22: RoleServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/impl/RoleServiceImpl.java`

```java
package cn.xxx.admin.system.service.impl;

import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.system.dto.AssignPermsReq;
import cn.xxx.admin.system.dto.RoleQueryReq;
import cn.xxx.admin.system.dto.RoleSaveReq;
import cn.xxx.admin.system.entity.Role;
import cn.xxx.admin.system.entity.RolePermission;
import cn.xxx.admin.system.mapper.RoleMapper;
import cn.xxx.admin.system.mapper.RolePermissionMapper;
import cn.xxx.admin.system.service.RoleService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class RoleServiceImpl extends ServiceImpl<RoleMapper, Role> implements RoleService {

    private final RoleMapper roleMapper;
    private final RolePermissionMapper rolePermissionMapper;

    @Override
    public Page<Role> page(RoleQueryReq req) {
        LambdaQueryWrapper<Role> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(req.getRoleName())) {
            wrapper.like(Role::getRoleName, req.getRoleName());
        }
        if (StringUtils.hasText(req.getRoleCode())) {
            wrapper.like(Role::getRoleCode, req.getRoleCode());
        }
        if (req.getStatus() != null) {
            wrapper.eq(Role::getStatus, req.getStatus());
        }
        wrapper.orderByDesc(Role::getCreateTime);
        return roleMapper.selectPage(new Page<>(req.getPageNum(), req.getPageSize()), wrapper);
    }

    @Override
    public Role getById(Long id) {
        Role role = roleMapper.selectById(id);
        if (role == null) {
            throw new BusinessException(BusinessErrorEnum.ROLE_NOT_FOUND);
        }
        return role;
    }

    @Override
    @Transactional
    public void save(RoleSaveReq req) {
        Role role = new Role();
        role.setRoleName(req.getRoleName());
        role.setRoleCode(req.getRoleCode());
        role.setDescription(req.getDescription());
        role.setStatus(req.getStatus() != null ? req.getStatus() : 1);
        roleMapper.insert(role);
    }

    @Override
    @Transactional
    public void update(RoleSaveReq req) {
        Role role = roleMapper.selectById(req.getId());
        if (role == null) {
            throw new BusinessException(BusinessErrorEnum.ROLE_NOT_FOUND);
        }
        role.setRoleName(req.getRoleName());
        role.setRoleCode(req.getRoleCode());
        role.setDescription(req.getDescription());
        if (req.getStatus() != null) {
            role.setStatus(req.getStatus());
        }
        roleMapper.updateById(role);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        Role role = roleMapper.selectById(id);
        if (role == null) {
            throw new BusinessException(BusinessErrorEnum.ROLE_NOT_FOUND);
        }
        roleMapper.deleteById(id);
        rolePermissionMapper.delete(new LambdaQueryWrapper<RolePermission>().eq(RolePermission::getRoleId, id));
    }

    @Override
    @Transactional
    public void assignPermissions(Long roleId, AssignPermsReq req) {
        Role role = roleMapper.selectById(roleId);
        if (role == null) {
            throw new BusinessException(BusinessErrorEnum.ROLE_NOT_FOUND);
        }
        rolePermissionMapper.delete(new LambdaQueryWrapper<RolePermission>().eq(RolePermission::getRoleId, roleId));
        List<RolePermission> rps = req.getPermissionIds().stream().map(permId -> {
            RolePermission rp = new RolePermission();
            rp.setRoleId(roleId);
            rp.setPermissionId(permId);
            return rp;
        }).collect(Collectors.toList());
        if (!rps.isEmpty()) {
            rps.forEach(rolePermissionMapper::insert);
        }
    }
}
```

### Task 4.23: PermissionService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/PermissionService.java`

```java
package cn.xxx.admin.system.service;

import cn.xxx.admin.system.dto.PermissionQueryReq;
import cn.xxx.admin.system.dto.PermissionSaveReq;
import cn.xxx.admin.system.entity.Permission;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface PermissionService {
    Page<Permission> page(PermissionQueryReq req);
    Permission getById(Long id);
    void save(PermissionSaveReq req);
    void update(PermissionSaveReq req);
    void delete(Long id);
}
```

### Task 4.24: PermissionServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/service/impl/PermissionServiceImpl.java`

```java
package cn.xxx.admin.system.service.impl;

import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.system.dto.PermissionQueryReq;
import cn.xxx.admin.system.dto.PermissionSaveReq;
import cn.xxx.admin.system.entity.Permission;
import cn.xxx.admin.system.entity.RolePermission;
import cn.xxx.admin.system.mapper.PermissionMapper;
import cn.xxx.admin.system.mapper.RolePermissionMapper;
import cn.xxx.admin.system.service.PermissionService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Slf4j
@Service
@RequiredArgsConstructor
public class PermissionServiceImpl extends ServiceImpl<PermissionMapper, Permission> implements PermissionService {

    private final PermissionMapper permissionMapper;
    private final RolePermissionMapper rolePermissionMapper;

    @Override
    public Page<Permission> page(PermissionQueryReq req) {
        LambdaQueryWrapper<Permission> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(req.getPermName())) {
            wrapper.like(Permission::getPermName, req.getPermName());
        }
        if (StringUtils.hasText(req.getPermCode())) {
            wrapper.like(Permission::getPermCode, req.getPermCode());
        }
        wrapper.orderByDesc(Permission::getCreateTime);
        return permissionMapper.selectPage(new Page<>(req.getPageNum(), req.getPageSize()), wrapper);
    }

    @Override
    public Permission getById(Long id) {
        Permission perm = permissionMapper.selectById(id);
        if (perm == null) {
            throw new BusinessException(2002, "权限不存在");
        }
        return perm;
    }

    @Override
    @Transactional
    public void save(PermissionSaveReq req) {
        boolean exists = permissionMapper.exists(new LambdaQueryWrapper<Permission>()
                .eq(Permission::getPermCode, req.getPermCode()));
        if (exists) {
            throw new BusinessException(BusinessErrorEnum.PERM_CODE_EXISTS);
        }
        Permission perm = new Permission();
        perm.setPermName(req.getPermName());
        perm.setPermCode(req.getPermCode());
        perm.setUrl(req.getUrl());
        perm.setMethod(req.getMethod());
        perm.setDescription(req.getDescription());
        permissionMapper.insert(perm);
    }

    @Override
    @Transactional
    public void update(PermissionSaveReq req) {
        Permission perm = permissionMapper.selectById(req.getId());
        if (perm == null) {
            throw new BusinessException(2002, "权限不存在");
        }
        perm.setPermName(req.getPermName());
        perm.setPermCode(req.getPermCode());
        perm.setUrl(req.getUrl());
        perm.setMethod(req.getMethod());
        perm.setDescription(req.getDescription());
        permissionMapper.updateById(perm);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        Permission perm = permissionMapper.selectById(id);
        if (perm == null) {
            throw new BusinessException(2002, "权限不存在");
        }
        permissionMapper.deleteById(id);
        rolePermissionMapper.delete(new LambdaQueryWrapper<RolePermission>().eq(RolePermission::getPermissionId, id));
    }
}
```

### Task 4.25: UserController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/controller/UserController.java`

```java
package cn.xxx.admin.system.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.system.dto.AssignRolesReq;
import cn.xxx.admin.system.dto.UserQueryReq;
import cn.xxx.admin.system.dto.UserSaveReq;
import cn.xxx.admin.system.entity.User;
import cn.xxx.admin.system.service.UserService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "用户管理")
@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    @Operation(summary = "用户分页列表")
    @GetMapping
    @SaCheckPermission("system:user:list")
    public Result<Page<User>> list(UserQueryReq req) {
        return Result.success(userService.page(req));
    }

    @Operation(summary = "新增用户")
    @PostMapping
    @SaCheckPermission("system:user:add")
    public Result<?> add(@Valid @RequestBody UserSaveReq req) {
        userService.save(req);
        return Result.success();
    }

    @Operation(summary = "用户详情")
    @GetMapping("/{id}")
    @SaCheckPermission("system:user:query")
    public Result<User> get(@PathVariable Long id) {
        return Result.success(userService.getById(id));
    }

    @Operation(summary = "编辑用户")
    @PutMapping("/{id}")
    @SaCheckPermission("system:user:edit")
    public Result<?> update(@PathVariable Long id, @Valid @RequestBody UserSaveReq req) {
        req.setId(id);
        userService.update(req);
        return Result.success();
    }

    @Operation(summary = "删除用户")
    @DeleteMapping("/{id}")
    @SaCheckPermission("system:user:delete")
    public Result<?> delete(@PathVariable Long id) {
        userService.delete(id);
        return Result.success();
    }

    @Operation(summary = "分配角色")
    @PutMapping("/{id}/roles")
    @SaCheckPermission("system:user:assign-role")
    public Result<?> assignRoles(@PathVariable Long id, @Valid @RequestBody AssignRolesReq req) {
        userService.assignRoles(id, req);
        return Result.success();
    }
}
```

### Task 4.26: RoleController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/controller/RoleController.java`

```java
package cn.xxx.admin.system.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.system.dto.AssignPermsReq;
import cn.xxx.admin.system.dto.RoleQueryReq;
import cn.xxx.admin.system.dto.RoleSaveReq;
import cn.xxx.admin.system.entity.Role;
import cn.xxx.admin.system.service.RoleService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "角色管理")
@RestController
@RequestMapping("/api/roles")
@RequiredArgsConstructor
public class RoleController {

    private final RoleService roleService;

    @Operation(summary = "角色列表")
    @GetMapping
    @SaCheckPermission("system:role:list")
    public Result<Page<Role>> list(RoleQueryReq req) {
        return Result.success(roleService.page(req));
    }

    @Operation(summary = "新增角色")
    @PostMapping
    @SaCheckPermission("system:role:add")
    public Result<?> add(@Valid @RequestBody RoleSaveReq req) {
        roleService.save(req);
        return Result.success();
    }

    @Operation(summary = "角色详情")
    @GetMapping("/{id}")
    @SaCheckPermission("system:role:query")
    public Result<Role> get(@PathVariable Long id) {
        return Result.success(roleService.getById(id));
    }

    @Operation(summary = "编辑角色")
    @PutMapping("/{id}")
    @SaCheckPermission("system:role:edit")
    public Result<?> update(@PathVariable Long id, @Valid @RequestBody RoleSaveReq req) {
        req.setId(id);
        roleService.update(req);
        return Result.success();
    }

    @Operation(summary = "删除角色")
    @DeleteMapping("/{id}")
    @SaCheckPermission("system:role:delete")
    public Result<?> delete(@PathVariable Long id) {
        roleService.delete(id);
        return Result.success();
    }

    @Operation(summary = "分配权限")
    @PutMapping("/{id}/permissions")
    @SaCheckPermission("system:role:assign-perm")
    public Result<?> assignPermissions(@PathVariable Long id, @Valid @RequestBody AssignPermsReq req) {
        roleService.assignPermissions(id, req);
        return Result.success();
    }
}
```

### Task 4.27: PermissionController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/system/controller/PermissionController.java`

```java
package cn.xxx.admin.system.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.system.dto.PermissionQueryReq;
import cn.xxx.admin.system.dto.PermissionSaveReq;
import cn.xxx.admin.system.entity.Permission;
import cn.xxx.admin.system.service.PermissionService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "权限管理")
@RestController
@RequestMapping("/api/permissions")
@RequiredArgsConstructor
public class PermissionController {

    private final PermissionService permissionService;

    @Operation(summary = "权限列表")
    @GetMapping
    @SaCheckPermission("system:perm:list")
    public Result<Page<Permission>> list(PermissionQueryReq req) {
        return Result.success(permissionService.page(req));
    }

    @Operation(summary = "新增权限")
    @PostMapping
    @SaCheckPermission("system:perm:add")
    public Result<?> add(@Valid @RequestBody PermissionSaveReq req) {
        permissionService.save(req);
        return Result.success();
    }

    @Operation(summary = "权限详情")
    @GetMapping("/{id}")
    @SaCheckPermission("system:perm:query")
    public Result<Permission> get(@PathVariable Long id) {
        return Result.success(permissionService.getById(id));
    }

    @Operation(summary = "编辑权限")
    @PutMapping("/{id}")
    @SaCheckPermission("system:perm:edit")
    public Result<?> update(@PathVariable Long id, @Valid @RequestBody PermissionSaveReq req) {
        req.setId(id);
        permissionService.update(req);
        return Result.success();
    }

    @Operation(summary = "删除权限")
    @DeleteMapping("/{id}")
    @SaCheckPermission("system:perm:delete")
    public Result<?> delete(@PathVariable Long id) {
        permissionService.delete(id);
        return Result.success();
    }
}
```

---

## Phase 5: Log 日志模块

### Task 5.1: LoginLog.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/entity/LoginLog.java`

```java
package cn.xxx.admin.log.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("sys_login_log")
public class LoginLog {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String username;
    private String ip;
    private LocalDateTime loginTime;
    private Integer status;
    private String userAgent;
    private LocalDateTime createTime;
}
```

### Task 5.2: OperationLog.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/entity/OperationLog.java`

```java
package cn.xxx.admin.log.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("sys_operation_log")
public class OperationLog {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String username;
    private String module;
    private String action;
    private String method;
    private String params;
    private String result;
    private Long duration;
    private String ip;
    private LocalDateTime createTime;
}
```

### Task 5.3: LoginLogMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/mapper/LoginLogMapper.java`

```java
package cn.xxx.admin.log.mapper;

import cn.xxx.admin.log.entity.LoginLog;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface LoginLogMapper extends BaseMapper<LoginLog> {
}
```

### Task 5.4: OperationLogMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/mapper/OperationLogMapper.java`

```java
package cn.xxx.admin.log.mapper;

import cn.xxx.admin.log.entity.OperationLog;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface OperationLogMapper extends BaseMapper<OperationLog> {
}
```

### Task 5.5: LoginLogQueryReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/dto/LoginLogQueryReq.java`

```java
package cn.xxx.admin.log.dto;

import lombok.Data;

@Data
public class LoginLogQueryReq {
    private String username;
    private Integer status;
    private String startTime;
    private String endTime;
    private Integer pageNum = 1;
    private Integer pageSize = 10;
}
```

### Task 5.6: OperationLogQueryReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/dto/OperationLogQueryReq.java`

```java
package cn.xxx.admin.log.dto;

import lombok.Data;

@Data
public class OperationLogQueryReq {
    private String username;
    private String action;
    private String startTime;
    private String endTime;
    private Integer pageNum = 1;
    private Integer pageSize = 10;
}
```

### Task 5.7: LoginLogService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/service/LoginLogService.java`

```java
package cn.xxx.admin.log.service;

import cn.xxx.admin.log.dto.LoginLogQueryReq;
import cn.xxx.admin.log.entity.LoginLog;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface LoginLogService {
    Page<LoginLog> page(LoginLogQueryReq req);
}
```

### Task 5.8: LoginLogServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/service/impl/LoginLogServiceImpl.java`

```java
package cn.xxx.admin.log.service.impl;

import cn.xxx.admin.log.dto.LoginLogQueryReq;
import cn.xxx.admin.log.entity.LoginLog;
import cn.xxx.admin.log.mapper.LoginLogMapper;
import cn.xxx.admin.log.service.LoginLogService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Slf4j
@Service
@RequiredArgsConstructor
public class LoginLogServiceImpl extends ServiceImpl<LoginLogMapper, LoginLog> implements LoginLogService {

    private final LoginLogMapper loginLogMapper;

    @Override
    public Page<LoginLog> page(LoginLogQueryReq req) {
        LambdaQueryWrapper<LoginLog> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(req.getUsername())) {
            wrapper.like(LoginLog::getUsername, req.getUsername());
        }
        if (req.getStatus() != null) {
            wrapper.eq(LoginLog::getStatus, req.getStatus());
        }
        if (StringUtils.hasText(req.getStartTime())) {
            wrapper.ge(LoginLog::getLoginTime, LocalDateTime.parse(req.getStartTime(), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        }
        if (StringUtils.hasText(req.getEndTime())) {
            wrapper.le(LoginLog::getLoginTime, LocalDateTime.parse(req.getEndTime(), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        }
        wrapper.orderByDesc(LoginLog::getLoginTime);
        return loginLogMapper.selectPage(new Page<>(req.getPageNum(), req.getPageSize()), wrapper);
    }
}
```

### Task 5.9: OperationLogService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/service/OperationLogService.java`

```java
package cn.xxx.admin.log.service;

import cn.xxx.admin.log.dto.OperationLogQueryReq;
import cn.xxx.admin.log.entity.OperationLog;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface OperationLogService {
    Page<OperationLog> page(OperationLogQueryReq req);
}
```

### Task 5.10: OperationLogServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/service/impl/OperationLogServiceImpl.java`

```java
package cn.xxx.admin.log.service.impl;

import cn.xxx.admin.log.dto.OperationLogQueryReq;
import cn.xxx.admin.log.entity.OperationLog;
import cn.xxx.admin.log.mapper.OperationLogMapper;
import cn.xxx.admin.log.service.OperationLogService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Slf4j
@Service
@RequiredArgsConstructor
public class OperationLogServiceImpl extends ServiceImpl<OperationLogMapper, OperationLog> implements OperationLogService {

    private final OperationLogMapper operationLogMapper;

    @Override
    public Page<OperationLog> page(OperationLogQueryReq req) {
        LambdaQueryWrapper<OperationLog> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(req.getUsername())) {
            wrapper.like(OperationLog::getUsername, req.getUsername());
        }
        if (StringUtils.hasText(req.getAction())) {
            wrapper.like(OperationLog::getAction, req.getAction());
        }
        if (StringUtils.hasText(req.getStartTime())) {
            wrapper.ge(OperationLog::getCreateTime, LocalDateTime.parse(req.getStartTime(), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        }
        if (StringUtils.hasText(req.getEndTime())) {
            wrapper.le(OperationLog::getCreateTime, LocalDateTime.parse(req.getEndTime(), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        }
        wrapper.orderByDesc(OperationLog::getCreateTime);
        return operationLogMapper.selectPage(new Page<>(req.getPageNum(), req.getPageSize()), wrapper);
    }
}
```

### Task 5.11: @Log 注解

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/aspect/Log.java`

```java
package cn.xxx.admin.log.aspect;

import java.lang.annotation.*;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface Log {
    String module() default "";
    String action() default "";
}
```

### Task 5.12: LogAspect.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/aspect/LogAspect.java`

```java
package cn.xxx.admin.log.aspect;

import cn.dev33.satoken.stp.StpUtil;
import cn.xxx.admin.log.entity.OperationLog;
import cn.xxx.admin.log.mapper.OperationLogMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import jakarta.servlet.http.HttpServletRequest;
import java.time.LocalDateTime;

@Slf4j
@Aspect
@Component
@RequiredArgsConstructor
public class LogAspect {

    private final OperationLogMapper operationLogMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Pointcut("@annotation(cn.xxx.admin.log.aspect.Log)")
    public void logPointcut() {
    }

    @Around("logPointcut()")
    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        long startTime = System.currentTimeMillis();

        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        Log logAnnotation = signature.getMethod().getAnnotation(Log.class);

        OperationLog operationLog = new OperationLog();
        operationLog.setModule(logAnnotation.module());
        operationLog.setAction(logAnnotation.action());
        operationLog.setMethod(signature.getDeclaringTypeName() + "." + signature.getName() + "()");

        // 获取当前用户
        try {
            if (StpUtil.isLogin()) {
                operationLog.setUsername(StpUtil.getLoginIdAsString());
            } else {
                operationLog.setUsername("anonymous");
            }
        } catch (Exception e) {
            operationLog.setUsername("anonymous");
        }

        // 获取请求参数
        try {
            Object[] args = joinPoint.getArgs();
            // 过滤掉 HttpServletRequest 等非业务参数
            Object[] filteredArgs = new Object[args.length];
            int i = 0;
            for (Object arg : args) {
                if (!(arg instanceof HttpServletRequest)) {
                    filteredArgs[i++] = arg;
                }
            }
            operationLog.setParams(objectMapper.writeValueAsString(filteredArgs));
        } catch (Exception e) {
            operationLog.setParams("参数序列化失败");
        }

        // 获取 IP
        try {
            ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
            if (attributes != null) {
                HttpServletRequest request = attributes.getRequest();
                String ip = request.getHeader("X-Forwarded-For");
                if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
                    ip = request.getHeader("X-Real-IP");
                }
                if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
                    ip = request.getRemoteAddr();
                }
                operationLog.setIp(ip);
            }
        } catch (Exception e) {
            operationLog.setIp("unknown");
        }

        // 执行目标方法
        Object result;
        try {
            result = joinPoint.proceed();
            // 采集返回结果
            try {
                operationLog.setResult(objectMapper.writeValueAsString(result));
            } catch (Exception e) {
                operationLog.setResult("结果序列化失败");
            }
        } catch (Throwable e) {
            operationLog.setResult("异常: " + e.getMessage());
            throw e;
        } finally {
            operationLog.setDuration(System.currentTimeMillis() - startTime);
            operationLog.setCreateTime(LocalDateTime.now());
            operationLogMapper.insert(operationLog);
        }

        return result;
    }
}
```

### Task 5.13: LoginLogController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/controller/LoginLogController.java`

```java
package cn.xxx.admin.log.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.log.dto.LoginLogQueryReq;
import cn.xxx.admin.log.entity.LoginLog;
import cn.xxx.admin.log.service.LoginLogService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "登录日志")
@RestController
@RequestMapping("/api/logs")
@RequiredArgsConstructor
public class LoginLogController {

    private final LoginLogService loginLogService;

    @Operation(summary = "登录日志分页")
    @GetMapping("/login")
    @SaCheckPermission("log:login:list")
    public Result<Page<LoginLog>> list(LoginLogQueryReq req) {
        return Result.success(loginLogService.page(req));
    }
}
```

### Task 5.14: OperationLogController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/log/controller/OperationLogController.java`

```java
package cn.xxx.admin.log.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.log.dto.OperationLogQueryReq;
import cn.xxx.admin.log.entity.OperationLog;
import cn.xxx.admin.log.service.OperationLogService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "操作日志")
@RestController
@RequestMapping("/api/logs")
@RequiredArgsConstructor
public class OperationLogController {

    private final OperationLogService operationLogService;

    @Operation(summary = "操作日志分页")
    @GetMapping("/operation")
    @SaCheckPermission("log:operation:list")
    public Result<Page<OperationLog>> list(OperationLogQueryReq req) {
        return Result.success(operationLogService.page(req));
    }
}
```

---

## Phase 6: Dict 字典模块

### Task 6.1: DictType.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/entity/DictType.java`

```java
package cn.xxx.admin.dict.entity;

import cn.xxx.admin.common.base.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("sys_dict_type")
public class DictType extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String dictName;
    private String dictType;
    private Integer status;
}
```

### Task 6.2: DictItem.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/entity/DictItem.java`

```java
package cn.xxx.admin.dict.entity;

import cn.xxx.admin.common.base.BaseEntity;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("sys_dict_item")
public class DictItem extends BaseEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long dictTypeId;
    private String label;
    private String value;
    private Integer sort;
}
```

### Task 6.3: DictTypeMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/mapper/DictTypeMapper.java`

```java
package cn.xxx.admin.dict.mapper;

import cn.xxx.admin.dict.entity.DictType;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface DictTypeMapper extends BaseMapper<DictType> {
}
```

### Task 6.4: DictItemMapper.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/mapper/DictItemMapper.java`

```java
package cn.xxx.admin.dict.mapper;

import cn.xxx.admin.dict.entity.DictItem;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface DictItemMapper extends BaseMapper<DictItem> {
}
```

### Task 6.5: DictTypeSaveReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/dto/DictTypeSaveReq.java`

```java
package cn.xxx.admin.dict.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class DictTypeSaveReq {
    private Long id;
    @NotBlank(message = "字典名称不能为空")
    private String dictName;
    @NotBlank(message = "字典类型编码不能为空")
    private String dictType;
    private Integer status;
}
```

### Task 6.6: DictItemSaveReq.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/dto/DictItemSaveReq.java`

```java
package cn.xxx.admin.dict.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class DictItemSaveReq {
    private Long id;
    @NotNull(message = "字典类型ID不能为空")
    private Long dictTypeId;
    @NotBlank(message = "标签不能为空")
    private String label;
    @NotBlank(message = "值不能为空")
    private String value;
    private Integer sort;
}
```

### Task 6.7: DictTypeService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/service/DictTypeService.java`

```java
package cn.xxx.admin.dict.service;

import cn.xxx.admin.dict.dto.DictTypeSaveReq;
import cn.xxx.admin.dict.entity.DictType;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

public interface DictTypeService {
    Page<DictType> page(Integer pageNum, Integer pageSize);
    DictType getById(Long id);
    void save(DictTypeSaveReq req);
    void update(DictTypeSaveReq req);
    void delete(Long id);
}
```

### Task 6.8: DictTypeServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/service/impl/DictTypeServiceImpl.java`

```java
package cn.xxx.admin.dict.service.impl;

import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.dict.dto.DictTypeSaveReq;
import cn.xxx.admin.dict.entity.DictItem;
import cn.xxx.admin.dict.entity.DictType;
import cn.xxx.admin.dict.mapper.DictItemMapper;
import cn.xxx.admin.dict.mapper.DictTypeMapper;
import cn.xxx.admin.dict.service.DictTypeService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
public class DictTypeServiceImpl extends ServiceImpl<DictTypeMapper, DictType> implements DictTypeService {

    private final DictTypeMapper dictTypeMapper;
    private final DictItemMapper dictItemMapper;

    @Override
    public Page<DictType> page(Integer pageNum, Integer pageSize) {
        LambdaQueryWrapper<DictType> wrapper = new LambdaQueryWrapper<>();
        wrapper.orderByDesc(DictType::getCreateTime);
        return dictTypeMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public DictType getById(Long id) {
        DictType dictType = dictTypeMapper.selectById(id);
        if (dictType == null) {
            throw new BusinessException(4001, "字典类型不存在");
        }
        return dictType;
    }

    @Override
    @Transactional
    public void save(DictTypeSaveReq req) {
        boolean exists = dictTypeMapper.exists(new LambdaQueryWrapper<DictType>()
                .eq(DictType::getDictType, req.getDictType()));
        if (exists) {
            throw new BusinessException(BusinessErrorEnum.DICT_TYPE_EXISTS);
        }
        DictType dictType = new DictType();
        dictType.setDictName(req.getDictName());
        dictType.setDictType(req.getDictType());
        dictType.setStatus(req.getStatus() != null ? req.getStatus() : 1);
        dictTypeMapper.insert(dictType);
    }

    @Override
    @Transactional
    public void update(DictTypeSaveReq req) {
        DictType dictType = dictTypeMapper.selectById(req.getId());
        if (dictType == null) {
            throw new BusinessException(4001, "字典类型不存在");
        }
        dictType.setDictName(req.getDictName());
        dictType.setDictType(req.getDictType());
        if (req.getStatus() != null) {
            dictType.setStatus(req.getStatus());
        }
        dictTypeMapper.updateById(dictType);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        DictType dictType = dictTypeMapper.selectById(id);
        if (dictType == null) {
            throw new BusinessException(4001, "字典类型不存在");
        }
        dictTypeMapper.deleteById(id);
        dictItemMapper.delete(new LambdaQueryWrapper<DictItem>().eq(DictItem::getDictTypeId, id));
    }
}
```

### Task 6.9: DictItemService.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/service/DictItemService.java`

```java
package cn.xxx.admin.dict.service;

import cn.xxx.admin.dict.dto.DictItemSaveReq;
import cn.xxx.admin.dict.entity.DictItem;

import java.util.List;

public interface DictItemService {
    List<DictItem> listByDictType(String dictType);
    DictItem getById(Long id);
    void save(DictItemSaveReq req);
    void update(DictItemSaveReq req);
    void delete(Long id);
}
```

### Task 6.10: DictItemServiceImpl.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/service/impl/DictItemServiceImpl.java`

```java
package cn.xxx.admin.dict.service.impl;

import cn.xxx.admin.common.exception.BusinessErrorEnum;
import cn.xxx.admin.common.exception.BusinessException;
import cn.xxx.admin.dict.dto.DictItemSaveReq;
import cn.xxx.admin.dict.entity.DictItem;
import cn.xxx.admin.dict.entity.DictType;
import cn.xxx.admin.dict.mapper.DictItemMapper;
import cn.xxx.admin.dict.mapper.DictTypeMapper;
import cn.xxx.admin.dict.service.DictItemService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class DictItemServiceImpl extends ServiceImpl<DictItemMapper, DictItem> implements DictItemService {

    private final DictItemMapper dictItemMapper;
    private final DictTypeMapper dictTypeMapper;

    @Override
    public List<DictItem> listByDictType(String dictType) {
        DictType type = dictTypeMapper.selectOne(new LambdaQueryWrapper<DictType>()
                .eq(DictType::getDictType, dictType));
        if (type == null) {
            throw new BusinessException(4001, "字典类型不存在");
        }
        return dictItemMapper.selectList(new LambdaQueryWrapper<DictItem>()
                .eq(DictItem::getDictTypeId, type.getId())
                .orderByAsc(DictItem::getSort));
    }

    @Override
    public DictItem getById(Long id) {
        DictItem item = dictItemMapper.selectById(id);
        if (item == null) {
            throw new BusinessException(4002, "字典项不存在");
        }
        return item;
    }

    @Override
    @Transactional
    public void save(DictItemSaveReq req) {
        DictItem item = new DictItem();
        item.setDictTypeId(req.getDictTypeId());
        item.setLabel(req.getLabel());
        item.setValue(req.getValue());
        item.setSort(req.getSort() != null ? req.getSort() : 0);
        dictItemMapper.insert(item);
    }

    @Override
    @Transactional
    public void update(DictItemSaveReq req) {
        DictItem item = dictItemMapper.selectById(req.getId());
        if (item == null) {
            throw new BusinessException(4002, "字典项不存在");
        }
        item.setDictTypeId(req.getDictTypeId());
        item.setLabel(req.getLabel());
        item.setValue(req.getValue());
        if (req.getSort() != null) {
            item.setSort(req.getSort());
        }
        dictItemMapper.updateById(item);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        DictItem item = dictItemMapper.selectById(id);
        if (item == null) {
            throw new BusinessException(4002, "字典项不存在");
        }
        dictItemMapper.deleteById(id);
    }
}
```

### Task 6.11: DictTypeController.java

**文件:** `admin-test-04/src/main/java/cn/xxx/admin/dict/controller/DictTypeController.java`

```java
package cn.xxx.admin.dict.controller;

import cn.dev33.satoken.annotation.SaCheckLogin;
import cn.dev33.satoken.annotation.SaCheckPermission;
import cn.xxx.admin.common.result.Result;
import cn.xxx.admin.dict.dto.DictTypeSaveReq;
import cn.xxx.admin.dict.entity.DictItem;
import cn.xxx.admin.dict.entity.DictType;
import cn.xxx.admin.dict.service.DictItemService;
import cn.xxx.admin.dict.service.DictTypeService;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(name = "字典管理")
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class DictTypeController {

    private final DictTypeService dictTypeService;
    private final DictItemService dictItemService;

    // ========== 字典类型 ==========

    @Operation(summary = "字典类型列表")
    @GetMapping("/dict-types")
    @SaCheckPermission("dict:type:list")
    public Result<Page<DictType>> list(
            @RequestParam(defaultValue = "1") Integer pageNum,
            @RequestParam(defaultValue = "10") Integer pageSize) {
        return Result.success(dictTypeService.page(pageNum, pageSize));
    }

    @Operation(summary = "新增字典类型")
    @PostMapping("/dict-types")
    @SaCheckPermission("dict:type:add")
    public Result<?> add(@Valid @RequestBody DictTypeSaveReq req) {
        dictTypeService.save(req);
        return Result.success();
    }

    @Operation(summary = "字典类型详情")
    @GetMapping("/dict-types/{id}")
    @SaCheckPermission("dict:type:query")
    public Result<DictType> get(@PathVariable Long id) {
        return Result.success(dictTypeService.getById(id));
    }

    @Operation(summary = "编辑字典类型")
    @PutMapping("/dict-types/{id}")
    @SaCheckPermission("dict:type:edit")
    public Result<?> update(@PathVariable Long id, @Valid @RequestBody DictTypeSaveReq req) {
        req.setId(id);
        dictTypeService.update(req);
        return Result.success();
    }

    @Operation(summary = "删除字典类型")
    @DeleteMapping("/dict-types/{id}")
    @SaCheckPermission("dict:type:delete")
    public Result<?> delete(@PathVariable Long id) {
        dictTypeService.delete(id);
        return Result.success();
    }

    // ========== 字典项 ==========

    @Operation(summary = "按类型编码获取字典项")
    @GetMapping("/dict-types/{type}/items")
    @SaCheckLogin
    public Result<List<DictItem>> listItems(@PathVariable String type) {
        return Result.success(dictItemService.listByDictType(type));
    }

    @Operation(summary = "新增字典项")
    @PostMapping("/dict-items")
    @SaCheckPermission("dict:item:add")
    public Result<?> addItem(@Valid @RequestBody DictItemSaveReq req) {
        dictItemService.save(req);
        return Result.success();
    }

    @Operation(summary = "编辑字典项")
    @PutMapping("/dict-items/{id}")
    @SaCheckPermission("dict:item:edit")
    public Result<?> updateItem(@PathVariable Long id, @Valid @RequestBody DictItemSaveReq req) {
        req.setId(id);
        dictItemService.update(req);
        return Result.success();
    }

    @Operation(summary = "删除字典项")
    @DeleteMapping("/dict-items/{id}")
    @SaCheckPermission("dict:item:delete")
    public Result<?> deleteItem(@PathVariable Long id) {
        dictItemService.delete(id);
        return Result.success();
    }
}
```

---

## Phase 7: SQL 初始化脚本

### Task 7.1: init.sql

**文件:** `admin-test-04/src/main/resources/db/init.sql`

```sql
-- 创建数据库
CREATE DATABASE IF NOT EXISTS admin_demo DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE admin_demo;

-- ==================== RBAC 核心 ====================

-- 用户表
CREATE TABLE IF NOT EXISTS sys_user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    username VARCHAR(50) NOT NULL COMMENT '用户名',
    password VARCHAR(255) NOT NULL COMMENT '密码（BCrypt加密）',
    status TINYINT DEFAULT 1 COMMENT '状态：1启用 0禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 角色表
CREATE TABLE IF NOT EXISTS sys_role (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '角色ID',
    role_name VARCHAR(50) NOT NULL COMMENT '角色名称',
    role_code VARCHAR(50) NOT NULL COMMENT '角色编码',
    description VARCHAR(200) COMMENT '描述',
    status TINYINT DEFAULT 1 COMMENT '状态：1启用 0禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';

-- 权限表
CREATE TABLE IF NOT EXISTS sys_permission (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '权限ID',
    perm_name VARCHAR(50) NOT NULL COMMENT '权限名称',
    perm_code VARCHAR(100) NOT NULL COMMENT '权限标识',
    url VARCHAR(200) COMMENT '接口路径',
    method VARCHAR(10) COMMENT '请求方法',
    description VARCHAR(200) COMMENT '描述',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_perm_code (perm_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='权限表';

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS sys_user_role (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    role_id BIGINT NOT NULL COMMENT '角色ID',
    UNIQUE KEY uk_user_role (user_id, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户角色关联表';

-- 角色权限关联表
CREATE TABLE IF NOT EXISTS sys_role_permission (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    role_id BIGINT NOT NULL COMMENT '角色ID',
    permission_id BIGINT NOT NULL COMMENT '权限ID',
    UNIQUE KEY uk_role_perm (role_id, permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色权限关联表';

-- ==================== 日志 ====================

-- 登录日志表
CREATE TABLE IF NOT EXISTS sys_login_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    username VARCHAR(50) NOT NULL COMMENT '用户名',
    ip VARCHAR(50) COMMENT '登录IP',
    login_time DATETIME COMMENT '登录时间',
    status TINYINT DEFAULT 1 COMMENT '状态：1成功 0失败',
    user_agent VARCHAR(500) COMMENT '浏览器User-Agent',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    KEY idx_username (username),
    KEY idx_login_time (login_time),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志表';

-- 操作日志表
CREATE TABLE IF NOT EXISTS sys_operation_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    username VARCHAR(50) COMMENT '操作用户',
    module VARCHAR(50) COMMENT '操作模块',
    action VARCHAR(50) COMMENT '操作类型',
    method VARCHAR(200) COMMENT '方法名',
    params TEXT COMMENT '请求参数JSON',
    result TEXT COMMENT '返回结果JSON',
    duration BIGINT COMMENT '耗时（毫秒）',
    ip VARCHAR(50) COMMENT '请求IP',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    KEY idx_username (username),
    KEY idx_action (action),
    KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';

-- ==================== 字典 ====================

-- 字典类型表
CREATE TABLE IF NOT EXISTS sys_dict_type (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    dict_name VARCHAR(50) NOT NULL COMMENT '字典名称',
    dict_type VARCHAR(50) NOT NULL COMMENT '字典类型编码',
    status TINYINT DEFAULT 1 COMMENT '状态：1启用 0禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_dict_type (dict_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='字典类型表';

-- 字典项表
CREATE TABLE IF NOT EXISTS sys_dict_item (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    dict_type_id BIGINT NOT NULL COMMENT '字典类型ID',
    label VARCHAR(100) NOT NULL COMMENT '标签',
    value VARCHAR(100) NOT NULL COMMENT '值',
    sort INT DEFAULT 0 COMMENT '排序',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    KEY idx_dict_type_id (dict_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='字典项表';

-- ==================== 初始数据 ====================

-- 默认管理员账号：admin / admin123 (BCrypt加密，coder 需用 BCryptPasswordEncoder 生成替换此 hash)
INSERT INTO sys_user (username, password, status) VALUES
('admin', '$2a$10$EixZaYVK1fsbw1ZfbX3OXe.P0jFGmOGOaj0JXciKCp1LhPqK/sFDy', 1);

-- 角色
INSERT INTO sys_role (role_name, role_code, description) VALUES
('超级管理员', 'admin', '拥有所有权限'),
('普通用户', 'user', '基础权限');

-- 权限
INSERT INTO sys_permission (perm_name, perm_code, url, method) VALUES
-- 用户管理
('用户列表', 'system:user:list', '/api/users', 'GET'),
('新增用户', 'system:user:add', '/api/users', 'POST'),
('用户详情', 'system:user:query', '/api/users/*', 'GET'),
('编辑用户', 'system:user:edit', '/api/users/*', 'PUT'),
('删除用户', 'system:user:delete', '/api/users/*', 'DELETE'),
('分配角色', 'system:user:assign-role', '/api/users/*/roles', 'PUT'),
-- 角色管理
('角色列表', 'system:role:list', '/api/roles', 'GET'),
('新增角色', 'system:role:add', '/api/roles', 'POST'),
('角色详情', 'system:role:query', '/api/roles/*', 'GET'),
('编辑角色', 'system:role:edit', '/api/roles/*', 'PUT'),
('删除角色', 'system:role:delete', '/api/roles/*', 'DELETE'),
('分配权限', 'system:role:assign-perm', '/api/roles/*/permissions', 'PUT'),
-- 权限管理
('权限列表', 'system:perm:list', '/api/permissions', 'GET'),
('新增权限', 'system:perm:add', '/api/permissions', 'POST'),
('权限详情', 'system:perm:query', '/api/permissions/*', 'GET'),
('编辑权限', 'system:perm:edit', '/api/permissions/*', 'PUT'),
('删除权限', 'system:perm:delete', '/api/permissions/*', 'DELETE'),
-- 日志
('登录日志', 'log:login:list', '/api/logs/login', 'GET'),
('操作日志', 'log:operation:list', '/api/logs/operation', 'GET'),
-- 字典
('字典类型列表', 'dict:type:list', '/api/dict-types', 'GET'),
('新增字典类型', 'dict:type:add', '/api/dict-types', 'POST'),
('字典类型详情', 'dict:type:query', '/api/dict-types/*', 'GET'),
('编辑字典类型', 'dict:type:edit', '/api/dict-types/*', 'PUT'),
('删除字典类型', 'dict:type:delete', '/api/dict-types/*', 'DELETE'),
('新增字典项', 'dict:item:add', '/api/dict-items', 'POST'),
('编辑字典项', 'dict:item:edit', '/api/dict-items/*', 'PUT'),
('删除字典项', 'dict:item:delete', '/api/dict-items/*', 'DELETE');

-- 为 admin 用户分配 admin 角色
INSERT INTO sys_user_role (user_id, role_id) VALUES (1, 1);

-- 为 admin 角色分配所有权限
INSERT INTO sys_role_permission (role_id, permission_id)
SELECT 1, id FROM sys_permission;

-- 字典类型初始数据
INSERT INTO sys_dict_type (dict_name, dict_type) VALUES
('用户状态', 'sys_user_status'),
('操作类型', 'sys_operation_type');

-- 字典项初始数据
INSERT INTO sys_dict_item (dict_type_id, label, value, sort) VALUES
(1, '启用', '1', 1),
(1, '禁用', '0', 2),
(2, '新增', 'add', 1),
(2, '编辑', 'edit', 2),
(2, '删除', 'delete', 3),
(2, '查询', 'query', 4),
(2, '导出', 'export', 5);
```

---

## Phase 8: README 启动说明

### Task 8.1: README.md

**文件:** `admin-test-04/README.md`

```markdown
# 后台管理系统 Demo

Spring Boot 3 后台管理系统纯后端 API Demo，包含用户注册登录、RBAC 权限、登录/操作日志、字典管理。

## 技术栈

- Spring Boot 3.2
- Sa-Token 1.37 + JWT
- MyBatis-Plus 3.5
- MySQL
- Knife4j (Swagger 增强)
- BCrypt 密码加密

## 快速启动

### 1. 数据库初始化

```bash
mysql -u root -p < src/main/resources/db/init.sql
```

JDBC URL: `jdbc:mysql://localhost:3306/admin_demo`

### 2. 修改配置

编辑 `src/main/resources/application.yml`，修改数据库用户名密码：

```yaml
spring:
  datasource:
    username: root
    password: 你的密码
```

### 3. 启动

```bash
mvn spring-boot:run
```

### 4. 访问 Swagger

http://localhost:8080/doc.html

## 初始化账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 超级管理员 |

## 接口模块

| 模块 | 路径前缀 | 说明 |
|------|---------|------|
| 认证 | /api/auth | 注册、登录、登出、用户信息 |
| 用户管理 | /api/users | 用户 CRUD + 分配角色 |
| 角色管理 | /api/roles | 角色 CRUD + 分配权限 |
| 权限管理 | /api/permissions | 权限 CRUD |
| 登录日志 | /api/logs/login | 登录日志分页查询 |
| 操作日志 | /api/logs/operation | 操作日志分页查询 |
| 字典类型 | /api/dict-types | 字典类型 CRUD + 按编码查字典项 |
| 字典项 | /api/dict-items | 字典项 CRUD |

## API 鉴权说明

所有接口（除 `/api/auth/login` 和 `/api/auth/register`）需要携带 Token：

```
Header: Authorization = <token>
```

使用 `@SaCheckPermission` 注解控制接口级权限，权限标识如 `system:user:add`。

## 项目结构

```
cn.xxx.admin/
├── common/      # 全局基础设施（Result、异常、配置）
├── auth/        # 认证（注册登录）
├── system/      # RBAC（用户/角色/权限）
├── log/         # 日志（登录日志/操作日志AOP）
└── dict/        # 字典
```
```

---

## 验证清单

| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| Maven 编译 | `cd admin-test-04 && mvn compile` | BUILD SUCCESS |
| 文件数量 | `find admin-test-04/src/main/java -name "*.java" \| wc -l` | ≥ 55 |
| Result<T> 统一 | `grep -r "Result<" admin-test-04/src/main/java` | 所有 Controller 返回 Result |
| 构造注入 | `grep -r "@Autowired" admin-test-04/src/main/java` 应为空 | 0 个 @Autowired |
| @Slf4j 日志 | `grep -r "@Slf4j" admin-test-04/src/main/java` | 所有 ServiceImpl 有 @Slf4j |
| URL RESTful | 抽查 Controller | 复数名词，无动词 CRUD URL |

---

## 边界约束

- coder 只能修改 `admin-test-04/` 目录下的文件
- **禁止**修改 `agents/` 或 `hooks/` 目录下的任何文件
- **禁止**修改 `review-output/` 目录
- 遵循 `agents/coder/` 中的架构规范
