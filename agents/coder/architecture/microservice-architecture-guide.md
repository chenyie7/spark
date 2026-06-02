# Spring Cloud 微服务架构规范

> 适用：Spring Boot 3 + Spring Cloud 微服务架构

---

## 一、项目结构总览

```
project/
├── project-common/              # 公共组件（jar，所有服务依赖）
│   ├── common-result/          # 统一返回结果 Result<T>
│   ├── common-exception/       # 全局异常处理、BusinessException
│   ├── common-enums/           # 公共枚举（BusinessErrorEnum 等）
│   ├── common-util/            # 工具类
│   └── common-config/          # 公共 Spring 配置
│       ├── JacksonConfig        # JSON 序列化
│       ├── MessageSourceConfig  # 国际化
│       └── HttpExchangeConfig   # HTTP 客户端拦截器（透传语言、认证）
│
├── project-api/                 # API 契约层（jar，接口 + DTO/VO + 降级）
│   ├── api-user/               # UserClient + dto/ + vo/ + fallback
│   ├── api-order/
│   └── api-payment/
│
├── project-gateway/             # 网关服务（独立 Spring Boot）
│   ├── 路由配置
│   ├── 全局过滤器（鉴权、限流、日志）
│   └── 跨域配置
│
├── project-auth/                # 认证授权服务（独立 Spring Boot）
│   ├── Token 管理
│   ├── 登录/登出
│   └── 权限校验
│
├── project-business/            # 核心业务服务（每个子模块独立部署）
│   ├── business-user/
│   ├── business-order/
│   └── business-payment/
│
├── project-platform/            # 后台管理聚合服务（可选）
│   └── platform-admin/
│
├── sql/                         # 数据库脚本集中管理
│   ├── user.sql
│   └── order.sql
│
├── docker/                      # 容器编排
│   └── docker-compose.yml       # 本地开发环境
│
└── docs/                        # 架构文档
```

---

## 二、common 模块规范

### 2.1 common-result

`Result<T>` 统一返回体，所有 Controller 返回值必须使用此类。完整定义和使用方式见 `infrastructure/result-guide.md`。

### 2.2 common-exception

- `BusinessException` + `BusinessErrorEnum`（定义见 `quality/error-code-reference.md`）
- `GlobalExceptionHandler` 放在此模块，各服务自动继承

### 2.3 common-enums

全局公共枚举，包含 `BusinessErrorEnum` 及业务状态枚举。

### 2.4 common-util

纯工具类，不依赖 Spring Bean，不包含业务逻辑。

### 2.5 common-config

各服务共享的 Spring 配置：

- **JacksonConfig**：统一 JSON 序列化规则（日期格式、null 值处理）
- **MessageSourceConfig**：国际化配置（见 `quality/i18n-guide.md`）
- **HttpExchangeConfig**：HTTP 客户端拦截器，透传 `Accept-Language`、`Authorization` 等请求头

---

## 三、api 契约层规范

### 3.1 接口定义

使用 Spring Boot 3 内置 `@HttpExchange` 声明接口，**替代 OpenFeign**：

```java
// api-user 模块中定义
@HttpExchange("/api/users")
public interface UserClient {

    @GetExchange("/{id}")
    Result<UserVO> getUser(@PathVariable Long id);

    @PostExchange
    Result<Void> create(@RequestBody UserCreateDTO dto);
}
```

### 3.2 降级处理

降级结合 Resilience4j（Spring Cloud CircuitBreaker）：

```java
// api-user 模块中定义 fallback
@Component
public class UserClientFallback implements UserClient {
    @Override
    public Result<UserVO> getUser(Long id) {
        return Result.error(50001, "用户服务暂不可用");
    }
}
```

### 3.3 api 层内容

api 模块包含三类内容：**接口定义 + 跨服务契约 DTO/VO + 降级实现**。

```
api-user/
├── UserClient.java              # HttpExchange 接口
├── fallback/
│   └── UserClientFallback.java  # 降级实现
├── dto/                          # 跨服务调用的入参（只放 UserClient 接口中用到的）
│   └── UserCreateDTO.java       # 其他服务调 create 时传入
└── vo/                           # 跨服务调用的出参（只放 UserClient 接口中用到的）
    └── UserVO.java              # 其他服务调 getUser 时返回
```

**规则：**
- dto 和 vo **必须是两个独立包**，不混放
- api 模块只放出现在 `{服务名}Client` 接口**入参或返回值**中的 DTO/VO
- 消费者引入 api 模块后直接使用其中的 DTO/VO，无需额外依赖
- **禁止**在 api 模块中放业务逻辑

---

## 四、业务服务内部结构

每个 business 服务内部按单体模式包结构（见 `package-structure-guide.md`）：

```
business-user/src/main/java/com/chenyi/user/
├── controller/       # 控制层
├── service/          # 服务层接口
│   └── impl/         # 服务层实现
├── mapper/           # 数据访问层
├── entity/           # 数据库实体
├── dto/              # 服务内部接口的入参（不被其他服务调用的）
├── vo/               # 服务内部接口的出参（不被其他服务调用的）
├── config/           # 该服务私有配置
└── UserApplication.java
```

### 4.1 DTO/VO 放置规则

| 放在哪里 | 范围 | 判断标准 |
|---------|------|---------|
| **api 模块** `dto/` `vo/` | 跨服务调用的契约 DTO/VO | 出现在 `{服务名}Client` 接口的入参或返回值中 |
| **business 模块** `dto/` `vo/` | 仅本服务内部使用的 DTO/VO | 不出现在 Client 接口中，仅本服务 Controller 使用 |

**示例：**

- `UserCreateDTO` 出现在 `UserClient.create()` 入参 → 放 api-user
- `UserVO` 出现在 `UserClient.getUser()` 返回值 → 放 api-user
- `UserDetailVO` 是内部聚合查询用的，不对外暴露 → 放 business-user
- `UserInternalReportDTO` 是内部报表导出用的 → 放 business-user

### 4.2 约束

- Controller 根据接口类型引用不同来源的 DTO/VO：跨服务接口用 api 模块的，内部接口用 business 自己的
- business 模块依赖自己的 api 模块：`business-user → api-user`

---

## 五、服务调用链

```
Gateway → Auth Service（鉴权）
                ↓
         Business Service → api-xxx (HttpExchange) → Business Service
                ↓
           Mapper → DB
```

```
平台调用示例：

platform-admin → api-user (UserClient)
              → api-order (OrderClient)
              → api-payment (PaymentClient)
```

---

## 六、Docker 部署规范

- 每个可部署服务（gateway、auth、business-xxx）根目录下放 `Dockerfile`
- 项目根目录 `docker/docker-compose.yml` 统一编排
- 不在根目录散落 Dockerfile 或 docker-compose 文件

```
project/
├── docker/
│   └── docker-compose.yml
├── project-gateway/
│   └── Dockerfile
├── project-auth/
│   └── Dockerfile
└── project-business/
    └── business-user/
        └── Dockerfile
```

---

## 七、模块依赖关系

```
project-business/* → project-api/* → project-common
project-gateway    → project-common
project-auth       → project-common
project-platform   → project-api/*  → project-common
```

**规则：**

- common 不依赖任何其他模块
- api 只依赖 common
- business 依赖 common + api
- 禁止循环依赖
- 禁止 business 之间直接依赖（只能通过 api 接口调用）

---

## 八、与单体模式的切换

从单体切换到微服务时：

| 单体 | 微服务 |
|------|--------|
| `com.chenyi.{project}.controller` | 按服务拆分到各 business 模块 |
| `com.chenyi.{project}.common` | 抽取到 `project-common` |
| `com.chenyi.{project}.enums` | 抽取到 `project-common/common-enums` |
| 模块内互相注入调用 | 通过 api 模块的 HTTP 接口调用 |
| 无 api 层 | 新增 api 层定义服务契约 |
