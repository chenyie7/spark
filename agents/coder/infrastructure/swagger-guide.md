# Swagger/Knife4j 接口文档规范

> 适用：Spring Boot 3 + Knife4j（OpenAPI 3.0），单体 + Spring Cloud Gateway 微服务聚合

---

## 一、版本与依赖

```xml
<!-- 单体 / 业务服务 -->
<dependency>
    <groupId>com.github.xiaoymin</groupId>
    <artifactId>knife4j-openapi3-jakarta-spring-boot-starter</artifactId>
    <version>4.5.0</version>
</dependency>

<!-- Gateway 聚合（微服务模式） -->
<dependency>
    <groupId>com.github.xiaoymin</groupId>
    <artifactId>knife4j-gateway-spring-boot-starter</artifactId>
    <version>4.5.0</version>
</dependency>
```

---

## 二、单体 / 业务服务配置

### 2.1 配置类

```java
package com.chenyi.{project}.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.Contact;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Knife4jConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("用户服务 API")
                .description("用户管理相关接口")
                .version("1.0.0")
                .contact(new Contact().name("chenyi"))
            );
    }
}
```

### 2.2 application.yml

```yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html       # 原生路径
  api-docs:
    path: /v3/api-docs           # OpenAPI 文档 JSON 路径（网关聚合需要）

knife4j:
  enable: true
  setting:
    language: zh_CN
```

### 2.3 访问路径

```
单体：http://localhost:{port}/doc.html
微服务各服务：http://localhost:{port}/doc.html
网关聚合：http://localhost:8080/doc.html
```

---

## 三、注解规范

### 3.1 注解层级

| 位置 | 注解 | 作用 | 必须 |
|------|------|------|------|
| Controller 类 | `@Tag(name = "模块名")` | 接口分组 | ✅ |
| Controller 方法 | `@Operation(summary = "描述")` | 接口说明 | ✅ |
| GET 平铺参数 / `@PathVariable` | `@Parameter(description = "描述")` | 参数说明 | ✅ |
| DTO 字段 | `@Schema(description = "描述", requiredMode = ...)` | 入参字段说明 | ✅ |
| VO 字段 | `@Schema(description = "描述")` | 出参字段说明 | ✅ |

### 3.2 Controller 示例

```java
@Tag(name = "用户管理")
@RestController
@RequestMapping("/api/users")
public class UserController {

    @Operation(summary = "分页查询用户")
    @GetMapping
    public Result<PageResult<UserVO>> page(@Validated UserPageQueryDTO dto) {
        ...
    }

    @Operation(summary = "根据ID查询用户")
    @GetMapping("/{id}")
    public Result<UserVO> get(
        @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        ...
    }

    @Operation(summary = "新增用户")
    @PostMapping
    public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) {
        ...
    }

    @Operation(summary = "重置用户密码")
    @PostMapping("/{id}/reset-password")
    public Result<Void> resetPassword(
        @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        ...
    }
}
```

### 3.3 DTO 字段示例

```java
public class UserCreateDTO {

    @Schema(description = "用户名", requiredMode = RequiredMode.REQUIRED, example = "zhangsan")
    @NotNull(message = "{user.username.notnull}", groups = Create.class)
    private String username;

    @Schema(description = "邮箱", requiredMode = RequiredMode.NOT_REQUIRED, example = "zhangsan@example.com")
    private String email;
}
```

**`requiredMode` 必须与校验注解保持一致：**

| `@Schema` | 对应校验注解 |
|-----------|------------|
| `requiredMode = RequiredMode.REQUIRED` | `@NotNull`、`@NotBlank`、`@NotEmpty` |
| `requiredMode = RequiredMode.NOT_REQUIRED`（默认） | 无必填校验注解 |

### 3.4 VO 字段示例

```java
public class UserVO {

    @Schema(description = "用户ID")
    private Long id;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "邮箱")
    private String email;

    @Schema(description = "创建时间", example = "2024-01-01 12:00:00")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createTime;
}
```

**VO 每个字段必须加 `@Schema(description = "...")`**，禁止裸字段，确保生成的文档可读。

---

## 四、微服务聚合模式

### 4.1 架构

```
用户浏览器 → http://gateway:8080/doc.html
                    │
            Spring Cloud Gateway (聚合入口)
               /v3/api-docs/user      → user-service
               /v3/api-docs/order     → order-service
               /v3/api-docs/payment   → payment-service
```

### 4.2 各业务服务配置

每个业务服务在 `application.yml` 中配置 `springdoc.group-configs`，一个服务一个分组：

```yaml
# business-user
springdoc:
  group-configs:
    - group: 'user'
      paths-to-match: '/api/**'

# business-order
springdoc:
  group-configs:
    - group: 'order'
      paths-to-match: '/api/**'
```

### 4.3 Gateway 聚合配置

```yaml
# project-gateway application.yml
knife4j:
  gateway:
    enabled: true
    strategy: manual                    # 手动配置 aggregator
    routes:
      - name: 用户服务
        service-name: user-service
        url: http://localhost:8081/v3/api-docs
        context-path: /user             # 子服务路径前缀
      - name: 订单服务
        service-name: order-service
        url: http://localhost:8082/v3/api-docs
        context-path: /order
```

或者采用**服务发现模式**（Nacos）：

```yaml
knife4j:
  gateway:
    enabled: true
    strategy: discover                  # 自动发现
    discover:
      enabled: true
      service-mappings:
        - name: user-service
          group-name: 用户服务
```

---

## 五、禁止事项

| 禁止 | 原因 |
|------|------|
| VO/DTO 字段不加 `@Schema(description = "...")` | 生成的文档字段无描述，调用方无法理解 |
| Controller 不加 `@Tag` | 接口无分组，文档页面混乱 |
| `@Schema.requiredMode` 与校验注解不一致 | 文档标注必填但实际不校验，或反之 |
| 生产环境 `knife4j.enable: true` | 安全隐患，生产应关闭：`knife4j.enable: false` |

---

## 六、环境隔离

```yaml
# application-dev.yml（开发/测试开启）
knife4j:
  enable: true

# application-prod.yml（生产关闭）
knife4j:
  enable: false
```

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../layered/controller-guide.md` | `@Tag` / `@Operation` 使用位置 |
| `../quality/i18n-guide.md` | DTO 字段 `@NotNull` 校验注解 |
| `result-guide.md` | 统一返回体 `Result<T>` |
