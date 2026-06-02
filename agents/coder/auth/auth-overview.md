# 认证授权规范总览

> **先读本文件**，按以下流程确认需求后再读取具体规范文件。

---

## 前置确认：你的项目需要多复杂？

在写任何认证代码前，**必须先向用户确认以下问题**：

1. **是否需要区分多端？**（用户端 + 管理端，登录态互不影响）
2. **是否需要多系统隔离？**（A 系统 + B 系统，各自独立）
3. **是否需要 SSO 单点登录？**（统一认证中心，一次登录全系统通用）
4. **是否需要 OAuth2？**（微信 / GitHub / 企业微信等第三方登录）

- 如果上述**全部不需要** → 只读 `auth-basic.md`，不读其他文件
- 如果需要**某些** → 读 `auth-basic.md` + 对应的文件，不要全读

---

## 一、文件清单

```
auth/
├── auth-overview.md          # 本文件，总览索引
├── auth-basic.md             # 基础：单应用 + SaToken JWT + RBAC
├── auth-multi-end.md         # 多端隔离：用户端/管理端
├── auth-multi-system.md      # 多系统隔离：A系统/B系统
├── auth-sso.md               # SSO 统一认证中心
└── auth-oauth2.md            # OAuth2 第三方登录接入
```

---

## 二、按需求叠加

```
auth-basic                         ← 必备，所有场景都要先读
    ├── auth-multi-end             ← 需要时叠加（端隔离）
    ├── auth-multi-system          ← 需要时叠加（系统隔离）
    ├── auth-sso                   ← 需要时叠加（跨系统单点登录）
    └── auth-oauth2                ← 需要时叠加（三方登录，依赖 auth-sso）
```

| 文件 | 适用场景 | 依赖 |
|------|---------|------|
| `auth-basic.md` | 单个 Spring Boot 应用，简单 RBAC 权限控制 | 无 |
| `auth-multi-end.md` | 同一系统区分用户端和管理端 | auth-basic |
| `auth-multi-system.md` | 多个业务系统独立隔离 | auth-basic |
| `auth-sso.md` | 统一认证中心，一次登录全系统通用 | auth-multi-system |
| `auth-oauth2.md` | 微信/GitHub/企业微信等第三方登录 | auth-sso |
