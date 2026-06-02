# 基础设施审查

> 审查基础设施代码：Swagger 文档、配置管理、Redis、国际化

---

## 一、Swagger / Knife4j 接口文档

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 1.1 | Controller 类是否加了 `@Tag(name = "模块名")` | P2 | `../coder/infrastructure/swagger-guide.md #三.1` |
| 1.2 | Controller 方法是否加了 `@Operation(summary = "描述")` | P2 | `../coder/infrastructure/swagger-guide.md #三.1` |
| 1.3 | GET 的 `@PathVariable` / `@RequestParam` 是否加了 `@Parameter(description = "...")` | P2 | `../coder/infrastructure/swagger-guide.md #三.1` |
| 1.4 | DTO 字段是否加了 `@Schema(description = "...")` | P2 | `../coder/infrastructure/swagger-guide.md #三.3` |
| 1.5 | VO 字段是否**每个字段**都加了 `@Schema(description = "...")` | P2 | `../coder/infrastructure/swagger-guide.md #三.4` |
| 1.6 | `@Schema.requiredMode` 是否与校验注解一致（有 @NotNull → REQUIRED，无 → NOT_REQUIRED） | P2 | `../coder/infrastructure/swagger-guide.md #三.3` |
| 1.7 | 生产环境 `application-prod.yml` 中 `knife4j.enable` 是否为 `false` | P1 | `../coder/infrastructure/swagger-guide.md #六` |

---

## 二、配置管理

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 2.1 | 敏感信息（密码、密钥）是否明文写在 yml 并提交仓库（禁止） | P0 | `../coder/infrastructure/config-guide.md #三.4` |
| 2.2 | 数据库密码/Redis 密码是否通过环境变量 `${VAR:}` 占位 | P1 | `../coder/infrastructure/config-guide.md #三.2` |
| 2.3 | 业务配置是否用 `@ConfigurationProperties` 绑定，未用 `@Value` 散落 | P1 | `../coder/infrastructure/config-guide.md #二.1` |
| 2.4 | 配置文件是否按环境拆分（application-dev/test/prod.yml） | P2 | `../coder/infrastructure/config-guide.md #一.1` |
| 2.5 | Nacos 地址是否通过环境变量注入，未硬编码 IP | P1 | `../coder/infrastructure/config-guide.md #四.3` |
| 2.6 | 数据库连接、Redis 连接是否配了 `@RefreshScope`（禁止，中间件不支持热刷新） | P1 | `../coder/infrastructure/config-guide.md #四.5` |
| 2.7 | Nacos 配置是否用 Namespace 区分环境 | P2 | `../coder/infrastructure/config-guide.md #四.4` |

---

## 三、Redis

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 3.1 | 是否直接使用 `RedisTemplate` 存取（应用 `RedisUtil` 封装） | P1 | `../coder/infrastructure/redis-guide.md #二` |
| 3.2 | Key 命名是否使用 `{项目}:{模块}:{类型}:{标识}` 格式，分隔符用 `:` | P2 | `../coder/infrastructure/redis-guide.md #三` |
| 3.3 | 是否不设过期时间长期缓存数据（禁止，计数器除外） | P1 | `../coder/infrastructure/redis-guide.md #四` |
| 3.4 | 是否存储了 > 10KB 的大对象（禁止，应换 OSS/MinIO） | P2 | `../coder/infrastructure/redis-guide.md #六` |
| 3.5 | 是否在线环境使用 `keys *`（禁止，应用 `scan`） | P1 | `../coder/infrastructure/redis-guide.md #六` |
| 3.6 | 敏感信息是否明文存 Redis（禁止，必要时脱敏） | P1 | `../coder/infrastructure/redis-guide.md #六` |
| 3.7 | Value 序列化是否配置为 JSON（`Jackson2JsonRedisSerializer`） | P2 | `../coder/infrastructure/redis-guide.md #一` |
| 3.8 | Key 是否硬编码散落各处（应定义 `RedisKeys` 常量类） | P2 | `../coder/infrastructure/redis-guide.md #六` |

---

## 四、国际化

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 4.1 | `ValidationMessages.properties` 和 `messages.properties` 是否分开存在 | P1 | `../coder/quality/i18n-guide.md #一` |
| 4.2 | 新增 BusinessErrorEnum 后是否在 `messages_zh_CN.properties` 和 `messages_en_US.properties` 中都添加了对应 key | P1 | `../coder/quality/i18n-guide.md #二` |
| 4.3 | 系统内部日志是否固定用 `zh_CN`（运维可读性） | P2 | `../coder/quality/i18n-guide.md #三` |
| 4.4 | 非 HTTP 场景是否手动从数据库获取 `locale` 而非依赖请求头 | P2 | `../coder/quality/i18n-guide.md #三` |

---

## 五、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/infrastructure/swagger-guide.md` | Swagger/Knife4j 注解规范 |
| `../coder/infrastructure/config-guide.md` | 配置管理、Nacos、敏感信息加密 |
| `../coder/infrastructure/redis-guide.md` | Redis 序列化、Key 命名、过期时间 |
| `../coder/quality/i18n-guide.md` | 国际化双轨体系、业务异常消息 |
| `../coder/quality/jsr303-guide.md` | JSR 303 校验消息国际化 |
