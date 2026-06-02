# 错误码完整参考

> 所有业务异常必须先新增枚举值再使用。新增枚举后必须同步添加国际化资源（见 i18n-guide.md）。

---

## 完整 BusinessErrorEnum 定义

```java
package com.chenyi.{project}.enums;

import lombok.Getter;

public enum BusinessErrorEnum {
    // ============ 用户模块 40001-40099 ============
    USER_NOT_FOUND(40001, "用户不存在"),
    USERNAME_DUPLICATE(40002, "用户名已存在"),
    PASSWORD_ERROR(40003, "密码错误"),
    USER_DISABLED(40004, "用户已被禁用"),

    // ============ 权限模块 40100-40199 ============
    PERMISSION_DENIED(40100, "权限不足"),
    TOKEN_EXPIRED(40101, "登录已过期"),
    TOKEN_INVALID(40102, "无效的登录凭证"),

    // ============ 文件模块 40200-40299 ============
    FILE_NOT_FOUND(40200, "文件不存在"),
    FILE_SIZE_EXCEED(40201, "文件大小超出限制"),
    FILE_FORMAT_UNSUPPORTED(40202, "不支持的文件格式"),

    // ============ 通用模块 50000-50099 ============
    SYSTEM_ERROR(50000, "系统内部错误"),
    PARAM_ERROR(50001, "参数错误");

    @Getter
    private final int code;               // 国际化 key + 接口错误码
    @Getter
    private final String defaultMessage;  // 中文兜底

    BusinessErrorEnum(int code, String defaultMessage) {
        this.code = code;
        this.defaultMessage = defaultMessage;
    }
}
```

---

## 错误码号段分配

| 号段 | 模块 |
|------|------|
| 40001 - 40099 | 用户模块 |
| 40100 - 40199 | 权限/认证模块 |
| 40200 - 40299 | 文件模块 |
| 40300 - 40399 | 订单模块 |
| 40400 - 40499 | 商品模块 |
| 50000 - 50099 | 通用/系统模块 |

**新增模块时**到此表登记号段，避免冲突。

---

## GlobalExceptionHandler 完整示例

> `Result<T>` 来自 `common-result`，完整定义见 `../infrastructure/result-guide.md`。

```java
package com.chenyi.{project}.common;

import com.chenyi.common.result.Result;
import com.chenyi.{project}.enums.BusinessErrorEnum;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.MessageSource;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.http.HttpStatus;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    private final MessageSource messageSource;

    public GlobalExceptionHandler(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    // JSR 303 校验异常
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleValidation(MethodArgumentNotValidException e) {
        FieldError fieldError = e.getBindingResult().getFieldError();
        String message = fieldError != null ? fieldError.getDefaultMessage() : "参数校验失败";
        return Result.error(400, message);  // 400 为 HTTP 状态码，JSR 303 校验统一用此码，不属于业务错误码号段
    }

    // 业务异常
    @ExceptionHandler(BusinessException.class)
    public Result<Void> handleBusiness(BusinessException e) {
        BusinessErrorEnum error = e.getError();
        String message = messageSource.getMessage(
            String.valueOf(error.getCode()),
            null,
            error.getDefaultMessage(),
            LocaleContextHolder.getLocale()
        );
        log.warn("业务异常 code={}, message={}", error.getCode(), message);
        return Result.error(error.getCode(), message);
    }

    // 系统异常兜底
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Result<Void> handleSystem(Exception e) {
        log.error("系统异常", e);
        return Result.error(50000, "系统内部错误");
    }
}
```
