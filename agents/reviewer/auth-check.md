# 认证审查

> 审查认证授权代码是否安全：StpKit 门面、登录接口、拦截器、权限注解、SSO/OAuth2

---

## 一、前置确认

审查认证代码前，**必须先确认项目有几套账号体系**。纯后台管理项目直接用 `StpUtil` 是合理的，不视为违规。

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-01 | 前置确认 | 审查前确认项目账号体系数量（纯后台管理？用户端+管理端？多系统？） | — | — | `../coder/auth/auth-overview.md` |

> **如果只有一套账号体系（纯后台管理）：** 使用 `StpUtil` 合理，跳过下方第二节和第六节中涉及 LoginContextHolder 的检查项。

---

## 二、StpKit 门面使用（仅多端/多系统场景）

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-02 | StpKit | 多端/多系统场景下，是否直接使用 `StpUtil` 而未通过 `StpKit` 门面 | P1 | "{class} 直接使用了 StpUtil，多端场景应使用 StpKit 门面" | `../coder/auth/auth-basic.md #分岔路口` |
| BE-AU-03 | StpKit | 是否定义了 `StpKit` 门面类，为各账号体系创建独立的 `StpLogic` 实例 | P1 | "缺少 StpKit 门面类" | `../coder/auth/auth-basic.md #二` |
| BE-AU-04 | StpKit | `StpKit` 是否包含与场景匹配的 StpLogic（如 USER + ADMIN） | P1 | "StpKit 缺少与业务场景匹配的 StpLogic" | 对应 auth 多端/多系统文件 |
| BE-AU-05 | StpKit | 配置类是否命名为 `SaTokenCustomConfig`（避免与库类 `SaTokenConfig` 冲突） | P0 | "{class} 配置类应命名为 SaTokenCustomConfig" | `../coder/auth/auth-basic.md #四` |

---

## 三、登录接口

> 纯后台管理项目：BE-AU-07 适用，其余仅多端场景需要。

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-06 | 登录接口 | 多端场景下，用户端和管理端登录是否分为两个独立 Controller（URL 前缀不同） | P1 | "用户端和管理端登录应分为独立 Controller" | `../coder/auth/auth-basic.md #五` |
| BE-AU-07 | 登录接口 | 登录密码是否使用 `BCryptPasswordEncoder` 加密 | P0 | "{method} 密码未使用 BCryptPasswordEncoder 加密" | `../coder/auth/auth-basic.md #十一` |
| BE-AU-08 | 登录接口 | 多端场景下，登录后是否调用 `StpKit.USER.login(userId)` 而非 `StpUtil.login()` | P1 | "{method} 应使用 StpKit.USER.login() 而非 StpUtil.login()" | `../coder/auth/auth-basic.md #五` |
| BE-AU-09 | 登录接口 | 多端场景下，登出是否通过 `LoginContextHolder.get()` 而非硬编码 `StpKit.USER` | P1 | "{method} 应使用 LoginContextHolder.get() 获取当前 StpLogic" | `../coder/auth/auth-basic.md #五` |
| BE-AU-10 | 登录接口 | 多端场景下，是否在登录时将用户名存入 Session（供 MetaObjectHandler 获取） | P1 | "{method} 登录后未将用户名存入 Session" | `../coder/auth/auth-sso.md #四` |

---

## 四、拦截器配置

> 纯后台管理项目：BE-AU-14 适用（白名单是否正确排除），BE-AU-11/12/13 仅多端场景需要。

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-11 | 拦截器 | 多端场景下，管理端和用户端是否分别配置了独立拦截器 | P1 | "多端场景应分别为用户端和管理端配置独立拦截器" | `../coder/auth/auth-basic.md #九` |
| BE-AU-12 | 拦截器 | 多端场景下，用户端拦截器是否排除了 `/api/admin/**` | P0 | "用户端拦截器未排除 /api/admin/**" | `../coder/auth/auth-basic.md #九` |
| BE-AU-13 | 拦截器 | 多端场景下，拦截器中是否在 `checkLogin()` 后立即调用 `LoginContextHolder.set(stp)` | P1 | "拦截器 checkLogin 后未调用 LoginContextHolder.set()" | `../coder/auth/auth-basic.md #九` |
| BE-AU-14 | 拦截器 | 登录接口和白名单路径是否在拦截器中正确排除 | P1 | "拦截器未正确排除登录接口和白名单路径" | `../coder/auth/auth-basic.md #九` |

---

## 五、权限注解

> 纯后台管理项目：BE-AU-15/19 适用（权限注解位置 + 权限码常量），BE-AU-16/17/18 仅多端场景需要。

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-15 | 权限注解 | 权限注解是否只放在 Controller 方法上，未放在 Service 层 | P1 | "{method} 权限注解应放在 Controller 层" | `../coder/auth/auth-basic.md #七` |
| BE-AU-16 | 权限注解 | 多端场景下，是否使用自定义注解替代散落的 `type = "user"` 字符串 | P1 | "{method} 应使用自定义注解 @SaUserCheckXxx 替代 type 字符串" | `../coder/auth/auth-basic.md #八` |
| BE-AU-17 | 权限注解 | 多端场景下，`@SaUserCheckPermission` 是否包含 `@AliasFor` 确保值透传 | P0 | "{annotation} 缺少 @AliasFor 注解" | `../coder/auth/auth-basic.md #八` |
| BE-AU-18 | 权限注解 | 权限码是否定义在 `PermissionCodes` 常量类中，未硬编码字符串 | P1 | "{method} 硬编码权限码字符串，应使用 PermissionCodes 常量" | `../coder/auth/auth-basic.md #六` |
| BE-AU-19 | 权限注解 | 多端场景下，是否启用了 `SaAnnotationStrategy` 注解合并 | P2 | "未启用 SaAnnotationStrategy 注解合并" | `../coder/auth/auth-basic.md #八` |

---

## 六、Service 层获取用户（仅多端）

> 纯后台管理项目：BE-AU-21 适用（禁止注入 HttpServletRequest），BE-AU-20/22 不适用，改为直接 `StpUtil.getLoginIdAsLong()`。

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-20 | 获取用户 | 多端场景下，Service 是否通过 `LoginContextHolder.getUserId()` 获取当前用户 | P1 | "{method} 应使用 LoginContextHolder.getUserId() 获取当前用户" | `../coder/auth/auth-basic.md #十` |
| BE-AU-21 | 获取用户 | Service 是否直接注入了 `HttpServletRequest` | P0 | "{class} 直接注入了 HttpServletRequest" | `../coder/layered/service-guide.md #四.1` |
| BE-AU-22 | 获取用户 | 多端场景下，Service 中是否硬编码了 `StpKit.USER`（应用 LoginContextHolder） | P1 | "{method} 硬编码了 StpKit.USER，应使用 LoginContextHolder" | `../coder/auth/auth-basic.md #十` |
| BE-AU-23 | 获取用户 | 定时任务/消息队列等非 HTTP 场景是否通过业务参数传入操作用户 | P2 | "{method} 非 HTTP 场景应从业务参数获取操作用户" | `../coder/layered/service-guide.md #四.2` |

---

## 七、SSO / OAuth2 专项

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-AU-24 | SSO/OAuth2 | Gateway 全局过滤器中是否遍历 `StpKit` 匹配 Token 而非硬编码 | P1 | "Gateway 过滤器不应硬编码 StpKit 实例" | `../coder/auth/auth-sso.md #三` |
| BE-AU-25 | SSO/OAuth2 | Gateway 过滤器是否将 `X-User-Id` / `X-User-Name` 透传到下游 Header | P1 | "Gateway 过滤器未透传 X-User-Id / X-User-Name" | `../coder/auth/auth-sso.md #三` |
| BE-AU-26 | SSO/OAuth2 | 下游服务是否从 Header 获取用户信息，不重复校验 Token | P1 | "下游服务应直接从 Header 获取用户信息" | `../coder/auth/auth-sso.md #五` |
| BE-AU-27 | SSO/OAuth2 | SSO 核心用户表是否包含 `locale` 字段（国际化需要） | P2 | "{table} 缺少 locale 字段" | `../coder/auth/auth-sso.md #七.2` |
| BE-AU-28 | SSO/OAuth2 | OAuth 回调日志是否记录了 provider/openId/userId（不打印 accessToken） | P2 | "{method} OAuth 回调日志缺少关键字段或打印了敏感 Token" | `../coder/auth/auth-oauth2.md #六` |
| BE-AU-29 | SSO/OAuth2 | `sys_user_oauth` 表是否有 `uk_provider_openid` 唯一索引 | P2 | "sys_user_oauth 缺少 uk_provider_openid 唯一索引" | `../coder/auth/auth-oauth2.md #四` |
| BE-AU-30 | SSO/OAuth2 | 敏感配置（app-id、app-secret）是否通过环境变量注入，不写死在配置文件中 | P0 | "{config} 敏感配置应通过环境变量注入" | `../coder/auth/auth-oauth2.md #三` |

---

## 八、安全红线（P0 必查）

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 |
|------|------|--------|:--:|-------------|
| BE-AU-31 | 安全红线 | 密码是否明文存储 | P0 | "密码明文存储" |
| BE-AU-32 | 安全红线 | Token/密钥是否硬编码在代码中 | P0 | "Token/密钥硬编码在 {class}" |
| BE-AU-33 | 安全红线 | 敏感信息（密码、Token）是否出现在日志中 | P0 | "{method} 日志包含敏感信息" |
| BE-AU-34 | 安全红线 | 是否存在绕过认证的接口（白名单外未加 @SaCheckLogin） | P0 | "{method} 缺少登录校验注解" |
| BE-AU-35 | 安全红线 | OAuth2 的 `app-secret` 是否通过环境变量 `${VAR:}` 注入 | P0 | "app-secret 应通过环境变量注入" |

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
