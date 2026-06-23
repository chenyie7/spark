# 后台管理系统 — 实现计划

> **For agentic workers:** 此计划通过 `/build` 技能执行 —— coder 自动生成代码，reviewer 双层审查，自动修复循环。

**Goal:** 从零构建 Spring Boot 3 后台管理系统 API，含认证、RBAC、日志、字典四大模块，约 30 个接口、10 张表。

**Architecture:** 领域驱动单体 —— `common/auth/system/log/dict` 五个包，每包内严格分层（controller → service → mapper → entity/dto）。Sa-Token 做认证鉴权，MyBatis-Plus 做 ORM，Knife4j 做文档。

**Tech Stack:** Spring Boot 3, Sa-Token, MyBatis-Plus, MySQL, Knife4j, Lombok, @Slf4j

**Spec:** `docs/superpowers/specs/2026-06-23-admin-system-design.md`

---

## 预期产出清单

build skill 完成后，应生成以下文件：

```
pom.xml                              ← Spring Boot 3 + 全部依赖
src/main/resources/
├── application.yml                  ← MySQL / Sa-Token / Knife4j / 日志
└── logback-spring.xml               ← 日志控制台输出

src/main/java/cn/xxx/admin/
├── AdminApplication.java            ← Spring Boot 启动类
│
├── common/
│   ├── config/
│   │   ├── SaTokenConfig.java       ← Sa-Token 配置 + 权限拦截器
│   │   ├── MybatisPlusConfig.java   ← 分页插件
│   │   ├── Knife4jConfig.java       ← API 文档配置
│   │   └── GlobalExceptionHandler.java ← 全局异常拦截
│   ├── exception/
│   │   └── BusinessException.java   ← 业务异常基类
│   ├── result/
│   │   └── Result.java              ← Result<T> 统一返回体
│   └── base/
│       └── BaseEntity.java          ← 通用时间字段
│
├── auth/
│   ├── controller/
│   │   └── AuthController.java      ← /api/auth/login, logout, info
│   ├── service/
│   │   └── AuthService.java
│   └── dto/
│       ├── LoginReq.java
│       └── LoginResp.java
│
├── system/
│   ├── controller/
│   │   ├── UserController.java      ← /api/users CRUD + 分配角色
│   │   ├── RoleController.java      ← /api/roles CRUD + 分配菜单
│   │   ├── MenuController.java      ← /api/menus 树形 CRUD
│   │   └── DeptController.java      ← /api/depts 树形 CRUD
│   ├── service/
│   │   ├── UserService.java
│   │   ├── RoleService.java
│   │   ├── MenuService.java
│   │   └── DeptService.java
│   ├── mapper/
│   │   ├── UserMapper.java
│   │   ├── RoleMapper.java
│   │   ├── MenuMapper.java
│   │   ├── DeptMapper.java
│   │   ├── UserRoleMapper.java
│   │   └── RoleMenuMapper.java
│   ├── entity/
│   │   ├── User.java, Role.java, Menu.java, Dept.java
│   │   ├── UserRole.java, RoleMenu.java
│   │   └── (XML: resources/mapper/ 下的联表查询)
│   └── dto/                         ← 各 Controller 对应的 DTO
│
├── log/
│   ├── controller/
│   │   ├── LoginLogController.java  ← /api/logs/login
│   │   └── OperationLogController.java ← /api/logs/operation
│   ├── service/
│   │   ├── LoginLogService.java
│   │   └── OperationLogService.java
│   ├── mapper/
│   │   ├── LoginLogMapper.java
│   │   └── OperationLogMapper.java
│   ├── entity/
│   │   ├── LoginLog.java
│   │   └── OperationLog.java
│   ├── aspect/
│   │   └── LogAspect.java           ← @Log 注解 + AOP 切面
│   └── dto/
│
└── dict/
    ├── controller/
    │   ├── DictTypeController.java  ← /api/dict-types CRUD + 按编码获取项
    │   └── DictItemController.java  ← /api/dict-items CRUD
    ├── service/
    │   ├── DictTypeService.java
    │   └── DictItemService.java
    ├── mapper/
    │   ├── DictTypeMapper.java
    │   └── DictItemMapper.java
    ├── entity/
    │   ├── DictType.java
    │   └── DictItem.java
    └── dto/
```

预计 **40+ 个 Java 文件** + 3 个资源文件 + pom.xml。

---

## 执行步骤

### Task 1: 清理环境

- [ ] **Step 1: 确认从零开始**

删除之前可能残留的 src 目录和 pom.xml：

```bash
rm -rf src/main/java src/main/resources pom.xml
```

确定 Java 文件生成目录为空：

```bash
ls src/main/java 2>/dev/null || echo "目录不存在或为空（预期）"
```

### Task 2: 运行 /build 流水线

- [ ] **Step 1: 启动 build skill**

将以下完整需求需求输入 `/build`：

```
构建一个后台管理系统，从零新建 Spring Boot 3 项目，纯后端 API，包路径 cn.xxx.admin。

完整功能清单：
1. 用户登录 — 账号密码登录，Sa-Token 签发 token，/api/auth/login、/api/auth/logout、/api/auth/info
2. 用户管理 — 分页列表/新增/详情/编辑/删除/分配角色，/api/users
3. 角色管理 — CRUD + 分配菜单权限，/api/roles
4. 菜单权限管理 — 树形结构 CRUD，支持目录/菜单/按钮三种类型，/api/menus
5. 部门管理 — 树形 CRUD，/api/depts
6. 登录日志 — 记录 IP/时间/状态/浏览器，/api/logs/login 只读列表
7. 操作日志 — AOP @Log 注解驱动，自动采集操作人/方法/参数/耗时/IP，/api/logs/operation 只读列表
8. 字典系统 — 字典类型 CRUD + 字典项 CRUD，按类型编码获取字典项，/api/dict-types + /api/dict-items

核心 RBAC 表：sys_user、sys_role、sys_menu（parent_id树形）、sys_dept（parent_id树形）、sys_user_role、sys_role_menu
字典表：sys_dict_type、sys_dict_item
日志表：sys_login_log、sys_operation_log
统一 sys_ 前缀，通用字段 status/create_time/update_time。

架构约束读取 agents/coder/README.md：
- 包结构：controller → service/impl → mapper → entity/dto/vo，按 common/auth/system/log/dict 五个领域分包
- 返回值统一 Result<T>
- 构造注入 @RequiredArgsConstructor
- @Slf4j 日志，抛 BusinessException
- MyBatis-Plus LambdaQueryWrapper + XML 联表查询（禁用 @Select 注解）
- 参数 >3 收敛到 DTO
- URL RESTful 复数名词

项目配置：MySQL 数据库连接、Sa-Token 权限拦截、Knife4j API 文档、Logback 日志
```

- [ ] **Step 2: 等待流水线自动运行**

流水线会自动执行 coder → reviewer → fix 循环（最多 3 轮）。观察每轮的进度报告：

```
📊 第 {round}/{max_retries} 轮完成
   review 结果：{PASSED / FAILED / ERROR}
   ➡️ {下一步动作}
```

### Task 3: 验证产出

- [ ] **Step 1: 检查文件生成数量**

```bash
find src/main/java -name "*.java" | wc -l
```
预期：≥ 40 个 Java 文件

- [ ] **Step 2: 检查关键文件存在**

```bash
# 启动类
ls src/main/java/cn/xxx/admin/AdminApplication.java

# 全局基础设施
ls src/main/java/cn/xxx/admin/common/result/Result.java
ls src/main/java/cn/xxx/admin/common/exception/BusinessException.java

# 认证
ls src/main/java/cn/xxx/admin/auth/controller/AuthController.java

# RBAC 核心
ls src/main/java/cn/xxx/admin/system/controller/UserController.java
ls src/main/java/cn/xxx/admin/system/controller/RoleController.java
ls src/main/java/cn/xxx/admin/system/controller/MenuController.java
ls src/main/java/cn/xxx/admin/system/controller/DeptController.java

# 日志
ls src/main/java/cn/xxx/admin/log/aspect/LogAspect.java

# 字典
ls src/main/java/cn/xxx/admin/dict/controller/DictTypeController.java
ls src/main/java/cn/xxx/admin/dict/controller/DictItemController.java

# 配置文件
ls pom.xml
ls src/main/resources/application.yml
```

- [ ] **Step 3: 读取最终审查报告**

```bash
cat review-output/final-review-report.md
```

确认 P0 = 0，无阻断问题。

### Task 4: 编译验证

- [ ] **Step 1: Maven 编译**

```bash
mvn compile -q
```

预期：BUILD SUCCESS，无编译错误。

- [ ] **Step 2: 如有编译错误，手动修复**

检查常见的编译问题：
- 缺少依赖（pom.xml 中是否包含了所有需要的 starter）
- import 路径错误
- Lombok 注解处理器是否配置

---

## 验证清单

| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| P0 清零 | `cat review-output/final-review-report.md` | P0 = 0 |
| 编译通过 | `mvn compile` | BUILD SUCCESS |
| 文件数量 | `find src/main/java -name "*.java" \| wc -l` | ≥ 40 |
| Result<T> 统一 | `grep -r "Result<" src/main/java` | 所有 Controller 返回 Result |
| 构造注入 | `grep -r "@Autowired" src/main/java` 应为空 | 0 个 @Autowired |
| @Slf4j 日志 | `grep -r "@Slf4j" src/main/java` | 所有 Service 有 @Slf4j |
| URL RESTful | 抽查 Controller | 复数名词，无动词 CRUD URL |
| pom.xml 依赖完整 | `grep "sa-token\|mybatis-plus\|knife4j\|mysql\|lombok" pom.xml` | 5 个核心依赖都有 |

---

## 边界约束（重要）

- coder 只能修改 `src/main/java/` 和项目根目录的 `pom.xml`
- **禁止**修改 `agents/` 或 `hooks/` 目录下的任何文件
- **禁止**修改 `review-output/` 目录（审查产物）
- 如需添加 Maven 依赖，只在根 pom.xml 中操作
