# 后台管理系统 — 设计规格

## 概述

从零构建一个 Spring Boot 3 后台管理系统纯后端 API，作为后续业务开发的基础底座。

## 技术栈

| 维度 | 选择 |
|------|------|
| 框架 | Spring Boot 3 |
| 认证 | Sa-Token（RBAC 权限注解） |
| ORM | MyBatis-Plus（LambdaQueryWrapper + XML） |
| 数据库 | MySQL |
| API 文档 | Knife4j |
| 日志 | Logback + @Slf4j |

## 功能范围

一次性构建以下全部功能：

1. **用户登录** — 账号密码登录，Sa-Token 签发 token
2. **用户管理** — 用户 CRUD、分配角色、关联部门
3. **RBAC 权限** — 角色管理、菜单权限管理、用户-角色关联、角色-菜单关联
4. **部门管理** — 部门树形 CRUD，用户归属部门
5. **登录日志** — 记录登录 IP、时间、状态
6. **操作日志** — AOP 注解驱动，自动采集操作人、方法、参数、耗时
7. **字典系统** — 字典类型 + 字典项键值对，供下拉选项、状态枚举使用

## 表设计

由 coder 根据领域模型自行设计，不做字段级约束。要求：

- 核心 RBAC：用户表、角色表、菜单权限表、部门表、用户-角色关联表、角色-菜单关联表
- 字典：字典类型表、字典项表
- 日志：登录日志表、操作日志表
- 统一前缀 `sys_`，通用字段统一（status、create_time、update_time）

## API 接口

### 认证 `/api/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 token |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/info` | 当前用户信息（角色、权限列表） |

### 用户管理 `/api/users`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/users` | 分页列表，支持按用户名/部门/状态搜索 |
| POST | `/api/users` | 新增用户 |
| GET | `/api/users/{id}` | 用户详情 |
| PUT | `/api/users/{id}` | 编辑用户 |
| DELETE | `/api/users/{id}` | 删除用户 |
| PUT | `/api/users/{id}/roles` | 分配角色 |

### 角色管理 `/api/roles`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/roles` | 角色列表 |
| POST | `/api/roles` | 新增角色 |
| GET | `/api/roles/{id}` | 角色详情 |
| PUT | `/api/roles/{id}` | 编辑角色 |
| DELETE | `/api/roles/{id}` | 删除角色 |
| PUT | `/api/roles/{id}/menus` | 分配菜单权限 |

### 菜单管理 `/api/menus`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/menus` | 树形结构返回所有菜单 |
| POST | `/api/menus` | 新增菜单 |
| GET | `/api/menus/{id}` | 菜单详情 |
| PUT | `/api/menus/{id}` | 编辑菜单 |
| DELETE | `/api/menus/{id}` | 删除菜单 |

### 部门管理 `/api/depts`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/depts` | 树形结构返回所有部门 |
| POST | `/api/depts` | 新增部门 |
| GET | `/api/depts/{id}` | 部门详情 |
| PUT | `/api/depts/{id}` | 编辑部门 |
| DELETE | `/api/depts/{id}` | 删除部门 |

### 字典管理 `/api/dict-types` `/api/dict-items`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dict-types` | 字典类型列表 |
| POST | `/api/dict-types` | 新增字典类型 |
| GET | `/api/dict-types/{id}` | 类型详情 |
| PUT | `/api/dict-types/{id}` | 编辑字典类型 |
| DELETE | `/api/dict-types/{id}` | 删除字典类型 |
| GET | `/api/dict-types/{type}/items` | 按类型编码获取字典项 |
| POST | `/api/dict-items` | 新增字典项 |
| PUT | `/api/dict-items/{id}` | 编辑字典项 |
| DELETE | `/api/dict-items/{id}` | 删除字典项 |

### 日志 `/api/logs`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs/login` | 登录日志列表，支持搜索筛选 |
| GET | `/api/logs/operation` | 操作日志列表，支持搜索筛选 |

## 项目结构

```
src/main/java/cn/xxx/admin/
│
├── common/                        ← 全局基础设施
│   ├── config/                    ← Sa-Token, MyBatis-Plus, Knife4j, 全局异常
│   ├── exception/                 ← BusinessException, GlobalExceptionHandler
│   ├── result/                    ← Result<T> 统一返回体
│   └── base/                      ← BaseEntity（通用时间字段）
│
├── auth/                          ← 认证
│   ├── controller/AuthController
│   ├── service/AuthService
│   └── dto/
│
├── system/                        ← RBAC 核心
│   ├── controller/                ← User/Role/Menu/DeptController
│   ├── service/
│   ├── mapper/
│   ├── entity/                    ← 6张核心表实体
│   └── dto/
│
├── log/                           ← 日志
│   ├── controller/                ← LoginLog/OperationLogController
│   ├── service/
│   ├── mapper/
│   ├── entity/
│   ├── aspect/                    ← @Log 注解 + AOP 切面
│   └── dto/
│
└── dict/                          ← 字典
    ├── controller/                ← DictType/DictItemController
    ├── service/
    ├── mapper/
    ├── entity/
    └── dto/
```

## 架构约束

以下规则来自 `agents/coder/` 规范，coder 必须遵守：

- **包结构**：controller → service/impl → mapper → entity/dto/vo，每个领域内严格分层
- **返回值**：统一 `Result<T>`
- **注入**：构造注入 `@RequiredArgsConstructor`，禁用 `@Autowired` 字段注入
- **日志**：`@Slf4j`，不打敏感信息
- **异常**：抛 `BusinessException`，不写自由文本
- **SQL**：简单查用 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 `@Select` 注解
- **参数**：>3 个收敛到 DTO
- **URL**：RESTful 复数名词，CRUD 不用动词。非 CRUD 业务动作（login、logout、分配角色/菜单）允许动词
- **配置**：`application.yml` + `logback-spring.xml`

## 关键数据流

### 登录流程
1. 前端 POST `/api/auth/login` {username, password}
2. auth 校验密码 → Sa-Token 签发 token → 记录登录日志（同步或异步）
3. 返回 token + 用户基本信息

### RBAC 鉴权流程
1. Sa-Token 拦截器校验 token 有效性
2. 从 `sys_role_menu` 查出用户所有权限标识
3. `@SaCheckPermission("system:user:add")` 注解校验通过放行

### 操作日志采集
1. 定义 `@Log(module="用户管理", action="新增")` 注解
2. AOP 切面环绕通知：采集操作人、IP、方法、参数 JSON、返回结果、耗时
3. 写入 `sys_operation_log` 表

## 不做

- 不做前端页面
- 不做数据权限（部门数据隔离）
- 不做多租户
- 不做 SSO/OAuth2（后续可加）
