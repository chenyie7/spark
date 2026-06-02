# 基础认证授权规范

> 适用：单个 Spring Boot 应用，SaToken JWT + RBAC 权限控制

---

## 前置确认

在按本文件开发前，**必须先向用户确认**：

> 是否需要多端隔离、多系统隔离、SSO、OAuth2？

- 如果**全部不需要** → 只读本文件，不读 auth 目录下的其他文件。**纯后台管理项目直接用 `StpUtil`，跳到下面的"分岔路口"看跳读路径。**
- 如果需要某些 → 读本文件 + 对应文件（见 `auth-overview.md`），需要 StpKit 门面模式

---

## 分岔路口

### 纯后台管理项目（无用户端，无多系统）

直接用 SaToken 内置的 `StpUtil`，**不需要** StpKit 门面、LoginContextHolder 等。按以下路径跳读：

| 章节 | 是否必读 | 说明 |
|------|---------|------|
| 一、依赖 | ✅ 必读 | 依赖不变 |
| 二、三、五、八 | ❌ 跳过 | StpKit/LoginContextHolder/自定义注解仅多端场景需要 |
| 四 yml 部分 | ✅ 必读 | `application.yml` 中 sa-token 配置 |
| 四 Java 配置类 | ❌ 跳过 | Java 配置类仅多端场景需要 |
| 六、七 | ✅ 必读 | 权限码 + 权限注解（去掉 `type = "xxx"` 属性） |
| 九 | ✅ 必读 | 拦截器，只需一个 `StpUtil.checkLogin()` |
| 十 | ❌ 跳过 | LoginContextHolder 仅多端需要 |
| 十一 | ✅ 必读 | 禁止事项 |

登录示例（简单模式）：

```java
@Operation(summary = "登录")
@PostMapping("/login")
public Result<LoginVO> login(@RequestBody @Validated AuthLoginDTO dto) {
    UserEntity user = userService.auth(dto.getUsername(), dto.getPassword());
    StpUtil.login(user.getId());
    return Result.success(new LoginVO(user.getId(), StpUtil.getTokenValue()));
}

@Operation(summary = "登出")
@PostMapping("/logout")
public Result<Void> logout() {
    StpUtil.logout();
    return Result.success();
}
```

拦截器示例（简单模式，单个即可）：

```java
registry.addInterceptor(new SaInterceptor(handle -> StpUtil.checkLogin()))
    .addPathPatterns("/api/**")
    .excludePathPatterns("/api/auth/login");
```

### 多端 / 多系统 / SSO / OAuth2 项目

需要 StpKit 门面管理多个 `StpLogic` 实例。继续阅读以下**全部章节**。

---

## 一、依赖

```xml
<!-- SaToken 核心 -->
<dependency>
    <groupId>cn.dev33</groupId>
    <artifactId>sa-token-spring-boot3-starter</artifactId>
    <version>1.39.0</version>
</dependency>
<!-- SaToken JWT 扩展 -->
<dependency>
    <groupId>cn.dev33</groupId>
    <artifactId>sa-token-jwt</artifactId>
    <version>1.39.0</version>
</dependency>
```

---

## 二、StpKit 门面模式（多端）

使用 `StpKit` 统一管理所有账号体系的 `StpLogic` 实例，替代直接使用 `StpUtil`：

```java
package com.chenyi.{project}.config;

import cn.dev33.satoken.stp.StpLogic;
import cn.dev33.satoken.stp.StpUtil;

public final class StpKit {

    private StpKit() {}

    /** 默认体系（内部使用） */
    public static final StpLogic DEFAULT = StpUtil.stpLogic;

    /** 用户端 */
    public static final StpLogic USER = new StpLogic("user");

    /** 管理端 */
    public static final StpLogic ADMIN = new StpLogic("admin");
}
```

---

## 三、LoginContextHolder（多端）

通用组件（`MetaObjectHandler`、Service 层）不能硬编码 `StpKit.USER` —— 它们不知道当前请求属于哪个系统/哪个端。通过 `LoginContextHolder` 让拦截器或网关设置当前 `StpLogic`，通用代码从 Holder 取：

```java
package com.chenyi.{project}.context;

import cn.dev33.satoken.stp.StpLogic;

public final class LoginContextHolder {
    private static final ThreadLocal<StpLogic> HOLDER = new ThreadLocal<>();

    public static void set(StpLogic stp) { HOLDER.set(stp); }
    public static StpLogic get() { return HOLDER.get(); }
    public static void clear() { HOLDER.remove(); }

    /** 获取当前用户ID */
    public static Long getUserId() {
        StpLogic stp = HOLDER.get();
        return stp != null ? stp.getLoginIdAsLong() : null;
    }

    /** 获取当前用户名 */
    public static String getUserName() {
        StpLogic stp = HOLDER.get();
        if (stp == null) return null;
        return (String) stp.getSession().get("userName");
    }
}
```

**如何设置：** 拦截器或网关中校验登录后立即调用 `LoginContextHolder.set(stp)`，请求完成后调用 `clear()`。

---

## 四、基础配置

不同账号体系可独立配置：

```yaml
# application.yml
sa-token:
  token-name: satoken
  timeout: 2592000
  is-log: false
  token-style: jwt                        # JWT 模式，不使用 UUID
  jwt-secret-key: ${JWT_SECRET_KEY}       # JWT 密钥，从环境变量注入
```

```java
package com.chenyi.{project}.config;

import cn.dev33.satoken.config.SaTokenConfig;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SaTokenCustomConfig {

    static {
        // 用户端：30天有效，不限无操作时间
        SaTokenConfig userConfig = new SaTokenConfig();
        userConfig.setTokenName("satoken-user");
        userConfig.setTimeout(2592000);
        userConfig.setActiveTimeout(-1);
        StpKit.USER.setConfig(userConfig);

        // 管理端：2小时有效，30分钟无操作
        SaTokenConfig adminConfig = new SaTokenConfig();
        adminConfig.setTokenName("satoken-admin");
        adminConfig.setTimeout(7200);
        adminConfig.setActiveTimeout(1800);
        StpKit.ADMIN.setConfig(adminConfig);
    }
}
```

---

## 五、登录接口（多端）

用户端和管理端登录分开为两个 Controller，对应不同的 URL 前缀和拦截器规则：

```java
@Tag(name = "认证管理")
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    @Operation(summary = "用户端登录")
    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Validated AuthLoginDTO dto) {
        UserEntity user = userService.auth(dto.getUsername(), dto.getPassword());
        StpKit.USER.login(user.getId());
        return Result.success(new LoginVO(user.getId(), StpKit.USER.getTokenValue()));
    }

    @Operation(summary = "登出")
    @PostMapping("/logout")
    public Result<Void> logout() {
        StpLogic stp = LoginContextHolder.get();
        if (stp != null) {
            stp.logout();
        }
        return Result.success();
    }
}

@Tag(name = "管理端认证")
@RestController
@RequestMapping("/api/admin/auth")
public class AdminAuthController {

    @Operation(summary = "管理端登录")
    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Validated AuthLoginDTO dto) {
        UserEntity admin = userService.authAdmin(dto.getUsername(), dto.getPassword());
        StpKit.ADMIN.login(admin.getId());
        return Result.success(new LoginVO(admin.getId(), StpKit.ADMIN.getTokenValue()));
    }
}
```

---

## 六、权限码定义

权限码统一在常量类中定义：

```java
package com.chenyi.{project}.constant;

public final class PermissionCodes {
    private PermissionCodes() {}

    public static final String USER_VIEW = "user:view";
    public static final String USER_CREATE = "user:create";
    public static final String USER_UPDATE = "user:update";
    public static final String USER_DELETE = "user:delete";
    public static final String ORDER_VIEW = "order:view";
    public static final String ORDER_CANCEL = "order:cancel";
}
```

---

## 七、接口权限控制

权限注解**只放在 Controller 方法上**，不放在 Service 层：

```java
// 用户端登录校验
@SaCheckLogin(type = "user")
@GetMapping("/{id}")
public Result<UserVO> get(...) { ... }

// 管理端登录校验
@SaCheckLogin(type = "admin")
@DeleteMapping("/{id}")
public Result<Void> delete(...) { ... }

// 方法级权限
@SaCheckPermission(value = PermissionCodes.USER_CREATE, type = "user")
@PostMapping
public Result<Void> create(...) { ... }

// 角色级权限
@SaCheckRole(value = "ADMIN", type = "admin")
@DeleteMapping("/{id}")
public Result<Void> delete(...) { ... }
```

---

## 八、自定义注解合并（多端，推荐）

避免每个接口写 `type = "user"`，通过自定义注解简化：

```java
package com.chenyi.{project}.annotation;

import cn.dev33.satoken.annotation.SaCheckLogin;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@SaCheckLogin(type = "user")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaUserCheckLogin {}

@SaCheckLogin(type = "admin")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaAdminCheckLogin {}

@SaCheckPermission(type = "user")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaUserCheckPermission {
    @AliasFor(annotation = SaCheckPermission.class, attribute = "value")
    String value();
}
```

```java
// 配置类中启用注解合并
@Configuration
public class SaTokenConfigure {
    @PostConstruct
    public void rewriteSaStrategy() {
        SaAnnotationStrategy.instance.getAnnotation =
            (element, annotationClass) -> AnnotatedElementUtils.getMergedAnnotation(element, annotationClass);
    }
}
```

使用：

```java
@SaUserCheckLogin
@GetMapping("/{id}")
public Result<UserVO> get(...) { ... }

@SaUserCheckPermission(PermissionCodes.USER_CREATE)
@PostMapping
public Result<Void> create(...) { ... }
```

---

## 九、路由拦截器

```java
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // 管理端路由
        registry.addInterceptor(new SaInterceptor(handle -> {
                    StpKit.ADMIN.checkLogin();
                    LoginContextHolder.set(StpKit.ADMIN);       // 设置当前体系
                }))
                .addPathPatterns("/api/admin/**")
                .excludePathPatterns("/api/admin/auth/login");

        // 用户端路由
        registry.addInterceptor(new SaInterceptor(handle -> {
                    StpKit.USER.checkLogin();
                    LoginContextHolder.set(StpKit.USER);        // 设置当前体系
                }))
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/auth/login", "/api/auth/register",
                        "/api/public/**", "/doc.html", "/v3/api-docs/**", "/api/admin/**");
    }
}
```

---

## 十、Service 层获取用户（多端）

通过 `LoginContextHolder` 获取当前用户，不硬编码 `StpKit.USER`：

```java
import com.chenyi.{project}.context.LoginContextHolder;

@Service
public class UserServiceImpl implements UserService {

    @Override
    public void create(UserCreateDTO dto) {
        Long currentUserId = LoginContextHolder.getUserId();
        ...
    }
}
```

非 HTTP 场景（定时任务等）通过业务参数传入操作用户，不依赖 `LoginContextHolder`。

---

## 十一、禁止事项

| 禁止 | 原因 |
|------|------|
| 直接使用 `StpUtil` 跨账号体系统一切换 | 用 `StpKit.USER` / `StpKit.ADMIN` 门面 |
| 权限注解放 Service 层 | 权限控制是接口层的事 |
| 硬编码 `type = "user"` 字符串散落各处 | 用自定义注解 `@SaUserCheckLogin` |
| 硬编码权限码字符串 | 用 PermissionCodes 常量类 |
| 登录密码明文存储 | 使用 `BCryptPasswordEncoder` |
| 运行时修改 `loginType` | 只能在启动时指定，运行时修改会线程不安全 |
