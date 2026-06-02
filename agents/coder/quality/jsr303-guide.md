# JSR 303 参数校验规范

> 适用：Spring Boot + JSR 303 Bean Validation，所有接收 DTO 的 Controller 方法

---

## 一、分组接口定义

放在 `com.chenyi.{project}.common` 或 `com.chenyi.{project}.enums`：

```java
public interface Create {}
public interface Update {}
public interface Delete {}
```

| 分组 | 适用场景 |
|------|---------|
| `Create` | 新增接口 |
| `Update` | 修改接口 |
| `Delete` | 删除接口 |

Controller 使用 `@Validated(XXX.class)` 激活对应分组。

---

## 二、Controller 写法

```java
@PostMapping
public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) { ... }

@PutMapping("/{id}")
public Result<Void> update(@PathVariable Long id,
                           @RequestBody @Validated(Update.class) UserUpdateDTO dto) { ... }
```

每个接收 DTO 的方法必须加 `@Validated` 或 `@Valid` 注解，否则 DTO 内的校验注解（`@NotNull`、`@Size` 等）不生效。

---

## 三、DTO 校验注解

```java
public class UserCreateDTO {
    @NotNull(message = "{user.username.notnull}", groups = Create.class)
    private String username;

    @Size(min = 6, max = 20, message = "{user.password.size}", groups = Create.class)
    private String password;
}
```

校验消息使用 `{key}` 占位符，由 `ValidationMessages.properties` 提供国际化文本。

---

## 四、国际化资源文件

JSR 303 校验使用独立的 `ValidationMessages.properties`，与业务异常的 `messages.properties` 分开管理：

```
src/main/resources/
├── ValidationMessages.properties         # 兜底 → 中文
├── ValidationMessages_zh_CN.properties   # 中文
└── ValidationMessages_en_US.properties   # 英文
```

```properties
# ValidationMessages_zh_CN.properties
user.username.notnull=用户名不能为空
user.password.size=密码长度需在6-20位之间
```

```properties
# ValidationMessages_en_US.properties
user.username.notnull=Username must not be null
user.password.size=Password must be between 6 and 20 characters
```

---

## 五、处理方式

JSR 303 校验失败时抛出 `MethodArgumentNotValidException`，其 `getDefaultMessage()` 返回的已经是国际化后的文本——Spring 自动根据请求头的 `Accept-Language` 切换 `ValidationMessages.properties`。

**完整的 `GlobalExceptionHandler` 模板（含 JSR 303 异常、业务异常、系统异常的完整处理）→** `error-code-reference.md`

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| Controller 方法不加 `@Validated` | DTO 内的校验注解不生效，无效校验 |
| 校验消息硬编码中文 | 不支持国际化，改用 `{key}` 占位符 |
| JSR 303 和业务异常混用同一套资源文件 | 两条体系独立，见 `i18n-guide.md` |

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../layered/controller-guide.md` | `@Validated` 在 Controller 中的使用位置 |
| `i18n-guide.md` | 两条国际化体系的设计原则，业务异常国际化 |
| `error-code-reference.md` | GlobalExceptionHandler 中 JSR 303 异常的统一拦截 |
