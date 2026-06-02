# 多系统隔离规范

> 适用：多个独立业务系统，接入同一认证但登录态互不干扰
> 依赖：先读 `auth-basic.md`

---

## 一、核心思路

每个系统创建独立的 `StpLogic` 实例，通过不同的 `loginType` 实现 Token 隔离。

---

## 二、StpKit 按系统划分

```java
public final class StpKit {
    private StpKit() {}

    /** A系统 */
    public static final StpLogic APP_USER = new StpLogic("app-user");
    public static final StpLogic APP_ADMIN = new StpLogic("app-admin");

    /** B系统 */
    public static final StpLogic BIZ_USER = new StpLogic("biz-user");
    public static final StpLogic BIZ_ADMIN = new StpLogic("biz-admin");
}
```

---

## 三、各系统独立配置

```java
@Configuration
public class SaTokenCustomConfig {

    static {
        // A系统用户端
        SaTokenConfig appUserConfig = new SaTokenConfig();
        appUserConfig.setTokenName("satoken-app-user");
        appUserConfig.setTimeout(2592000);
        StpKit.APP_USER.setConfig(appUserConfig);

        // A系统管理端
        SaTokenConfig appAdminConfig = new SaTokenConfig();
        appAdminConfig.setTokenName("satoken-app-admin");
        appAdminConfig.setTimeout(7200);
        StpKit.APP_ADMIN.setConfig(appAdminConfig);

        // B系统用户端
        SaTokenConfig bizUserConfig = new SaTokenConfig();
        bizUserConfig.setTokenName("satoken-biz-user");
        bizUserConfig.setTimeout(86400);
        StpKit.BIZ_USER.setConfig(bizUserConfig);
    }
}
```

每个系统的 Token 独立管理，A 系统的 Token 不能访问 B 系统的接口。

---

## 四、权限码按系统划分

```java
// A系统权限码
public final class AppPermissionCodes {
    private AppPermissionCodes() {}
    public static final String ORDER_VIEW = "app:order:view";
    public static final String ORDER_CANCEL = "app:order:cancel";
}

// B系统权限码
public final class BizPermissionCodes {
    private BizPermissionCodes() {}
    public static final String PRODUCT_VIEW = "biz:product:view";
    public static final String PRODUCT_EDIT = "biz:product:edit";
}
```

权限码前缀等于系统名，不同系统权限互不通用。

---

## 五、自定义注解按系统

```java
// A系统
@SaCheckLogin(type = "app-user")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaAppUserCheckLogin {}

// B系统
@SaCheckLogin(type = "biz-user")
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface SaBizUserCheckLogin {}
```

---

## 六、对接 SSO 时

多个系统存在时，通常引入 SSO 统一认证（见 `auth-sso.md`）。多系统隔离 + SSO 组合时：

```
SSO 认证中心 签发 Ticket  →  各系统凭 Ticket 换本系统的 StpLogic Token
```

同一个用户在 A 系统和 B 系统的登录是独立的：SSO 识别用户身份，但各系统用自己的 `StpLogic` 签发本地 Token。
