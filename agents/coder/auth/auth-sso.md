# SSO 统一认证规范

> 适用：多个业务系统 + 统一认证中心 + 网关鉴权
> 依赖：先读 `auth-multi-system.md`

---

## 一、架构：网关统一鉴权

微服务模式下，网关统一校验 Token，下游服务不重复校验：

```
用户请求 → Gateway（统一鉴权）
              │ Token 校验通过
              │ 透传 userId 到 Header
              ├──→ business-user（信任网关，不重复鉴权）
              ├──→ business-order
              └──→ business-payment
```

- 网关负责 Token 合法性校验、路由转发
- 下游服务从 Header 获取 `X-User-Id`，不需要再用 SaToken 校验
- 下游服务**仍保留 SaToken 依赖**，用于获取会话信息和权限判断

---

## 二、网关依赖

```xml
<!-- Gateway 集成 SaToken -->
<dependency>
    <groupId>cn.dev33</groupId>
    <artifactId>sa-token-reactor-spring-boot3-starter</artifactId>
    <version>1.39.0</version>
</dependency>
```

---

## 三、网关全局过滤器

```java
@Component
public class GatewayAuthFilter implements GlobalFilter, Ordered {

    private static final Set<String> WHITE_LIST = Set.of(
        "/api/auth/login", "/api/auth/register",
        "/doc.html", "/v3/api-docs"
    );

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();

        // 白名单放行
        if (isWhiteListed(path)) {
            return chain.filter(exchange);
        }

        // 校验 Token
        // 注意：网关层遍历 StpKit 尝试匹配 Token，这是唯一可以直接使用 StpLogic 的场景，
        //       因为请求尚未路由到具体服务，无法通过 URL 预判登录体系。
        String token = exchange.getRequest().getHeaders().getFirst("Authorization");
        if (token == null) {
            return unauthorized(exchange, "未登录");
        }

        try {
            // 遍历所有 StpLogic 找到匹配的 Token
            StpLogic matchedStp = findMatchedStp(token);
            if (matchedStp == null) {
                return unauthorized(exchange, "Token无效");
            }
            Object loginId = matchedStp.getLoginIdByToken(token);
            // 注意：Gateway 是响应式（WebFlux）线程模型，LoginContextHolder 基于 ThreadLocal，
            // 在此设置不可靠（线程切换会丢失）。下游服务会在自己的拦截器中重新设置。

            ServerHttpRequest request = exchange.getRequest().mutate()
                .header("X-User-Id", String.valueOf(loginId))
                .header("X-User-Name", URLEncoder.encode(
                    matchedStp.getSessionByLoginId(loginId).getString("userName"), StandardCharsets.UTF_8))
                .build();
            return chain.filter(exchange.mutate().request(request).build());
        } catch (Exception e) {
            return unauthorized(exchange, "Token无效");
        }
    }

    @Override
    public int getOrder() { return -100; }

    /** 遍历所有 StpLogic 找到匹配当前 Token 的体系 */
    private StpLogic findMatchedStp(String token) {
        for (StpLogic stp : List.of(StpKit.APP_USER, StpKit.APP_ADMIN, StpKit.BIZ_USER)) {
            if (stp.isLogin(token)) {
                return stp;
            }
        }
        return null;
    }
}
```

---

## 四、认证中心（SSO）

认证中心独立部署，负责登录和 Token 签发：

```
Gateway 路由：
  /api/auth/**           → project-auth（认证中心）
  /api/user/**           → business-user
  /api/order/**          → business-order
```

```java
// project-auth 中的登录接口
@PostMapping("/api/auth/login")
public Result<LoginVO> login(@RequestBody @Validated AuthLoginDTO dto) {
    UserEntity user = userService.auth(dto.getUsername(), dto.getPassword());
    StpKit.USER.login(user.getId());
    // 将用户名存入 Session，网关鉴权时透传
    StpKit.USER.getSession().set("userName", user.getUsername());
    return Result.success(new LoginVO(user.getId(), StpKit.USER.getTokenValue()));
}
```

---

## 五、下游服务如何获取用户

下游服务不重复校验 Token，从 Header 获取网关透传的用户信息：

```java
// 下游服务的业务 Controller
@GetMapping("/api/user/info")
public Result<UserVO> info(@RequestHeader("X-User-Id") Long userId) {
    return Result.success(userService.getById(userId));
}
```

如果需要权限校验，下游仍可调用 `StpKit.USER.checkPermission("user:view")` —— SaToken 的 Session 和权限存储默认在 Redis 中，网关和下游共享同一 Redis。

---

## 六、完整登录流程

```
1. 用户 POST /api/auth/login → Gateway → project-auth
2. project-auth 校验用户密码，签发 Token
3. 返回 Token 给用户
4. 后续请求带 Authorization: {token}
5. Gateway 校验 Token，透传 X-User-Id / X-User-Name
6. 下游服务从 Header 获取用户信息
```

---

## 七、用户数据模型：认证统一 + 业务分治

### 7.1 核心原则

**SSO 只负责认证（你是谁），用户画像（你有哪些偏好）由各系统自己管理。**

### 7.2 数据分布

```
project-auth/
└── sys_user                    ← 认证核心信息
    ├── user_id                 # 全局唯一，跨系统统一
    ├── username                # 登录名
    ├── password                # 加密密码
    ├── phone                   # 手机号
    ├── email                   # 邮箱
    ├── status                  # 账号状态（启用/禁用）
    └── locale                  # 语言偏好

A系统（电商）
└── sys_user_profile            ← A系统业务扩展
    ├── user_id                 # 关联 sys_user.user_id
    ├── default_address         # 收货地址
    ├── member_level            # 会员等级
    └── points                  # 积分

B系统（内容）
└── sys_user_profile            ← B系统业务扩展
    ├── user_id                 # 关联 sys_user.user_id
    ├── specialty               # 擅长领域
    ├── article_count           # 文章数
    └── follower_count          # 粉丝数
```

### 7.3 关键约束

- 用户**只需注册一次**（在 SSO 认证中心），不接受各系统分别注册
- `user_id` 是全局统一的跨系统标识符，由 SSO 认证中心统一分配
- 各系统用 `user_id` 关联自己的扩展数据
- 扩展数据表不参与登录校验，纯业务数据

### 7.4 首次登录流程

```
1. 用户首次访问 A系统
2. A系统检测未登录 → 重定向到 SSO 登录页
3. 用户登录（或注册）成功 → SSO 签发 Token
4. 用户回到 A系统，A系统检测到 user_id 没有扩展数据
5. A系统自动创建 sys_user_profile（默认值），关联 user_id
6. 用户后续访问 B系统 → 已登录 → B系统自动创建自己的 profile
```

### 7.5 建表规范

SSO 核心用户表：

```sql
CREATE TABLE sys_user (
    id          BIGINT       NOT NULL COMMENT '用户ID（全局唯一）',
    username    VARCHAR(64)  NOT NULL COMMENT '登录名',
    password    VARCHAR(256) NOT NULL COMMENT '密码（BCrypt加密）',
    phone       VARCHAR(20)  DEFAULT NULL COMMENT '手机号',
    email       VARCHAR(128) DEFAULT NULL COMMENT '邮箱',
    status      TINYINT      NOT NULL DEFAULT 1 COMMENT '状态：0禁用 1启用',
    locale      VARCHAR(10)  DEFAULT 'zh_CN' COMMENT '语言偏好',
    -- 审计字段（参见 database-guide.md）
    create_id   BIGINT       NOT NULL COMMENT '创建人ID',
    create_name VARCHAR(64)  NOT NULL COMMENT '创建人姓名',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_id   BIGINT       NOT NULL COMMENT '最后更新人ID',
    update_name VARCHAR(64)  NOT NULL COMMENT '最后更新人姓名',
    update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    deleted     TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除 1已删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_phone (phone),
    UNIQUE KEY uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='SSO用户表';
```

---

## 八、SSO 认证中心模式（跨系统）

```
                    ┌─────────────────┐
                    │  project-auth    │  SSO 认证中心
                    │ /api/auth/**     │  登录/登出/Token签发
                    └────────┬────────┘
                             │ 登录成功，返回 Token
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  A系统     │  │ A系统管理端 │  │  B系统     │
        │ app-user  │  │app-admin  │  │ biz-user  │
        └──────────┘  └──────────┘  └──────────┘

Gateway 鉴权：校验 Token → 透传用户信息
```

- 认证中心：登录、签发各体系 `StpLogic` Token
- Gateway：统一校验 Token，透传用户信息
- 业务系统：从 Header 取用户信息，权限校验用 Redis 共享 Session
