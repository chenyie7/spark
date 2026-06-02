# 配置管理规范

> 适用：Spring Boot 3 + Nacos（微服务），单体项目只涉及前两节

---

## 一、多环境隔离

### 1.1 文件拆分

```
resources/
├── application.yml              # 公共配置（所有环境相同）
├── application-dev.yml          # 开发环境
├── application-test.yml         # 测试环境
├── application-prod.yml         # 生产环境
```

### 1.2 职责

| 文件 | 内容 |
|------|------|
| `application.yml` | 只放所有环境相同的公共配置（应用名、公共连接池大小等） |
| `application-{profile}.yml` | 环境差异配置（数据库地址、Redis地址、日志级别、Nacos地址） |

### 1.3 启动指定

```bash
java -jar app.jar --spring.profiles.active=dev
```

---

## 二、配置属性注入

### 2.1 业务配置：强制 `@ConfigurationProperties`

所有自定义业务配置必须用 `@ConfigurationProperties` 绑定，禁止用 `@Value` 散落各处：

```java
// ✅ @ConfigurationProperties
@ConfigurationProperties(prefix = "app.upload")
public class UploadConfig {
    private String path;
    private long maxSize;
    private List<String> allowedTypes;
}

// ❌ 禁止 @Value 散落
@Service
public class FileService {
    @Value("${app.upload.path}")    // 东一个西一个，难以追踪
    private String uploadPath;
}
```

### 2.2 启用配置类

```java
@Configuration
@EnableConfigurationProperties(UploadConfig.class)
public class AppConfig {
}
```

### 2.3 规则

- `app.*` 开头的业务自定义配置 → `@ConfigurationProperties`
- Spring 框架自身配置（`spring.datasource.*` 等） → yml 中配置即可，不需要 Java 类绑定

---

## 三、敏感配置加密

### 3.1 推荐策略

| 方式 | 适用场景 |
|------|---------|
| 环境变量占位符 `${VAR:}` | **数据库密码、Redis 密码**等基础设施凭证（首选） |
| jasypt `ENC()` | 第三方 API Key 等不想配环境变量的场景（备选） |

### 3.2 环境变量占位符（首选）

```yaml
# application.yml
spring:
  datasource:
    password: ${DB_PASSWORD:}      # 启动时从环境变量注入，不写死
  redis:
    password: ${REDIS_PASSWORD:}
```

**注入方式：**

| 场景 | 方式 |
|------|------|
| 本地开发 | IDE 中配置环境变量，或 `export DB_PASSWORD=xxx` |
| Docker | `docker run -e DB_PASSWORD=xxx` 或 `env_file` |
| K8s | `Secret` 挂载为环境变量 |

### 3.3 jasypt 加密（备选）

```xml
<dependency>
    <groupId>com.github.ulisesbocchio</groupId>
    <artifactId>jasypt-spring-boot-starter</artifactId>
    <version>3.0.5</version>
</dependency>
```

```yaml
# application.yml — 密文可提交仓库
app:
  wechat:
    app-secret: ENC(加密后的密文)

# 密钥通过启动参数或环境变量传入，不写在配置文件
# java -jar app.jar --jasypt.encryptor.password=YourSecretKey
```

### 3.4 不论用哪种方式

- **敏感信息一律不进仓库**：密文可以进仓库（jasypt），密钥不进
- 环境变量占位符是默认选择，jasypt 作为备选

---

## 四、微服务：Nacos 配置中心

### 4.1 依赖

```xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-nacos-config</artifactId>
</dependency>
```

### 4.2 配置架构

Nacos 中配置分三层：

| 层级 | 类型 | 示例 | 作用范围 |
|------|------|------|---------|
| 全局共享 | `shared-configs` | `common-datasource.yml`、`common-redis.yml` | 所有服务 |
| 业务共享 | `extension-configs` | `common-message.yml` | 多个服务共用 |
| 服务私有 | `${application.name}.yml` | `business-user.yml` | 单个服务 |

**优先级**：服务私有 > extension-configs > shared-configs（私有覆盖共享）

### 4.3 本地 yml 配置（导入 Nacos）

Spring Boot 3 不使用 `bootstrap.yml`，用 `spring.config.import` 导入 Nacos：

```yaml
# application.yml
spring:
  config:
    import:
      - optional:nacos:${spring.application.name}.yml     # 服务私有配置
  cloud:
    nacos:
      config:
        server-addr: ${NACOS_SERVER:localhost:8848}
        namespace: ${spring.profiles.active}               # 按环境隔离：dev/test/prod
                                                         # 注意：Nacos 命名空间默认 ID 是 UUID，
                                                         # 需在 Nacos 控制台创建时手动设为环境名
        group: DEFAULT_GROUP
        shared-configs:                                     # 全局共享
          - data-id: common-datasource.yml
            group: DEFAULT_GROUP
            refresh: true                                   # 允许自动刷新
          - data-id: common-redis.yml
            group: DEFAULT_GROUP
            refresh: true
```

**注意：**
- Nacos 地址通过环境变量 `${NACOS_SERVER:}` 注入，不可硬编码 IP
- `optional:` 前缀表示 Nacos 不可用时服务能启动（不影响本地开发）

### 4.4 Nacos 管理界面结构

```
Namespace: dev                           Namespace: prod
  ├── common-datasource.yml                ├── common-datasource.yml
  ├── common-redis.yml                     ├── common-redis.yml
  ├── common-message.yml                   ├── common-message.yml
  ├── business-user.yml                    ├── business-user.yml
  ├── business-order.yml                   ├── business-order.yml
  └── business-payment.yml                 └── business-payment.yml
```

- **用 Namespace 区分环境**，不用 Group 区分，权限管理更方便
- 生产 Namespace 控制台权限设为**只读**，防止误操作

### 4.5 配置热刷新

需要动态刷新的 Bean 加 `@RefreshScope`：

```java
@Service
@RefreshScope
public class RuleService {
    @ConfigurationProperties(prefix = "app.rule")
    public static class RuleConfig {
        private int maxRetry;
        private int timeout;
    }
}
```

**注意：** 数据库连接池、Redis 连接等中间件配置**不支持**热刷新，需重启 Pod。

### 4.6 本地 yml 与 Nacos 的职责划分

| 配置类型 | 放哪里 | 说明 |
|---------|--------|------|
| 服务端口、应用名 | 本地 yml | 部署前就确定，不会动态变 |
| Nacos 地址 | 本地 yml | 启动时优先加载，否则无法连接 Nacos |
| 数据库/Redis/MQ 地址 | **Nacos 共享配置** | 多服务一致，改一处全生效 |
| 业务规则、开关、阈值 | **Nacos 私有配置** | 动态调整不用重启 |
| 第三方服务地址、AppKey | **Nacos 共享 or 私有** | 按使用范围 |
| 日志级别 | 本地 yml（prod） | 生产不宜动，Nacos 可能影响性能 |

---

## 五、禁止事项

| 禁止 | 原因 |
|------|------|
| 敏感信息明文写在 yml 并提交仓库 | 安全合规，密钥泄露 |
| `@Value` 散落注入业务配置 | 难以追踪哪些类用了哪些配置 |
| Nacos 地址硬编码 IP | 不同环境 IP 不同，用环境变量 |
| 数据库连接、Redis 连接配 `@RefreshScope` | 中间件连接不支持热刷新，会导致错误 |
| 配置文件混乱存放 | 严格按照 profile 和环境拆分 |

---

## 六、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../architecture/microservice-architecture-guide.md` | 微服务项目结构，common-config 模块 |
| `logging-guide.md` | 日志级别环境配置 |
| `../layered/service-guide.md` | Nacos 热刷新 @RefreshScope 使用 |
