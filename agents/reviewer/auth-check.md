# 认证审查

> 审查认证授权代码是否安全：StpKit 门面、登录接口、拦截器、权限注解、SSO/OAuth2

---

## 一、前置确认

审查认证代码前，**必须先确认项目有几套账号体系**。纯后台管理项目直接用 `StpUtil` 是合理的，不视为违规。

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 0.1 | 审查前确认项目账号体系数量（纯后台管理？用户端+管理端？多系统？） | — | `../coder/auth/auth-overview.md` |

> **如果只有一套账号体系（纯后台管理）：** 使用 `StpUtil` 合理，跳过下方第二节的全部检查项和第五节中涉及 LoginContextHolder 的检查项。

---

## 二、StpKit 门面使用（仅多端/多系统场景）

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 1.1 | 多端/多系统场景下，是否直接使用 `StpUtil` 而**未**通过 `StpKit` 门面（禁止） | P1 | `../coder/auth/auth-basic.md #分岔路口` |
| 1.2 | 是否定义了 `StpKit` 门面类，为各账号体系创建独立的 `StpLogic` 实例 | P1 | `../coder/auth/auth-basic.md #二` |
| 1.3 | `StpKit` 是否包含与场景匹配的 StpLogic（如 USER + ADMIN） | P1 | 对应 auth 多端/多系统文件 |
| 1.4 | 配置类是否命名为 `SaTokenCustomConfig`（避免与库类 `SaTokenConfig` 冲突） | P0 | `../coder/auth/auth-basic.md #四` |

---

## 三、登录接口

> 纯后台管理项目：2.2 适用，其余 2.1/2.3/2.4/2.5 仅多端场景需要。

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 2.1 | 多端场景下，用户端和管理端登录是否分为两个独立 Controller（URL 前缀不同） | P1 | `../coder/auth/auth-basic.md #五` |
| 2.2 | 登录密码是否使用 `BCryptPasswordEncoder` 加密（禁止明文存储） | P0 | `../coder/auth/auth-basic.md #十一` |
| 2.3 | 多端场景下，登录后是否调用 `StpKit.USER.login(userId)` 而非 `StpUtil.login()` | P1 | `../coder/auth/auth-basic.md #五` |
| 2.4 | 多端场景下，登出是否通过 `LoginContextHolder.get()` 而非硬编码 `StpKit.USER` | P1 | `../coder/auth/auth-basic.md #五` |
| 2.5 | 多端场景下，是否在登录时将用户名存入 Session（供 MetaObjectHandler 获取） | P1 | `../coder/auth/auth-sso.md #四` |

---

## 四、拦截器配置

> 纯后台管理项目：3.4 适用（白名单是否正确排除），3.1/3.2/3.3 仅多端场景需要。

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 3.1 | 多端场景下，管理端和用户端是否分别配置了独立拦截器 | P1 | `../coder/auth/auth-basic.md #九` |
| 3.2 | 多端场景下，用户端拦截器是否排除了 `/api/admin/**` | P0 | `../coder/auth/auth-basic.md #九` |
| 3.3 | 多端场景下，拦截器中是否在 `checkLogin()` 后立即调用 `LoginContextHolder.set(stp)` | P1 | `../coder/auth/auth-basic.md #九` |
| 3.4 | 登录接口和白名单路径是否在拦截器中正确排除 | P1 | `../coder/auth/auth-basic.md #九` |

---

## 五、权限注解

> 纯后台管理项目：4.1/4.4 适用（权限注解位置 + 权限码常量），4.2/4.3/4.5 仅多端场景需要（自定义注解合并）。

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 4.1 | 权限注解是否**只放在 Controller 方法上**，未放在 Service 层 | P1 | `../coder/auth/auth-basic.md #七` |
| 4.2 | 多端场景下，是否使用自定义注解替代散落的 `type = "user"` 字符串 | P1 | `../coder/auth/auth-basic.md #八` |
| 4.3 | 多端场景下，`@SaUserCheckPermission` 是否包含 `@AliasFor` 确保值透传 | P0 | `../coder/auth/auth-basic.md #八` |
| 4.4 | 权限码是否定义在 `PermissionCodes` 常量类中，未硬编码字符串 | P1 | `../coder/auth/auth-basic.md #六` |
| 4.5 | 多端场景下，是否启用了 `SaAnnotationStrategy` 注解合并 | P2 | `../coder/auth/auth-basic.md #八` |

---

## 六、Service 层获取用户（仅多端）

> 纯后台管理项目：5.2 适用（禁止注入 HttpServletRequest），5.1/5.3 不适用（无需 LoginContextHolder），改为直接 `StpUtil.getLoginIdAsLong()`。

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 5.1 | 多端场景下，Service 是否通过 `LoginContextHolder.getUserId()` 获取当前用户 | P1 | `../coder/auth/auth-basic.md #十` |
| 5.2 | Service 是否**直接注入了 `HttpServletRequest`**（禁止） | P0 | `../coder/layered/service-guide.md #四.1` |
| 5.3 | 多端场景下，Service 中是否硬编码了 `StpKit.USER`（应用 LoginContextHolder） | P1 | `../coder/auth/auth-basic.md #十` |
| 5.4 | 定时任务/消息队列等非 HTTP 场景是否通过业务参数传入操作用户 | P2 | `../coder/layered/service-guide.md #四.2` |

---

## 七、SSO / OAuth2 专项

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 6.1 | Gateway 全局过滤器中是否遍历 `StpKit` 匹配 Token 而非硬编码 | P1 | `../coder/auth/auth-sso.md #三` |
| 6.2 | Gateway 过滤器是否将 `X-User-Id` / `X-User-Name` 透传到下游 Header | P1 | `../coder/auth/auth-sso.md #三` |
| 6.3 | 下游服务是否从 Header 获取用户信息，不重复校验 Token | P1 | `../coder/auth/auth-sso.md #五` |
| 6.4 | SSO 核心用户表是否包含 `locale` 字段（国际化需要） | P2 | `../coder/auth/auth-sso.md #七.2` |
| 6.5 | OAuth 回调日志是否记录了 provider/openId/userId（不打印 accessToken） | P2 | `../coder/auth/auth-oauth2.md #六` |
| 6.6 | `sys_user_oauth` 表是否有 `uk_provider_openid` 唯一索引 | P2 | `../coder/auth/auth-oauth2.md #四` |
| 6.7 | 敏感配置（app-id、app-secret）是否通过环境变量注入，不写死在配置文件中 | P0 | `../coder/auth/auth-oauth2.md #三` |

---

## 八、安全红线（P0 必查）

| # | 检查项 | 级别 |
|---|--------|------|
| 7.1 | 密码是否明文存储 | P0 |
| 7.2 | Token/密钥是否硬编码在代码中 | P0 |
| 7.3 | 敏感信息（密码、Token）是否出现在日志中 | P0 |
| 7.4 | 是否存在绕过认证的接口（白名单外未加 `@SaCheckLogin`） | P0 |
| 7.5 | OAuth2 的 `app-secret` 是否通过环境变量 `${VAR:}` 注入 | P0 |

---

## 九、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/auth/auth-basic.md` | StpKit、登录、权限注解、拦截器 |
| `../coder/auth/auth-multi-end.md` | 多端隔离 |
| `../coder/auth/auth-multi-system.md` | 多系统隔离 |
| `../coder/auth/auth-sso.md` | SSO、Gateway 鉴权 |
| `../coder/auth/auth-oauth2.md` | OAuth2 第三方登录 |
| `../coder/layered/service-guide.md` | Service 层获取用户、禁止注入 HttpServletRequest |
