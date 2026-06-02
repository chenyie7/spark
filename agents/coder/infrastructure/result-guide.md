# 统一 Result 返回体规范

> 所有 Controller 和 HttpExchange 接口的返回值必须使用 `Result<T>`，禁止返回裸对象或字符串。
> 
> **包路径说明：** 微服务架构中 `Result<T>`、`PageQueryDTO`、`PageResult<T>` 放在 `com.chenyi.common.result` 包（`project-common` 模块）。单体项目应改为 `com.chenyi.{project}.common.result`。

---

## 一、完整定义

```java
package com.chenyi.common.result;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Getter;

@Getter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Result<T> {

    private final int code;
    private final String message;
    private final T data;

    private Result(int code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
    }

    // ============ 成功 ============

    /** 成功（有数据） */
    public static <T> Result<T> success(T data) {
        return new Result<>(0, "ok", data);
    }

    /** 成功（无数据，如新增/修改/删除） */
    public static Result<Void> success() {
        return new Result<>(0, "ok", null);
    }

    // ============ 失败 ============

    /** 失败（自定义 code + message） */
    public static <T> Result<T> error(int code, String message) {
        return new Result<>(code, message, null);
    }

    /** 失败（枚举快捷方法） */
    public static <T> Result<T> error(BusinessErrorEnum error) {
        return new Result<>(error.getCode(), error.getDefaultMessage(), null);
    }
}
```

---

## 二、字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `int` | 0 = 成功，非 0 = 失败（对应 `BusinessErrorEnum` 中的 code） |
| `message` | `String` | 提示信息，成功时为 `"ok"`，失败时为国际化后的错误信息 |
| `data` | `T` | 业务数据，失败为 `null`，不序列化（`NON_NULL` 策略） |

---

## 三、使用方式

### 3.1 Controller 返回

```java
// 查询（有数据）
@GetMapping("/{id}")
public Result<UserVO> getUser(@PathVariable Long id) {
    UserVO user = userService.getById(id);
    return Result.success(user);
}

// 列表查询
@GetMapping
public Result<List<UserVO>> listUsers() {
    return Result.success(userService.listAll());
}

// 新增/修改/删除（无数据）
@PostMapping
public Result<Void> create(@Validated @RequestBody UserCreateDTO dto) {
    userService.create(dto);
    return Result.success();
}

// 业务异常由 GlobalExceptionHandler 统一拦截，无需手动构建 Result.error()
```

### 3.2 分页查询

#### 分页请求基类

所有分页查询的 DTO 必须继承 `PageQueryDTO`：

```java
package com.chenyi.common.result;

import lombok.Data;

@Data
public class PageQueryDTO {
    private int page = 1;
    private int size = 10;
}
```

```java
// 使用示例：分页查询 DTO 继承 PageQueryDTO
@Data
public class UserPageQueryDTO extends PageQueryDTO {
    private String username;
    private Integer age;
}
```

#### 分页响应

```java
// 分页查询（复杂查询用 POST + @RequestBody）
@PostMapping("/page")
public Result<PageResult<UserVO>> page(@RequestBody @Validated UserPageQueryDTO dto) {
    PageResult<UserVO> page = userService.page(dto);
    return Result.success(page);
}
```

分页封装类：

```java
package com.chenyi.common.result;

import lombok.Data;
import java.util.List;

@Data
public class PageResult<T> {
    private long total;
    private int page;
    private int size;
    private List<T> records;

    public static <T> PageResult<T> of(long total, int page, int size, List<T> records) {
        PageResult<T> result = new PageResult<>();
        result.total = total;
        result.page = page;
        result.size = size;
        result.records = records;
        return result;
    }
}
```

---

## 四、规则

### 4.1 允许的返回类型

| 场景 | 写法 | 说明 |
|------|------|------|
| 查询单条 | `Result<UserVO>` | `data` 为单个 VO 对象 |
| 查询列表 | `Result<List<UserVO>>` | `data` 为数组 |
| 分页查询 | `Result<PageResult<UserVO>>` | `data` 为分页封装对象 |
| 新增/修改/删除 | `Result<Void>` | 无 `data` |

### 4.2 禁止的返回类型

| 禁止写法 | 原因 |
|----------|------|
| `UserVO` / `String` / `boolean` / `int` | 裸返回，未用 `Result<>` 包裹，前端无法统一解析 |
| `Result<String>` | 滥用 String 拼接，应定义 VO 或使用枚举返回状态 |
| `Result<Map<String, Object>>` | 无类型约束，字段不明确，调用方不知道里面有什么 |
| `Result<JSONObject>` | 同上，应定义明确的 VO 类 |

### 4.3 其他规则

| 规则 | 说明 |
|------|------|
| 成功消息固定为 `"ok"` | 不添油加醋，不返回 `"添加成功"` 之类文本 |
| 新增/修改/删除用 `Result.success()` | 无 data，用 `Result<Void>` |
| 业务报错通过抛 `BusinessException` | 不手动 `Result.error()` |
| 失败时 data 为 null 且不序列化 | 用 `NON_NULL` 覆盖 `@JsonInclude` |

---

## 五、前端接收格式

```json
// 成功（有数据）
{"code": 0, "message": "ok", "data": {"id": 1, "username": "zhangsan"}}

// 成功（无数据）
{"code": 0, "message": "ok"}

// 失败
{"code": 40001, "message": "用户不存在"}
```

---

## 六、与其他规范的关系

- 错误码定义 → `../quality/error-code-reference.md`
- 国际化错误信息 → `../quality/i18n-guide.md`
- GlobalExceptionHandler 中使用 `Result.error()` → `../quality/error-code-reference.md`
