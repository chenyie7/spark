# 多端隔离规范

> 适用：同一系统区分用户端和管理端，登录态互不干扰
> 依赖：先读 `auth-basic.md`

---

## 一、核心思路

使用 `StpKit` 门面模式为不同端创建独立的 `StpLogic` 实例，每个端的 Token 名称、过期时间独立配置。

---

## 二、StpKit 定义

```java
public final class StpKit {
    private StpKit() {}

    public static final StpLogic DEFAULT = StpUtil.stpLogic;
    public static final StpLogic USER = new StpLogic("user");    // 用户端
    public static final StpLogic ADMIN = new StpLogic("admin");  // 管理端
}
```

---

## 三、独立配置

用户端和管理端使用不同的 Token 名称和超时时间：

```java
@Configuration
public class SaTokenCustomConfig {

    static {
        // 用户端：30天，不限无操作时间
        SaTokenConfig userConfig = new SaTokenConfig();
        userConfig.setTokenName("satoken-user");
        userConfig.setTimeout(2592000);
        userConfig.setActiveTimeout(-1);
        StpKit.USER.setConfig(userConfig);

        // 管理端：2小时，30分钟无操作
        SaTokenConfig adminConfig = new SaTokenConfig();
        adminConfig.setTokenName("satoken-admin");
        adminConfig.setTimeout(7200);
        adminConfig.setActiveTimeout(1800);
        StpKit.ADMIN.setConfig(adminConfig);
    }
}
```

| 配置项 | 用户端 | 管理端 |
|--------|--------|--------|
| `tokenName` | `satoken-user` | `satoken-admin` |
| `timeout` | 30 天 | 2 小时 |
| `activeTimeout` | -1（不限） | 1800（30分钟） |

---

## 四、登录接口分离

```java
// 用户端登录
@PostMapping("/api/auth/login")
public Result<LoginVO> userLogin(@RequestBody @Validated AuthLoginDTO dto) {
    UserEntity user = userService.auth(dto.getUsername(), dto.getPassword());
    StpKit.USER.login(user.getId());
    return Result.success(new LoginVO(user.getId(), StpKit.USER.getTokenValue()));
}

// 管理端登录
@PostMapping("/api/admin/auth/login")
public Result<LoginVO> adminLogin(@RequestBody @Validated AuthLoginDTO dto) {
    UserEntity admin = userService.authAdmin(dto.getUsername(), dto.getPassword());
    StpKit.ADMIN.login(admin.getId());
    return Result.success(new LoginVO(admin.getId(), StpKit.ADMIN.getTokenValue()));
}
```

---

## 五、自定义注解按端区分

```java
// 用户端注解
@SaCheckLogin(type = "user")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaUserCheckLogin {}

// 管理端注解
@SaCheckLogin(type = "admin")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaAdminCheckLogin {}
```

```java
// 用户端接口
@SaUserCheckLogin
@GetMapping("/api/user/info")
public Result<UserVO> info() { ... }

// 管理端接口
@SaAdminCheckLogin
@GetMapping("/api/admin/user/list")
public Result<List<UserVO>> list() { ... }
```

---

## 六、拦截器按端隔离

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    // 管理端路由
    registry.addInterceptor(new SaInterceptor(handle -> {
                StpKit.ADMIN.checkLogin();
                LoginContextHolder.set(StpKit.ADMIN);
            }))
            .addPathPatterns("/api/admin/**")
            .excludePathPatterns("/api/admin/auth/login");

    // 用户端路由
    registry.addInterceptor(new SaInterceptor(handle -> {
                StpKit.USER.checkLogin();
                LoginContextHolder.set(StpKit.USER);
            }))
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/auth/login", "/api/auth/register",
                    "/api/public/**", "/api/admin/**");
}
```

---

## 七、防止同端 Token 覆盖（可选优化）

如果同一客户端下多个账号体系同时登录，需要避免 Cookie 中的 Token 互相覆盖。以下是对第二节 `StpKit` 定义的**替换方案**，通过 `splicingKeyTokenName` 重写让各体系的 Token 名称不同。**注意：此方案与第二节互斥，选择其一即可。**

```java
public static final StpLogic USER = new StpLogic("user") {
    @Override
    public String splicingKeyTokenName() {
        return super.splicingKeyTokenName() + "-user";
    }
};

public static final StpLogic ADMIN = new StpLogic("admin") {
    @Override
    public String splicingKeyTokenName() {
        return super.splicingKeyTokenName() + "-admin";
    }
};
```
