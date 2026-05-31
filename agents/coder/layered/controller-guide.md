# Controller 层开发规范

> 适用：Spring Boot 单体 + Spring Cloud 微服务（各服务内部 Controller 均遵循此规范）

---

## 一、RESTful API 语义

| 请求方式 | 语义 | 示例 |
|---------|------|------|
| `@GetMapping` | 查询 | 查单个、查列表（条件 ≤ 3 个） |
| `@PostMapping` | 新增 | 新增资源 |
| `@PutMapping` | 全量修改 | 替换整条资源 |
| `@PatchMapping` | 部分修改 | 修改部分字段（如有场景） |
| `@DeleteMapping` | 删除 | 删除资源 |

---

## 二、URL 命名约定

### 2.1 基本规则

```
GET    /api/users                # 查列表（条件 ≤ 3 个的简单筛选）
GET    /api/users/{id}           # 查单个
POST   /api/users/query          # 查列表/复杂筛选（多条件、嵌套结构）
POST   /api/users/page           # 分页查询
POST   /api/users                # 新增
PUT    /api/users/{id}           # 全量修改
DELETE /api/users/{id}           # 删除
```

- 用**复数名词**，kebab-case：`/api/order-items`
- 层级关系：`/api/users/{id}/orders`
- **CRUD 操作不用动词**在 URL 上，HTTP Method 已经表达了动作

### 2.2 业务动作允许动词

非 CRUD 的复杂业务动作（状态流转、审批、重置等）允许在 URL 使用动词：

```
POST   /api/orders/{id}/cancel            # 取消订单
POST   /api/users/{id}/reset-password     # 重置密码
POST   /api/payments/{id}/refund          # 退款
```

原则：**CRUD → RESTful，非 CRUD → 允许动词**。避免把业务动作硬塞进 PUT 修改字段里。

---

## 三、参数约束

### 3.1 入参规则

- Controller 方法参数 **≤ 3 个** → 可直接写在方法签名上（GET 的平铺参数或 POST 的 `@RequestBody` DTO）
- Controller 方法参数 **> 3 个** → 必须收敛到 DTO + 改用 POST + `@RequestBody`

```java
// ❌ 4个平铺参数，应收敛到 DTO
@GetMapping
public Result<List<UserVO>> list(String name, Integer age, String email, String phone) {
    ...
}

// ✅ 收敛到 DTO + POST + @RequestBody（DTO 必须配合 @RequestBody）
@PostMapping("/query")
public Result<List<UserVO>> query(@RequestBody @Validated UserQueryDTO dto) {
    ...
}
```

### 3.2 查询接口的请求方式

| 查询类型 | 请求方式 | 说明 |
|---------|---------|------|
| 查单个（根据 ID） | GET | `GET /api/users/{id}` |
| 简单筛选（条件 ≤ 3 个） | GET | URL 参数自动绑定，直接平铺写在方法签名上 |
| 简单筛选（条件 > 3 个） | **POST** | 收敛到 DTO + `@RequestBody` |
| **复杂查询（嵌套条件、分页、JSON 结构）** | **POST** | DTO + `@RequestBody` |

**判断标准：** 看筛选条件的**结构复杂度**和**参数数量**。

- 扁平 key=value 且 ≤ 3 个 → **GET**，参数直接平铺在方法签名上
- 扁平 key=value 但 > 3 个 → **POST** + DTO + `@RequestBody`（DTO 必须配合 `@RequestBody`）
- 条件包含嵌套对象、数组、范围区间（如 `{"price": {"min": 100, "max": 500}}`）→ **POST**，GET 无法传 JSON
- 分页查询统一用 **POST**，便于后续扩展筛选条件

```java
// ✅ 简单查询：GET + @RequestParam
@GetMapping
public Result<List<UserVO>> list(
    @RequestParam @Parameter(description = "用户名") String name,
    @RequestParam(required = false) @Parameter(description = "年龄") Integer age) { ... }

// ✅ 查单个：GET + @PathVariable
@GetMapping("/{id}")
public Result<UserVO> get(
        @Parameter(description = "用户ID", required = true) @PathVariable Long id) { ... }

// ✅ 复杂筛选/嵌套条件：POST + RequestBody
@PostMapping("/query")
public Result<List<UserVO>> query(@RequestBody @Validated UserQueryDTO dto) { ... }

// ✅ 分页查询：POST + RequestBody
@PostMapping("/page")
public Result<PageResult<UserVO>> page(@RequestBody @Validated UserPageQueryDTO dto) { ... }
```

### 3.3 DTO 传递规则

**DTO 必须配合 `@RequestBody` 使用**，禁止 GET 请求使用 DTO 参数。

| 请求方式 | 参数传递方式 |
|---------|------------|
| GET | `@RequestParam` 平铺（≤ 3 个），禁用 DTO |
| POST / PUT / PATCH | `@RequestBody` + DTO |

```java
// ✅ GET：≤ 3 个参数用 @RequestParam 平铺
@GetMapping
public Result<List<UserVO>> list(
    @RequestParam @Parameter(description = "用户名") String name,
    @RequestParam(required = false) @Parameter(description = "年龄") Integer age) { ... }

// ✅ POST：@RequestBody + DTO
@PostMapping
public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) { ... }

// ❌ 禁止：GET 使用 DTO
@GetMapping
public Result<List<UserVO>> list(@Validated UserPageQueryDTO dto) { ... }
```

---

## 四、参数校验

每个接收 DTO 的方法必须加 `@Validated` 或 `@Valid` 注解，否则 DTO 内的校验注解（`@NotNull`、`@Size` 等）不生效。

**完整校验规则（JSR 303 分组校验、国际化消息等）参考：`../quality/i18n-guide.md`**

```java
@PostMapping
public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) { ... }

@PutMapping("/{id}")
public Result<Void> update(
        @Parameter(description = "用户ID", required = true) @PathVariable Long id,
        @RequestBody @Validated(Update.class) UserUpdateDTO dto) { ... }
```

---

## 五、接口文档注解

每个 Controller 和接口需标注 Swagger/Knife4j 注解，规范定义见 `../infrastructure/swagger-guide.md`。

```java
@Tag(name = "用户管理")
@RestController
@RequestMapping("/api/users")
public class UserController {

    @Operation(summary = "根据ID查询用户")
    @GetMapping("/{id}")
    public Result<UserVO> getUser(
            @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        ...
    }
}
```

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| 在 Controller 写业务逻辑 | Controller 只负责参数校验和调用 Service |
| Controller 直接注入 Mapper | 必须经过 Service 层，见 `../architecture/package-structure-guide.md` |
| 用 `try-catch` 包裹整个方法体 | 异常由 GlobalExceptionHandler 统一拦截，见 `../quality/error-code-reference.md` |
| 返回非 `Result<>` 包裹的类型 | 见 `../infrastructure/result-guide.md` |
| GET 请求使用 DTO 或 `@RequestBody` | GET 不支持 Request Body，参数直接平铺在方法签名上（≤ 3 个） |

---

## 七、完整示例

```java
@Tag(name = "用户管理")
@RestController
@RequestMapping("/api/users")
@Slf4j
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    // 分页列表（POST，复杂查询条件用 RequestBody）
    @Operation(summary = "分页查询用户")
    @PostMapping("/page")
    public Result<PageResult<UserVO>> page(@RequestBody @Validated UserPageQueryDTO dto) {
        return Result.success(userService.page(dto));
    }

    // 查单个
    @Operation(summary = "根据ID查询用户")
    @GetMapping("/{id}")
    public Result<UserVO> get(
            @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        return Result.success(userService.getById(id));
    }

    // 新增
    @Operation(summary = "新增用户")
    @PostMapping
    public Result<Void> create(@RequestBody @Validated(Create.class) UserCreateDTO dto) {
        userService.create(dto);
        return Result.success();
    }

    // 修改
    @Operation(summary = "修改用户")
    @PutMapping("/{id}")
    public Result<Void> update(
            @Parameter(description = "用户ID", required = true) @PathVariable Long id,
            @RequestBody @Validated(Update.class) UserUpdateDTO dto) {
        userService.update(id, dto);
        return Result.success();
    }

    // 删除
    @Operation(summary = "删除用户")
    @DeleteMapping("/{id}")
    public Result<Void> delete(
            @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        userService.delete(id);
        return Result.success();
    }

    // 业务动作（允许动词）
    @Operation(summary = "重置用户密码")
    @PostMapping("/{id}/reset-password")
    public Result<Void> resetPassword(
            @Parameter(description = "用户ID", required = true) @PathVariable Long id) {
        userService.resetPassword(id);
        return Result.success();
    }
}
```

---

## 八、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../architecture/package-structure-guide.md` | Controller 在包结构中的位置 |
| `../infrastructure/result-guide.md` | 统一返回体 `Result<T>` |
| `../quality/i18n-guide.md` | `@Validated` 分组校验 + 国际化 |
| `../quality/error-code-reference.md` | GlobalExceptionHandler 统一异常拦截 |
| `../infrastructure/swagger-guide.md` | `@Tag` / `@Operation` 接口文档规范 |
