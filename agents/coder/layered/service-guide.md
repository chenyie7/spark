# Service 层开发规范

> 适用：Spring Boot 单体 + Spring Cloud 微服务（各服务内部 Service 均遵循此规范）

---

## 一、接口 + 实现类强制

```java
// ✅ 必须接口 + 实现
public interface UserService {
    UserVO getById(Long id);
    void create(UserCreateDTO dto);
}

@Service
public class UserServiceImpl implements UserService {
    @Override
    public UserVO getById(Long id) { ... }
}

// ❌ 禁止只有实现类没有接口
@Service
public class UserService {
    ...
}
```

**原因**：无接口会导致 AOP 代理失效（Spring 事务切面基于 JDK/CGLIB 代理），单测 Mock 困难。

---

## 二、事务管理

### 2.1 位置

`@Transactional` **只放在 Service Impl 类或方法上**，不放在 Controller 上。

```java
@Service
public class UserServiceImpl implements UserService {

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(UserCreateDTO dto) { ... }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(Long id, UserUpdateDTO dto) { ... }
}
```

### 2.2 规则

| 规则 | 说明 |
|------|------|
| `rollbackFor = Exception.class` | 受检异常也必须回滚，Spring 默认只回滚 RuntimeException |
| 不加 `readOnly` | 不做假优化，保持简洁 |
| 不放在 Controller | Controller 只负责参数校验和调用 |

---

## 三、DTO ↔ Entity 转换

使用 `BeanUtils.copyProperties`，在 Service Impl 中完成转换：

```java
import org.springframework.beans.BeanUtils;

@Service
public class UserServiceImpl implements UserService {

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(UserCreateDTO dto) {
        UserEntity user = new UserEntity();
        BeanUtils.copyProperties(dto, user);
        userMapper.insert(user);
    }

    @Override
    public UserVO getById(Long id) {
        UserEntity user = userMapper.selectById(id);
        if (user == null) {
            throw new BusinessException(BusinessErrorEnum.USER_NOT_FOUND);
        }
        UserVO vo = new UserVO();
        BeanUtils.copyProperties(user, vo);
        return vo;
    }
}
```

**规则：**

- Controller 不感知 Entity，Entity 不穿透到 Controller 层
- 转换逻辑放在 Service Impl，不用 MapStruct

---

## 四、请求上下文的获取

### 4.1 禁止直接注入 Servlet API

```java
// ❌ 禁止：Service 直接依赖 HttpServletRequest
@Service
public class UserServiceImpl implements UserService {
    @Autowired
    private HttpServletRequest request;   // 定时任务/消息队列场景直接 NPE
}
```

### 4.2 当前用户获取：使用 SaToken

权限框架统一使用 SaToken，Service 层通过 `StpUtil` 获取当前用户信息：

```java
import cn.dev33.satoken.stp.StpUtil;

@Service
public class UserServiceImpl implements UserService {

    @Override
    public void create(UserCreateDTO dto) {
        Long currentUserId = StpUtil.getLoginIdAsLong();
        // 定时任务/非 HTTP 场景不会被自动注入，由调用方决定是否跳过或手动设置
        ...
    }
}
```

**注意：** 定时任务或消息队列等非 HTTP 场景中没有登录态，`StpUtil.getLoginId()` 会抛异常。这类场景应通过业务参数传入操作用户，不依赖 `StpUtil`。

### 4.3 国际化 Locale

Locale 由 Spring 从请求头 `Accept-Language` 自动解析（`LocaleContextHolder.getLocale()`），Service 层不需要手动获取，国际化在 `GlobalExceptionHandler` + `MessageSource` 层面完成，见 `../quality/i18n-guide.md`。

---

## 五、方法命名约定

| 操作 | 命名 |
|------|------|
| 查询单个 | `getById(Long id)` / `getByName(String name)` |
| 查询列表 | `list(UserQueryDTO dto)` |
| 分页查询 | `page(UserPageQueryDTO dto)` |
| 新增 | `create(UserCreateDTO dto)` |
| 修改 | `update(Long id, UserUpdateDTO dto)` |
| 删除 | `delete(Long id)` / `deleteBatch(List<Long> ids)` |
| 状态流转 | `cancel(Long id)` / `resetPassword(Long id)` |

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| 只有实现类没有接口 | AOP 代理失效、单测无法 Mock |
| `@Transactional` 放在 Controller | 事务管理移到不该在的层 |
| 直接注入 `HttpServletRequest`/`HttpServletResponse` | 非 HTTP 场景 NPE，见第四节 |
| catch 异常后只打日志不抛出 | 上层感知不到错误，数据不一致 |
| 循环内逐条查数据库 | 性能问题，改用批量方法 |
| Service 方法返回 Entity 给 Controller | Entity 不能穿透到 Controller 层 |

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../architecture/package-structure-guide.md` | Service 在包结构中的位置（`service/impl`） |
| `controller-guide.md` | Controller 只调 Service，不调 Mapper |
| `../infrastructure/result-guide.md` | Controller 调用 Service 后用 `Result<T>` 返回 |
| `../quality/error-code-reference.md` | Service 中抛 `BusinessException` 由 GlobalExceptionHandler 拦截 |
