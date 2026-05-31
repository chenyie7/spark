# 日志规范

> 适用：Spring Boot + Lombok @Slf4j，单体 + 微服务

---

## 一、日志框架

使用 Lombok `@Slf4j` + Logback（Spring Boot 默认），不额外引入 Log4j2：

```java
@Slf4j
@Service
public class UserServiceImpl implements UserService {
    // Lombok 自动生成 private static final Logger log = ...
}
```

**所有需要打日志的类必须加 `@Slf4j`**，禁止手动声明 `Logger` 字段。

---

## 二、日志级别使用场景

| 级别 | 场景 | 示例 |
|------|------|------|
| `error` | 系统异常，需要人工介入 | `log.error("支付回调失败 orderId={}", orderId, e)` |
| `warn` | 业务异常已被拦截，需记录留痕 | `log.warn("订单已过期 orderId={}", orderId)` |
| `info` | 关键业务流程节点、启动完成 | `log.info("创建订单成功 orderId={}", orderId)` |
| `debug` | 开发调试、SQL 参数、服务调用详情 | 本地开发开启，生产关闭 |

---

## 三、链路追踪 TraceId

微服务模式下通过 Micrometer Tracing（Spring Boot 3 内置）自动注入 TraceId：

```yaml
# application.yml
management:
  tracing:
    sampling:
      probability: 1.0
```

日志输出自动带 `[traceId, spanId]`，无需手动拼接。

**注意：** 如果单体项目暂时不需要链路追踪，不强制引入。

---

## 四、Controller 请求日志

用 Filter 或 AOP 统一记录请求日志，**不在每个 Controller 方法内手写**：

```java
@Slf4j
@Component
public class RequestLogFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        long start = System.currentTimeMillis();
        chain.doFilter(request, response);
        long elapsed = System.currentTimeMillis() - start;

        log.info("{} {} {} {}ms",
            request.getMethod(), request.getRequestURI(),
            response.getStatus(), elapsed);
    }
}
```

Controller 方法内禁止写无意义日志：

```java
// ❌ 禁止
@GetMapping
public Result<UserVO> get(@PathVariable Long id) {
    log.info("收到查询用户请求 id={}", id);  // Filter 已经记了
    ...
}
```

---

## 五、Service 日志

只记录关键业务节点，有明确排查价值：

```java
// ✅ 有意义
log.info("创建订单成功 orderId={}, userId={}", order.getId(), userId);
log.warn("订单已过期 orderId={}", orderId);
log.error("支付回调处理失败 tradeNo={}", tradeNo, e);

// ❌ 无意义
log.info("开始创建用户");
log.info("用户创建完成");
```

---

## 六、日志格式

使用 Spring Boot 默认日志格式，不做自定义配置。

---

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| `System.out.println()` / `System.err.println()` | 不走日志框架，无法分级、无法格式化 |
| 打印密码、手机号、Token、身份证等敏感信息 | 安全合规，日志不可泄露隐私 |
| `log.info("user:{}", user.toString())` 打印完整对象 | 日志膨胀，只打关键字段 |
| 循环内大量 `log.info` | 刷日志影响性能 |
| Controller 方法内手写请求日志 | 由 Filter 统一拦截 |
| 吞异常不打日志 | `catch` 后必须记录或向上抛 |

---

## 八、环境级别配置

```yaml
# application-dev.yml
logging:
  level:
    com.chenyi: debug
    com.chenyi.{project}.mapper: debug     # SQL 日志

# application-prod.yml
logging:
  level:
    com.chenyi: info                        # 生产关闭 debug
```

---

## 九、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../layered/service-guide.md` | Service 日志写法 |
| `../quality/error-code-reference.md` | GlobalExceptionHandler 中已统一 `log.error` 和 `log.warn` |
