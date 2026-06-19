# 基础设施审查

> 审查基础设施代码：Swagger 文档、配置管理、Redis、国际化、文件上传/下载

---

## 一、Swagger / Knife4j 接口文档

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-IN-01 | Swagger | Controller 类是否加了 `@Tag(name = "模块名")` | P2 | "{class} 缺少 @Tag 注解" | `../coder/infrastructure/swagger-guide.md #三.1` |
| BE-IN-02 | Swagger | Controller 方法是否加了 `@Operation(summary = "描述")` | P2 | "{method} 缺少 @Operation 注解" | `../coder/infrastructure/swagger-guide.md #三.1` |
| BE-IN-03 | Swagger | GET 的 `@PathVariable` / `@RequestParam` 是否加了 `@Parameter(description = "...")` | P2 | "{method} 的 {param} 缺少 @Parameter 注解" | `../coder/infrastructure/swagger-guide.md #三.1` |
| BE-IN-04 | Swagger | DTO 字段是否加了 `@Schema(description = "...")` | P2 | "{class}.{field} 缺少 @Schema 注解" | `../coder/infrastructure/swagger-guide.md #三.3` |
| BE-IN-05 | Swagger | VO 字段是否每个字段都加了 `@Schema(description = "...")` | P2 | "{class}.{field} 缺少 @Schema 注解" | `../coder/infrastructure/swagger-guide.md #三.4` |
| BE-IN-06 | Swagger | `@Schema.requiredMode` 是否与校验注解一致（有 @NotNull → REQUIRED，无 → NOT_REQUIRED） | P2 | "{class}.{field} @Schema.requiredMode 与校验注解不一致" | `../coder/infrastructure/swagger-guide.md #三.3` |
| BE-IN-07 | Swagger | 生产环境 `application-prod.yml` 中 `knife4j.enable` 是否为 `false` | P1 | "生产环境 knife4j.enable 应为 false" | `../coder/infrastructure/swagger-guide.md #六` |

---

## 二、配置管理

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-IN-08 | 配置管理 | 敏感信息（密码、密钥）是否明文写在 yml 并提交仓库 | P0 | "{file} 包含明文敏感信息" | `../coder/infrastructure/config-guide.md #三.4` |
| BE-IN-09 | 配置管理 | 数据库密码/Redis 密码是否通过环境变量 `${VAR:}` 占位 | P1 | "{config} 应通过环境变量占位符注入" | `../coder/infrastructure/config-guide.md #三.2` |
| BE-IN-10 | 配置管理 | 业务配置是否用 `@ConfigurationProperties` 绑定，未用 `@Value` 散落 | P1 | "{class} 应使用 @ConfigurationProperties 替代 @Value" | `../coder/infrastructure/config-guide.md #二.1` |
| BE-IN-11 | 配置管理 | 配置文件是否按环境拆分（application-dev/test/prod.yml） | P2 | "配置文件应按环境拆分" | `../coder/infrastructure/config-guide.md #一.1` |
| BE-IN-12 | 配置管理 | Nacos 地址是否通过环境变量注入，未硬编码 IP | P1 | "{config} Nacos 地址应通过环境变量注入" | `../coder/infrastructure/config-guide.md #四.3` |
| BE-IN-13 | 配置管理 | 数据库连接、Redis 连接是否配了 `@RefreshScope` | P1 | "{class} 中间件连接不支持 @RefreshScope 热刷新" | `../coder/infrastructure/config-guide.md #四.5` |
| BE-IN-14 | 配置管理 | Nacos 配置是否用 Namespace 区分环境 | P2 | "Nacos 应使用 Namespace 区分环境" | `../coder/infrastructure/config-guide.md #四.4` |

---

## 三、Redis

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-IN-15 | Redis | 是否直接使用 `RedisTemplate` 存取 | P1 | "{class} 应使用 RedisUtil 封装，不直接使用 RedisTemplate" | `../coder/infrastructure/redis-guide.md #二` |
| BE-IN-16 | Redis | Key 命名是否使用 `{项目}:{模块}:{类型}:{标识}` 格式，分隔符用 `:` | P2 | "{key} Key 命名不符合 {项目}:{模块}:{类型}:{标识} 格式" | `../coder/infrastructure/redis-guide.md #三` |
| BE-IN-17 | Redis | 是否不设过期时间长期缓存数据 | P1 | "{key} 未设置过期时间，可能导致内存膨胀" | `../coder/infrastructure/redis-guide.md #四` |
| BE-IN-18 | Redis | 是否存储了 > 10KB 的大对象 | P2 | "{key} 存储了大对象，应换用 OSS/MinIO" | `../coder/infrastructure/redis-guide.md #六` |
| BE-IN-19 | Redis | 是否在线环境使用 `keys *` | P1 | "{method} 在生产环境使用 keys *，应使用 scan" | `../coder/infrastructure/redis-guide.md #六` |
| BE-IN-20 | Redis | 敏感信息是否明文存 Redis | P1 | "{key} 明文存储敏感信息" | `../coder/infrastructure/redis-guide.md #六` |
| BE-IN-21 | Redis | Value 序列化是否配置为 JSON（`Jackson2JsonRedisSerializer`） | P2 | "Redis Value 序列化应配置为 Jackson2JsonRedisSerializer" | `../coder/infrastructure/redis-guide.md #一` |
| BE-IN-22 | Redis | Key 是否硬编码散落各处（应定义 `RedisKeys` 常量类） | P2 | "{key} 应定义在 RedisKeys 常量类中" | `../coder/infrastructure/redis-guide.md #六` |

---

## 四、国际化

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-IN-23 | 国际化 | `ValidationMessages.properties` 和 `messages.properties` 是否分开存在 | P1 | "缺少 ValidationMessages.properties 或 messages.properties" | `../coder/quality/i18n-guide.md #一` |
| BE-IN-24 | 国际化 | 新增 BusinessErrorEnum 后是否在 `messages_zh_CN.properties` 和 `messages_en_US.properties` 中都添加了对应 key | P1 | "{enum} 缺少对应的国际化资源" | `../coder/quality/i18n-guide.md #二` |
| BE-IN-25 | 国际化 | 系统内部日志是否固定用 `zh_CN`（运维可读性） | P2 | "系统内部日志应固定使用 zh_CN" | `../coder/quality/i18n-guide.md #三` |
| BE-IN-26 | 国际化 | 非 HTTP 场景是否手动从数据库获取 `locale` 而非依赖请求头 | P2 | "非 HTTP 场景应从数据库获取 locale" | `../coder/quality/i18n-guide.md #三` |

---

## 五、文件上传/下载

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-IN-27 | 文件上传 | 是否配置了 `spring.servlet.multipart.max-file-size` 全局大小限制 | P1 | "缺少全局文件大小限制配置" | `../coder/infrastructure/file-upload-guide.md #一` |
| BE-IN-28 | 文件上传 | 文件类型是否使用白名单校验（禁止黑名单） | P1 | "文件类型校验应使用白名单而非黑名单" | `../coder/infrastructure/file-upload-guide.md #二` |
| BE-IN-29 | 文件上传 | 是否校验了文件魔数（文件头） | P1 | "缺少文件魔数校验，Content-Type 可被伪造" | `../coder/infrastructure/file-upload-guide.md #二.3` |
| BE-IN-30 | 文件上传 | 文件名是否由服务端生成（UUID/雪花ID），未使用用户原始文件名 | P0 | "使用了用户原始文件名做存储路径，存在路径遍历风险" | `../coder/infrastructure/file-upload-guide.md #三` |
| BE-IN-31 | 文件上传 | 上传文件是否存放到 `static/` 或 `resources/` 目录 | P1 | "文件存储路径不应在 static/resources 下，可被直接 URL 访问" | `../coder/infrastructure/file-upload-guide.md #四.3` |
| BE-IN-32 | 文件上传 | 下载接口是否通过 fileId 查找，不暴露服务器文件路径 | P1 | "下载接口暴露了服务器文件路径，存在路径遍历风险" | `../coder/infrastructure/file-upload-guide.md #五` |

---

## 六、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/infrastructure/swagger-guide.md` | Swagger/Knife4j 注解规范 |
| `../coder/infrastructure/config-guide.md` | 配置管理、Nacos、敏感信息加密 |
| `../coder/infrastructure/redis-guide.md` | Redis 序列化、Key 命名、过期时间 |
| `../coder/infrastructure/file-upload-guide.md` | 文件上传/下载安全规范 |
| `../coder/quality/i18n-guide.md` | 国际化双轨体系、业务异常消息 |
| `../coder/quality/jsr303-guide.md` | JSR 303 校验消息国际化 |
