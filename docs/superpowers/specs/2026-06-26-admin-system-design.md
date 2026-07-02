# 后台管理系统 Demo — 设计规格

## 概述

使用 Java + Spring Boot 3 从零构建一个后台管理系统 Demo，纯后端 API。包含用户注册登录、JWT 认证、RBAC 权限控制、登录/操作日志、字典管理五大模块。

## 技术栈

| 维度 | 选择 |
|------|------|
| 框架 | Spring Boot 3 |
| 认证 | Sa-Token + JWT 风格 Token |
| 密码加密 | BCrypt（Spring Security Crypto） |
| ORM | MyBatis-Plus（LambdaQueryWrapper + XML 联表） |
| 数据库 | MySQL |
| API 文档 | Knife4j（Swagger 增强） |
| AOP | Spring AOP（操作日志采集） |
| 校验 | JSR 303 Bean Validation |
| 测试 | JUnit 5 + Mockito + H2 内存数据库 |

## 功能范围

### 包含

1. **用户注册与登录**
   - 注册：用户名 + 密码 + 确认密码，BCrypt 加密存储，注册成功自动登录返回 Token
   - 登录：校验用户名密码，成功后 Sa-Token 签发 JWT 风格 Token
   - 登出、获取当前用户信息（含角色和权限列表）

2. **登录日志**
   - 记录每次登录的用户名、IP、时间、状态（成功/失败）、User-Agent
   - 分页查询接口，支持按用户名、状态、时间范围筛选

3. **操作日志**
   - AOP 注解 `@Log` 驱动，环绕通知采集：操作用户、模块、操作类型、方法名、参数 JSON、返回结果、耗时（ms）、IP、时间
   - 分页查询接口，支持按用户名、操作类型、时间范围筛选

4. **RBAC 权限**
   - 5 张表：用户、角色、权限、用户-角色关联、角色-权限关联
   - 权限控制到接口 URL + 请求方法（如 `POST /api/users`）
   - 用户管理 CRUD + 分配角色
   - 角色管理 CRUD + 分配权限
   - 权限管理 CRUD
   - Sa-Token `@SaCheckPermission` 注解鉴权

5. **字典表**
   - 字典类型表 + 字典项表，支持动态键值对
   - 字典类型 CRUD
   - 字典项 CRUD
   - 按类型编码查询字典项列表

### 不做

- 不做前端页面
- 不做部门管理
- 不做数据权限（部门数据隔离）
- 不做多租户
- 不做 SSO/OAuth2
- 不做多端隔离
- 不做邮件/手机验证

## 表设计

统一前缀 `sys_`，通用字段：`create_time`（datetime）、`update_time`（datetime），状态字段 `status`（tinyint，1 启用 0 禁用）。

### RBAC 核心（5 张）

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `sys_user` | 用户表 | id (bigint PK), username (varchar 唯一), password (varchar), status (tinyint), create_time, update_time |
| `sys_role` | 角色表 | id (bigint PK), role_name (varchar), role_code (varchar 唯一), description (varchar), status (tinyint), create_time, update_time |
| `sys_permission` | 权限表 | id (bigint PK), perm_name (varchar), perm_code (varchar 唯一), url (varchar), method (varchar GET/POST/PUT/DELETE), description (varchar), create_time, update_time |
| `sys_user_role` | 用户-角色关联 | id (bigint PK), user_id (bigint FK), role_id (bigint FK) |
| `sys_role_permission` | 角色-权限关联 | id (bigint PK), role_id (bigint FK), permission_id (bigint FK) |

### 日志（2 张）

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `sys_login_log` | 登录日志 | id (bigint PK), username (varchar), ip (varchar), login_time (datetime), status (tinyint: 1 成功 0 失败), user_agent (varchar), create_time |
| `sys_operation_log` | 操作日志 | id (bigint PK), username (varchar), module (varchar), action (varchar), method (varchar), params (text), result (text), duration (bigint, 毫秒), ip (varchar), create_time |

### 字典（2 张）

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `sys_dict_type` | 字典类型 | id (bigint PK), dict_name (varchar), dict_type (varchar 唯一), status (tinyint), create_time, update_time |
| `sys_dict_item` | 字典项 | id (bigint PK), dict_type_id (bigint FK), label (varchar), value (varchar), sort (int), create_time, update_time |

## API 接口

### 认证 `/api/auth`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/api/auth/register` | 注册（username, password, confirmPassword），成功后返回 Token | 无 |
| POST | `/api/auth/login` | 登录（username, password），返回 Token + 用户信息 | 无 |
| POST | `/api/auth/logout` | 登出 | 登录 |
| GET | `/api/auth/info` | 当前用户信息（角色、权限列表） | 登录 |

### 用户管理 `/api/users`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/users` | 分页列表（支持 username/status 搜索） | system:user:list |
| POST | `/api/users` | 新增用户 | system:user:add |
| GET | `/api/users/{id}` | 用户详情 | system:user:query |
| PUT | `/api/users/{id}` | 编辑用户 | system:user:edit |
| DELETE | `/api/users/{id}` | 删除用户 | system:user:delete |
| PUT | `/api/users/{id}/roles` | 分配角色 | system:user:assign-role |

### 角色管理 `/api/roles`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/roles` | 角色列表 | system:role:list |
| POST | `/api/roles` | 新增角色 | system:role:add |
| GET | `/api/roles/{id}` | 角色详情 | system:role:query |
| PUT | `/api/roles/{id}` | 编辑角色 | system:role:edit |
| DELETE | `/api/roles/{id}` | 删除角色 | system:role:delete |
| PUT | `/api/roles/{id}/permissions` | 分配权限 | system:role:assign-perm |

### 权限管理 `/api/permissions`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/permissions` | 权限列表（支持 perm_code/perm_name 搜索） | system:perm:list |
| POST | `/api/permissions` | 新增权限 | system:perm:add |
| GET | `/api/permissions/{id}` | 权限详情 | system:perm:query |
| PUT | `/api/permissions/{id}` | 编辑权限 | system:perm:edit |
| DELETE | `/api/permissions/{id}` | 删除权限 | system:perm:delete |

### 日志 `/api/logs`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/logs/login` | 登录日志分页（username/status/时间范围） | log:login:list |
| GET | `/api/logs/operation` | 操作日志分页（username/action/时间范围） | log:operation:list |

### 字典 `/api/dict-types` `/api/dict-items`

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | `/api/dict-types` | 字典类型列表 | dict:type:list |
| POST | `/api/dict-types` | 新增字典类型 | dict:type:add |
| GET | `/api/dict-types/{id}` | 类型详情 | dict:type:query |
| PUT | `/api/dict-types/{id}` | 编辑字典类型 | dict:type:edit |
| DELETE | `/api/dict-types/{id}` | 删除字典类型 | dict:type:delete |
| GET | `/api/dict-types/{type}/items` | 按类型编码获取字典项 | 登录 |
| POST | `/api/dict-items` | 新增字典项 | dict:item:add |
| PUT | `/api/dict-items/{id}` | 编辑字典项 | dict:item:edit |
| DELETE | `/api/dict-items/{id}` | 删除字典项 | dict:item:delete |

**统计：29 个接口，7 组 Controller。**

## 项目结构

```
admin-test-04/
├── pom.xml
├── README.md                              # 启动说明
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
    │   │   │   └── BusinessException.java
    │   │   ├── result/
    │   │   │   └── Result.java
    │   │   └── base/
    │   │       └── BaseEntity.java
    │   ├── auth/
    │   │   ├── controller/AuthController.java
    │   │   ├── service/AuthService.java
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
    │   │   ├── mapper/
    │   │   │   ├── LoginLogMapper.java
    │   │   │   └── OperationLogMapper.java
    │   │   ├── entity/
    │   │   │   ├── LoginLog.java
    │   │   │   └── OperationLog.java
    │   │   ├── aspect/
    │   │   │   ├── Log.java               # @Log 注解
    │   │   │   └── LogAspect.java          # AOP 切面
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
            └── init.sql                    # 建表 + 初始数据
```

**预计约 55 个 Java 文件。**

## 架构约束

以下规则来自 `agents/coder/` 规范，coder 必须遵守：

- 包结构：`controller → service/impl → mapper → entity/dto/vo`，每个领域内严格分层
- 返回值：统一 `Result<T>`
- 注入：构造注入 `@RequiredArgsConstructor`，禁用 `@Autowired` 字段注入
- 日志：`@Slf4j`，不打敏感信息
- 异常：抛 `BusinessException`，不写自由文本。错误码使用 `BusinessErrorEnum`
- SQL：简单查用 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 `@Select` 注解
- 参数：>3 个收敛到 DTO
- URL：RESTful 复数名词，CRUD 不用动词。非 CRUD 业务动作（login、logout、register、assign-role、assign-perm）允许动词
- 配置：`application.yml` + `logback-spring.xml`

## 关键数据流

### 1. 注册 → 自动登录流程

```
用户 POST /api/auth/register {username, password, confirmPassword}
  → AuthService.register()
    1. 校验 password.equals(confirmPassword)，不一致抛 BusinessException(1004, "两次密码不一致")
    2. 校验 username 唯一性，已存在抛 BusinessException(1001, "用户名已存在")
    3. BCrypt 加密密码 → 写入 sys_user（status=1 启用）
    4. 调用 login() → Sa-Token 签发 JWT 风格 Token
    5. 记录登录日志（status=成功, IP, User-Agent）
    6. 返回 {token, userInfo}
```

### 2. 登录流程

```
用户 POST /api/auth/login {username, password}
  → AuthService.login()
    1. 根据 username 查询 sys_user
    2. 不存在 → 记录登录日志（status=失败），抛 BusinessException(1002, "用户名或密码错误")
    3. BCrypt 校验密码，不匹配 → 同上
    4. Sa-Token 签发 JWT 风格 Token
    5. 记录登录日志（status=成功, IP, User-Agent）
    6. 返回 {token, userInfo}
```

### 3. RBAC 鉴权流程

```
请求携带 Token → Sa-Token 拦截器校验 Token 有效性
  → 从 sys_user_role + sys_role_permission 查出用户所有权限标识
  → Controller 方法上的 @SaCheckPermission("system:user:add") 校验
  → 通过则放行，失败则返回 403（无权限）
```

### 4. 操作日志 AOP 采集

```
业务方法上有 @Log(module="用户管理", action="新增")
  → LogAspect 环绕通知：
    1. 从 Sa-Token 上下文获取当前登录用户名
    2. 记录方法全名、参数序列化为 JSON、请求 IP
    3. 执行原方法，记录耗时 ms
    4. 采集返回结果摘要
    5. 异步写入 sys_operation_log
```

## 错误码规划

| 号段 | 范围 | 示例 |
|------|------|------|
| 1000-1999 | 用户/认证 | 1001 用户名已存在，1002 用户名或密码错误，1003 未登录，1004 两次密码不一致，1005 用户不存在 |
| 2000-2999 | RBAC | 2001 角色不存在，2002 权限标识已存在，2003 无权限 |
| 4000-4999 | 字典 | 4001 字典类型已存在，4002 字典项值重复 |
| 9000-9999 | 通用 | 9001 参数校验失败，9999 系统未知错误 |

## 测试策略

| 层级 | 类型 | 覆盖内容 |
|------|------|---------|
| Service | 单元测试 | AuthService（注册/登录/登出）、UserService CRUD、RoleService CRUD、DictService CRUD |
| Mapper | 单元测试 | 联表 XML（用户-角色、角色-权限）、分页查询 |
| Controller | 集成测试 | 登录/注册接口、核心 CRUD 接口、权限拦截验证 |

- 工具：JUnit 5 + Mockito（单元测试）、Spring Boot Test + MockMvc（集成测试）、H2 内存数据库
- 不对字典项 CRUD 做全覆盖（重复模式，抽查即可）
- 不对 AOP 切面做独立单元测试（集成测试间接覆盖）
