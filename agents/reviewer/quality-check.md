# 质量审查

> 审查代码质量：异常处理、日志、Result 返回、数据库规范、参数校验、代码风格、Mapper 专项

---

## 一、异常处理

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-01 | 异常处理 | 是否写了 `throw new RuntimeException("自由文本")` | P1 | "{method} 抛出了 RuntimeException 自由文本，应使用 BusinessException" | `../coder/quality/i18n-guide.md #二` |
| BE-QL-02 | 异常处理 | 业务异常是否使用 `BusinessException(BusinessErrorEnum.XXX)` | P1 | "{method} 应使用 BusinessException(BusinessErrorEnum.XXX)" | `../coder/quality/error-code-reference.md` |
| BE-QL-03 | 异常处理 | 新增 BusinessErrorEnum 后是否同步添加了国际化资源 | P1 | "{enum} 新增后缺少对应国际化资源文件中的 key" | `../coder/quality/i18n-guide.md #二` |
| BE-QL-04 | 异常处理 | Controller 方法是否包裹了 `try-catch` | P1 | "{method} 不应手写 try-catch，由 GlobalExceptionHandler 统一拦截" | `../coder/layered/controller-guide.md #六` |
| BE-QL-05 | 异常处理 | Service 中 catch 异常后是否只打日志不抛出 | P1 | "{method} catch 后只打日志未向上抛出，上层感知不到错误" | `../coder/layered/service-guide.md #六` |
| BE-QL-06 | 异常处理 | 系统异常（NPE、IO）是否被 GlobalExceptionHandler 兜底处理 | P2 | "系统异常未被 GlobalExceptionHandler 兜底" | `../coder/quality/error-code-reference.md` |

---

## 二、日志

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-07 | 日志 | 是否使用 `System.out.println` 或 `System.err.println` | P1 | "{method} 使用 System.out/err，应使用 @Slf4j log" | `../coder/infrastructure/logging-guide.md #七` |
| BE-QL-08 | 日志 | 需要日志的类是否加了 `@Slf4j` | P2 | "{class} 缺少 @Slf4j 注解" | `../coder/infrastructure/logging-guide.md #一` |
| BE-QL-09 | 日志 | 是否打印了密码、手机号、Token、身份证等敏感信息 | P0 | "{method} 日志中包含敏感信息" | `../coder/infrastructure/logging-guide.md #七` |
| BE-QL-10 | 日志 | Controller 方法内是否手写了请求日志 | P2 | "{method} 手写了请求日志，应使用 Filter 统一拦截" | `../coder/infrastructure/logging-guide.md #四` |
| BE-QL-11 | 日志 | `log.info` 是否包含关键业务信息（如 orderId、userId） | P2 | "{method} 的 log.info 缺少关键业务信息" | `../coder/infrastructure/logging-guide.md #五` |
| BE-QL-12 | 日志 | 循环内是否有大量 `log.info` | P2 | "{method} 循环内有 log.info，影响性能" | `../coder/infrastructure/logging-guide.md #七` |

---

## 三、Result 返回体

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-13 | Result | Controller 返回值是否用 `Result<T>` 包裹 | P1 | "{method} 返回值未使用 Result<T> 包裹" | `../coder/infrastructure/result-guide.md` |
| BE-QL-14 | Result | 是否返回了裸的 `String`、`boolean`、`Map` 或 `JSONObject` | P1 | "{method} 返回了裸 {type}，应使用 Result<T> 或定义 VO" | `../coder/infrastructure/result-guide.md #四.2` |
| BE-QL-15 | Result | 新增/修改/删除是否用 `Result.success()` 无 data 返回 | P2 | "{method} 应使用 Result.success() 无 data 返回" | `../coder/infrastructure/result-guide.md #四.3` |
| BE-QL-16 | Result | 分页查询是否返回 `Result<PageResult<T>>` | P2 | "{method} 分页查询应返回 Result<PageResult<T>>" | `../coder/infrastructure/result-guide.md #三.2` |
| BE-QL-17 | Result | 分页 DTO 是否继承了 `PageQueryDTO` | P2 | "{class} 分页 DTO 应继承 PageQueryDTO" | `../coder/infrastructure/result-guide.md #三.2` |
| BE-QL-18 | Result | 成功消息是否固定为 `"ok"` | P2 | "{method} 成功消息应为 'ok'，不应返回自定义文本" | `../coder/infrastructure/result-guide.md #四.3` |

---

## 四、数据库规范

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-19 | 数据库 | 业务表是否包含必备审计字段（id/createId/createName/createTime/updateId/updateName/updateTime/deleted） | P1 | "{table} 缺少必备审计字段" | `../coder/quality/database-guide.md #一` |
| BE-QL-20 | 数据库 | 主键是否使用 `BIGINT` + 雪花ID | P1 | "{table} 主键应为 BIGINT + 雪花ID" | `../coder/quality/database-guide.md #三` |
| BE-QL-21 | 数据库 | 业务表是否加了 `deleted` 逻辑删除字段 | P1 | "{table} 缺少 deleted 逻辑删除字段" | `../coder/quality/database-guide.md #四` |
| BE-QL-22 | 数据库 | 表名/字段名是否用小写+下划线 | P1 | "{table/field} 应使用小写+下划线，禁止驼峰" | `../coder/quality/database-guide.md #五` |
| BE-QL-23 | 数据库 | 字符集是否用 `utf8mb4` | P1 | "{table} 字符集应为 utf8mb4" | `../coder/quality/database-guide.md #六` |
| BE-QL-24 | 数据库 | 引擎是否用 `InnoDB` | P2 | "{table} 引擎应为 InnoDB" | `../coder/quality/database-guide.md #六` |
| BE-QL-25 | 数据库 | 每张表是否加了 `COMMENT` | P2 | "{table} 缺少 COMMENT 注释" | `../coder/quality/database-guide.md #六` |
| BE-QL-26 | 数据库 | 数据库字段是否缺 `NOT NULL` 约束 | P2 | "{table}.{column} 应加 NOT NULL 约束" | `../coder/quality/database-guide.md #七` |
| BE-QL-27 | 数据库 | Entity 是否加了 `@TableLogic` 注解 | P1 | "{class} 缺少 @TableLogic 注解" | `../coder/quality/database-guide.md #一.3` |
| BE-QL-28 | 数据库 | 多对多中间表/日志表是否不应该加审计字段 | P2 | "{table} 中间表/日志表不应添加冗余审计字段" | `../coder/quality/database-guide.md #二` |

---

## 五、JSR 303 参数校验

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-29 | 参数校验 | 接收 DTO 的 Controller 方法是否加了 `@Validated` 或 `@Valid` | P1 | "{method} 缺少 @Validated/@Valid 注解" | `../coder/quality/jsr303-guide.md #二` |
| BE-QL-30 | 参数校验 | `@Validated` 是否指定了分组（Create/Update） | P2 | "{method} 的 @Validated 未指定分组" | `../coder/quality/jsr303-guide.md #一` |
| BE-QL-31 | 参数校验 | DTO 字段的校验消息是否用了 `{key}` 占位符 | P1 | "{class}.{field} 校验消息应使用 {key} 占位符" | `../coder/quality/jsr303-guide.md #三` |
| BE-QL-32 | 参数校验 | `@Schema.requiredMode` 是否与校验注解（@NotNull 等）保持一致 | P2 | "{class}.{field} @Schema.requiredMode 与校验注解不一致" | `../coder/infrastructure/swagger-guide.md #三.3` |

---

## 六、代码风格

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-33 | 代码风格 | 是否使用了禁止的 Lombok 注解（@SneakyThrows/@Cleanup/@Synchronized） | P1 | "{class} 使用了禁止的 Lombok 注解 {annotation}" | `../coder/quality/code-style-guide.md #一.2` |
| BE-QL-34 | 代码风格 | 工具类是否 `final` + 私有构造 + 全部 `static` 方法 | P2 | "{class} 工具类应声明为 final + 私有构造" | `../coder/quality/code-style-guide.md #三` |
| BE-QL-35 | 代码风格 | 集合返回值是否可能为 null | P1 | "{method} 集合返回值可能为 null，应返回空集合" | `../coder/quality/code-style-guide.md #四` |
| BE-QL-36 | 代码风格 | 跨文件出现 2 次及以上的字符串/数字是否提取为常量 | P2 | "{value} 出现 {count} 次，应提取为常量" | `../coder/quality/code-style-guide.md #五.1` |
| BE-QL-37 | 代码风格 | 有固定范围的状态/角色是否用了枚举而非字符串常量 | P2 | "{field} 应使用枚举替代字符串常量" | `../coder/quality/code-style-guide.md #五.2` |
| BE-QL-38 | 代码风格 | 常量类是否 `final` + 私有构造 | P2 | "{class} 常量类应声明为 final + 私有构造" | `../coder/quality/code-style-guide.md #五.4` |
| BE-QL-39 | 代码风格 | 循环内是否用 `+` 拼接字符串 | P2 | "{method} 循环内使用 + 拼接字符串，应使用 StringBuilder" | `../coder/quality/code-style-guide.md #六` |
| BE-QL-40 | 代码风格 | 是否手动声明了 `Logger` 字段而未用 `@Slf4j` | P2 | "{class} 手动声明 Logger，应使用 @Slf4j" | `../coder/infrastructure/logging-guide.md #一` |
| BE-QL-41 | 代码风格 | 是否存在魔法数字（如 `if (status == 1)` 未用枚举/常量） | P2 | "{method} 存在魔法数字，应使用枚举或常量替代" | `../coder/quality/code-style-guide.md #七` |
| BE-QL-42 | 代码风格 | 是否调用了 `System.gc()` / `Runtime.gc()` | P2 | "{method} 调用了 System.gc()，不应手动触发 GC" | `../coder/quality/code-style-guide.md #七` |
| BE-QL-43 | 代码风格 | 是否使用了 `finalize()` 方法 | P2 | "{class} 使用了 finalize()，JDK 已废弃" | `../coder/quality/code-style-guide.md #七` |

---

## 七、Mapper 专项

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-QL-44 | Mapper | Mapper 方法参数是否缺 `@Param` 注解 | P1 | "{method} 缺少 @Param 注解，XML 无法引用参数名" | `../coder/layered/mapper-guide.md #八` |
| BE-QL-45 | Mapper | 是否用字符串字段名构建条件（如 `new QueryWrapper<UserEntity>().eq("username", name)`） | P1 | "{method} 使用字符串字段名构建条件，应使用 LambdaQueryWrapper" | `../coder/layered/mapper-guide.md #八` |
| BE-QL-46 | Mapper | 循环内是否逐条查数据库 | P1 | "{method} 循环内逐条查询数据库，应使用批量方法或一次查询" | `../coder/layered/service-guide.md #六` |

---

## 八、相关文件

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
| `../coder/layered/service-guide.md` | 事务、异常抛出、禁止循环内查库 |
| `../coder/layered/mapper-guide.md` | @Param、LambdaQueryWrapper、XML |
