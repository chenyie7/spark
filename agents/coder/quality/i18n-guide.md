# 国际化完整指南

> 适用：Spring Boot + JSR 303 + BusinessErrorEnum 双轨国际化

---

## 一、两条国际化体系

JSR 303 参数校验和业务异常使用**两套独立的国际化文件**，互不干扰：

```
src/main/resources/
├── ValidationMessages.properties         # JSR 303 兜底 → 中文
├── ValidationMessages_zh_CN.properties   # JSR 303 中文
├── ValidationMessages_en_US.properties   # JSR 303 英文
├── messages.properties                   # 业务异常兜底 → 中文
├── messages_zh_CN.properties             # 业务异常中文
└── messages_en_US.properties             # 业务异常英文
```

| 体系 | 配置文件 | 加载机制 | 独立 code |
|------|---------|---------|----------|
| JSR 303 参数校验 | `ValidationMessages.properties` | `LocalValidatorFactoryBean` 自动加载 | 不需要，统一 HTTP 400 |
| 业务异常 | `messages.properties` | Spring `MessageSource`（`spring.messages.basename` 配置） | 需要，通过 BusinessErrorEnum 定义 |

**设计原则：** JSR 303 和业务异常本质不同——一个是用户输入格式错误，一个是系统业务规则不满足。不强行统一，各管各的。

---

## 二、JSR 303 分组校验

### 分组接口定义

```java
// 放在 com.chenyi.{project}.common 或 com.chenyi.{project}.enums
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

### Controller 写法

```java
@PostMapping
public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) { ... }

@PutMapping("/{id}")
public Result<Void> update(@PathVariable Long id,
                           @RequestBody @Validated(Update.class) UserUpdateDTO dto) { ... }
```

---

## 三、JSR 303 校验 + 国际化

### DTO 写法

```java
public class UserCreateDTO {
    @NotNull(message = "{user.username.notnull}", groups = Create.class)
    private String username;

    @Size(min = 6, max = 20, message = "{user.password.size}", groups = Create.class)
    private String password;
}
```

### 国际化资源文件

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

### 处理方式

JSR 303 校验失败时，`MethodArgumentNotValidException` 中 `getDefaultMessage()` 返回的已经是国际化后的文本——Spring 自动根据请求头的 `Accept-Language` 切换了 `ValidationMessages.properties`。

**完整的 `GlobalExceptionHandler` 模板（含 JSR 303 异常、业务异常、系统异常的完整处理）→** `error-code-reference.md`

---

## 四、业务异常处理 + 国际化

### 枚举定义

```java
public enum BusinessErrorEnum {
    USER_NOT_FOUND(40001, "用户不存在"),
    USERNAME_DUPLICATE(40002, "用户名已存在"),
    PERMISSION_DENIED(40003, "权限不足");

    @Getter
    private final int code;               // 接口错误码 = 国际化 key
    @Getter
    private final String defaultMessage;  // 中文兜底
}
```

### 异常类

```java
public class BusinessException extends RuntimeException {
    private final BusinessErrorEnum error;

    // 只接收枚举，不接收自由文本
    public BusinessException(BusinessErrorEnum error) {
        super(error.getDefaultMessage());
        this.error = error;
    }
}
```

### 使用方式

```java
throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
```

### 处理流程

```
输入错误（参数格式问题）
  JSR 303 拦截 → ValidationMessages.properties → 国际化 message → code 400

业务异常（业务规则问题）
  BusinessException(BusinessErrorEnum.XXX)
    → GlobalExceptionHandler 拦截
    → 从枚举取 code
    → 通过 code 查 messages.properties
    → 取到 → 返回对应语言信息
    → 取不到 → 枚举中的中文 defaultMessage 兜底
```

### 规则

- 所有业务异常必须先新增枚举值，再使用
- 新增枚举后必须同步添加国际化资源
- **禁止**在代码中写 `throw new RuntimeException("用户不存在")` 之类自由文本
- 系统异常（NPE、IO 等）由 GlobalExceptionHandler 统一兜底

### 资源文件

```properties
# messages_zh_CN.properties
40001=用户不存在
40002=用户名已存在
40003=权限不足
```

```properties
# messages_en_US.properties
40001=User not found
40002=Username already exists
40003=Permission denied
```

---

## 五、非 HTTP 请求场景（定时任务/消息队列）

定时任务、消息队列消费者等场景中没有 HTTP 请求，无法通过请求头获取 `Locale`。此时语言来源为**数据库**。

### 用户表需包含语言偏好字段

```sql
ALTER TABLE sys_user ADD COLUMN locale VARCHAR(10) DEFAULT 'zh_CN';
```

### 使用方式

```java
// 从数据库获取用户语言偏好
UserEntity user = userService.getById(task.getUserId());
Locale locale = Locale.forLanguageTag(user.getLocale());

// 走同一套 messages.properties + BusinessErrorEnum
String message = messageSource.getMessage(
    String.valueOf(BusinessErrorEnum.ORDER_TIMEOUT.getCode()),
    null,
    BusinessErrorEnum.ORDER_TIMEOUT.getDefaultMessage(),
    locale
);
```

| 场景 | Locale 来源 | 说明 |
|------|-----------|------|
| HTTP 接口 | 请求头 `Accept-Language` | Spring 自动解析 |
| 定时任务/消息队列 | 数据库 `sys_user.locale` | 手动传入 |
| 系统内部日志 | 固定 `zh_CN` | 运维可读性 |

**核心原则：** 不管 Locale 从哪里来，底层走的是同一套 `messages.properties` + `BusinessErrorEnum`。不因为场景不同而拆出第二套国际化机制。
