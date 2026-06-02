# 质量审查

> 审查代码质量：异常处理、日志、Result 返回、数据库规范、参数校验、代码风格

---

## 一、异常处理

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 1.1 | 是否写了 `throw new RuntimeException("自由文本")`（禁止） | P1 | `../coder/quality/i18n-guide.md #二` |
| 1.2 | 业务异常是否使用 `BusinessException(BusinessErrorEnum.XXX)` | P1 | `../coder/quality/error-code-reference.md` |
| 1.3 | 新增 BusinessErrorEnum 后是否同步添加了国际化资源 | P1 | `../coder/quality/i18n-guide.md #二` |
| 1.4 | Controller 方法是否包裹了 `try-catch`（禁止，由 GlobalExceptionHandler 统一拦截） | P1 | `../coder/layered/controller-guide.md #六` |
| 1.5 | Service 中 catch 异常后是否只打日志不抛出 | P1 | `../coder/layered/service-guide.md #六` |
| 1.6 | 系统异常（NPE、IO）是否被 GlobalExceptionHandler 兜底处理 | P2 | `../coder/quality/error-code-reference.md` |

---

## 二、日志

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 2.1 | 是否使用 `System.out.println` 或 `System.err.println`（禁止） | P1 | `../coder/infrastructure/logging-guide.md #七` |
| 2.2 | 需要日志的类是否加了 `@Slf4j` | P2 | `../coder/infrastructure/logging-guide.md #一` |
| 2.3 | 是否打印了密码、手机号、Token、身份证等敏感信息（禁止） | P0 | `../coder/infrastructure/logging-guide.md #七` |
| 2.4 | Controller 方法内是否手写了请求日志（禁止，由 Filter 统一拦截） | P2 | `../coder/infrastructure/logging-guide.md #四` |
| 2.5 | `log.info` 是否包含关键业务信息（如 orderId、userId）而非空泛文字 | P2 | `../coder/infrastructure/logging-guide.md #五` |
| 2.6 | 循环内是否有大量 `log.info`（禁止） | P2 | `../coder/infrastructure/logging-guide.md #七` |

---

## 三、Result 返回体

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 3.1 | Controller 返回值是否用 `Result<T>` 包裹 | P1 | `../coder/infrastructure/result-guide.md` |
| 3.2 | 是否返回了裸的 `String`、`boolean`、`Map` 或 `JSONObject`（禁止） | P1 | `../coder/infrastructure/result-guide.md #四.2` |
| 3.3 | 新增/修改/删除是否用 `Result.success()` 无 data 返回 | P2 | `../coder/infrastructure/result-guide.md #四.3` |
| 3.4 | 分页查询是否返回 `Result<PageResult<T>>` | P2 | `../coder/infrastructure/result-guide.md #三.2` |
| 3.5 | 分页 DTO 是否继承了 `PageQueryDTO` | P2 | `../coder/infrastructure/result-guide.md #三.2` |
| 3.6 | 成功消息是否固定为 `"ok"`，没有写"添加成功"之类文本 | P2 | `../coder/infrastructure/result-guide.md #四.3` |

---

## 四、数据库规范

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 4.1 | 业务表是否包含必备审计字段（id/createId/createName/createTime/updateId/updateName/updateTime/deleted） | P1 | `../coder/quality/database-guide.md #一` |
| 4.2 | 主键是否使用 `BIGINT` + 雪花ID，**禁止** `AUTO_INCREMENT` | P1 | `../coder/quality/database-guide.md #三` |
| 4.3 | 业务表是否加了 `deleted` 逻辑删除字段 | P1 | `../coder/quality/database-guide.md #四` |
| 4.4 | 表名/字段名是否用小写+下划线（禁止驼峰） | P1 | `../coder/quality/database-guide.md #五` |
| 4.5 | 字符集是否用 `utf8mb4`（禁止 `utf8`） | P1 | `../coder/quality/database-guide.md #六` |
| 4.6 | 引擎是否用 `InnoDB` | P2 | `../coder/quality/database-guide.md #六` |
| 4.7 | 每张表是否加了 `COMMENT` | P2 | `../coder/quality/database-guide.md #六` |
| 4.8 | Entity 是否加了 `@TableLogic` 注解 | P1 | `../coder/quality/database-guide.md #一.3` |
| 4.9 | 多对多中间表/日志表是否不应该加审计字段 | P2 | `../coder/quality/database-guide.md #二` |

---

## 五、JSR 303 参数校验

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 5.1 | 接收 DTO 的 Controller 方法是否加了 `@Validated` 或 `@Valid` | P1 | `../coder/quality/jsr303-guide.md #二` |
| 5.2 | `@Validated` 是否指定了分组（Create/Update） | P2 | `../coder/quality/jsr303-guide.md #一` |
| 5.3 | DTO 字段的校验消息是否用了 `{key}` 占位符，而非硬编码中文 | P1 | `../coder/quality/jsr303-guide.md #三` |
| 5.4 | `@Schema.requiredMode` 是否与校验注解（@NotNull 等）保持一致 | P2 | `../coder/infrastructure/swagger-guide.md #三.3` |

---

## 六、代码风格

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 6.1 | 是否使用了禁止的 Lombok 注解（@SneakyThrows/@Cleanup/@Synchronized） | P1 | `../coder/quality/code-style-guide.md #一.2` |
| 6.2 | 工具类是否 `final` + 私有构造 + 全部 `static` 方法 | P2 | `../coder/quality/code-style-guide.md #三` |
| 6.3 | 集合返回值是否可能为 null（禁止，应返回空集合） | P1 | `../coder/quality/code-style-guide.md #四` |
| 6.4 | 跨文件出现 2 次及以上的字符串/数字是否提取为常量 | P2 | `../coder/quality/code-style-guide.md #五.1` |
| 6.5 | 有固定范围的状态/角色是否用了枚举而非字符串常量 | P2 | `../coder/quality/code-style-guide.md #五.2` |
| 6.6 | 常量类是否 `final` + 私有构造 | P2 | `../coder/quality/code-style-guide.md #五.4` |
| 6.7 | 循环内是否用 `+` 拼接字符串（禁止） | P2 | `../coder/quality/code-style-guide.md #六` |
| 6.8 | 是否手动声明了 `Logger` 字段而未用 `@Slf4j` | P2 | `../coder/infrastructure/logging-guide.md #一` |

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/quality/error-code-reference.md` | BusinessErrorEnum、GlobalExceptionHandler |
| `../coder/quality/i18n-guide.md` | 业务异常国际化 |
| `../coder/quality/jsr303-guide.md` | JSR 303 参数校验 |
| `../coder/quality/code-style-guide.md` | Lombok、命名、常量、集合返回 |
| `../coder/quality/database-guide.md` | 建表规范、审计字段 |
| `../coder/infrastructure/result-guide.md` | Result<T>、分页返回 |
| `../coder/infrastructure/logging-guide.md` | 日志规范 |
| `../coder/layered/controller-guide.md` | Controller 禁止 try-catch |
| `../coder/layered/service-guide.md` | 事务、异常抛出 |
