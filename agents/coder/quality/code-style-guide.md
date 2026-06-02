# 代码风格规范

> 适用：所有 Java 代码，无框架限制

---

## 一、Lombok 使用规范

### 1.1 允许使用的注解

| 注解 | 适用位置 | 说明 |
|------|---------|------|
| `@Data` | Entity、DTO、VO | getter/setter/toString/equals/hashCode 全包 |
| `@Slf4j` | 所有需要日志的类 | 统一日志声明 |
| `@Builder` | 构建复杂对象 | 替代链式 setter，创建不可变对象 |
| `@NoArgsConstructor` | DTO 必加 | 作为 `@RequestBody` 入参时，Jackson 反序列化需要无参构造 |
| `@AllArgsConstructor` | DTO/VO | 全字段构造 |
| `@RequiredArgsConstructor` | Service（构造注入） | 替代 `@Autowired` 字段注入 |

### 1.2 禁止使用的注解

| 注解 | 原因 |
|------|------|
| `@SneakyThrows` | 隐藏受检异常，掩盖问题 |
| `@Cleanup` | 不如 try-with-resources 直观 |
| `@Synchronized` | Lombok 自己实现的锁，不如 `synchronized` / `ReentrantLock` 明确 |
| `@ToString` 单独使用 | 可能导致循环引用 StackOverflow，用 `@Data` 自带即可 |
| `@EqualsAndHashCode` 单独使用 | 同上，特殊情况（如 JPA 双向关联）需手动排除字段 |

### 1.3 构造注入 vs 字段注入

```java
// ✅ 构造注入（@RequiredArgsConstructor）
@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {
    private final UserMapper userMapper;
    private final OrderService orderService;
}

// ❌ 禁止字段注入
@Service
public class UserServiceImpl implements UserService {
    @Autowired
    private UserMapper userMapper;   // 单测困难，依赖隐藏
}
```

**为什么构造注入更好：**

| 维度 | 构造注入 | 字段注入 `@Autowired` |
|------|---------|---------------------|
| 单测 | 直接 `new Service(mockMapper)` 一行搞定 | 必须用 `@SpringBootTest` 或反射注入 mock |
| 依赖可见性 | 构造器参数一眼看出依赖了哪些，依赖多了自然警惕 | 字段散落类中，加 10 个也不会有警告 |
| 不可变性 | `private final` — 不会被意外修改，线程安全 | 非 final，可被重新赋值 |
| 设计信号 | 构造器参数多了 → 提醒你类该拆了 | 掩盖类的臃肿，依赖膨胀无感知 |

> Spring 官方从 4.x 开始推荐构造注入。Spring Boot 3 / Spring 6 中如果只有一个构造器，连 `@Autowired` 注解都可以省略。大部分项目用 `@Autowired` 是历史惯性，不是因为它更好。

### 1.4 依赖过多时的处理

构造注入会让依赖过多的问题变得显眼——这是好事，逼着你正视设计问题。针对不同场景有以下解法：

**场景一：拆 Service（首选）**

一个 Service 注入了 6-7 个依赖，通常意味着它管了太多事情。按聚合根边界拆开：

```java
// ❌ 构造器臃肿：订单服务什么都干
@RequiredArgsConstructor
public class OrderServiceImpl implements OrderService {
    private final OrderMapper orderMapper;
    private final UserMapper userMapper;
    private final ProductMapper productMapper;
    private final PaymentMapper paymentMapper;
    private final CouponMapper couponMapper;
    private final MessageService messageService;
}

// ✅ 按职责拆：跨聚合的操作通过 Service 调用，不直接调 Mapper
@RequiredArgsConstructor
public class OrderServiceImpl implements OrderService {
    private final OrderMapper orderMapper;       // 订单自己的持久化
    private final UserService userService;       // 调用户服务接口
    private final ProductService productService; // 调商品服务接口
    private final PaymentService paymentService; // 调支付服务接口
}
```

**场景二：事件驱动解耦**

下单后发短信、扣优惠券、记积分——这些非核心流程不要堆在主事务里：

```java
// ✅ 主流程只保留核心依赖，非核心通过事件异步处理
@RequiredArgsConstructor
public class OrderServiceImpl implements OrderService {
    private final OrderMapper orderMapper;
    private final ProductService productService;    // 扣库存，核心流程
    private final ApplicationEventPublisher eventPublisher;  // Spring 自带
}

// 短信、积分、优惠券通过事件异步处理，各自的 Service 各自注入
@TransactionalEventListener
public void onOrderCreated(OrderCreatedEvent event) {
    couponService.useCoupon(event.getCouponId());
}
```

**场景三：Facade 编排层**

聚合查询场景（如后台管理汇总数据），用 Facade 专门做数据拼装，不写具体业务逻辑：

```java
// Facade 专门做编排，依赖多也合理——职责就是"拼数据"
@RequiredArgsConstructor
public class OrderQueryFacade {
    private final OrderService orderService;
    private final UserService userService;
    private final ProductService productService;
    private final PaymentService paymentService;

    public OrderDetailVO getDetail(Long orderId) {
        // 分别调各个 Service，拼装结果，无自己的业务逻辑
    }
}
```

**参数数量参考标准：**

| 参数数量 | 判断 |
|---------|------|
| 1-3 个 | 正常 |
| 4-5 个 | 审视是否有拆分空间，但可接受 |
| 6-7 个 | 大概率需要拆分 |
| 8+ 个 | 必须重构 |

> 核心原则：构造注入不会制造问题，它只是**暴露**了原本就存在的设计问题。`@Autowired` 字段注入掩盖了类的臃肿——10 个字段安安静静没人觉得不对劲。而构造器参数一长，逼着你正视"这个类是不是该拆了"。

---

## 二、命名约定

| 元素 | 风格 | 示例 |
|------|------|------|
| 类名 | UpperCamelCase | `UserService`、`BusinessErrorEnum` |
| 方法名 | lowerCamelCase | `getById()`、`create()`、`page()` |
| 变量名 | lowerCamelCase | `userName`、`orderId` |
| 常量 | UPPER_SNAKE | `MAX_RETRY_COUNT`、`DEFAULT_PAGE_SIZE` |
| 包名 | 全小写 | `com.chenyi.{project}.controller` |
| 枚举值 | UPPER_SNAKE | `USER_NOT_FOUND`、`PERMISSION_DENIED` |
| Entity 类 | `{表名驼峰}Entity` | `UserEntity`、`OrderItemEntity`，统一 `Entity` 后缀 |

---

## 三、工具类规范

```java
// ✅ 静态方法 + 私有构造 + final 类
public final class ConvertUtils {
    private ConvertUtils() {}
    public static String toSnake(String camel) { ... }
}

// ❌ 禁止：普通类命名 XXXUtils
public class XXXUtils {
    public String helper() { ... }  // 实例方法
}
```

- 工具类必须是 `final`，构造方法 `private`
- 方法全部 `static`
- 放在 `common/util` 包下

---

## 四、集合返回值

```java
// ❌ 禁止返回 null
public List<UserVO> list() {
    if (isEmpty) return null;
    ...
}

// ✅ 空集合
public List<UserVO> list() {
    if (isEmpty) return Collections.emptyList();
}
```

**所有返回集合的方法不允许返回 null**。

---

## 五、常量定义规范

### 5.1 规则

**跨文件出现 2 次及以上的字符串或数字 → 必须提取为常量**。即使目前只在 1 处使用，如果将来可能变（阈值、超时、前缀），也建议提取。

### 5.2 字符串/数字 → 用什么

| 场景 | 定义方式 | 示例 |
|------|---------|------|
| 有固定范围的状态、角色 | **枚举** | `RoleEnum.ADMIN`、`StatusEnum.ENABLED` |
| Redis Key 前缀、Token 前缀 | **常量类** | `CacheConstants.USER_TOKEN` |
| 正则表达式 | **常量类** | `RegexConstants.PHONE` |
| 默认值、阈值、超时 | **常量类** | `DEFAULT_PAGE_SIZE`、`MAX_RETRY` |
| 错误消息文本 | **BusinessErrorEnum** | 不走常量，走 `error-code-reference.md` |
| 配置 key（`app.xxx`） | **`@ConfigurationProperties`** | 见 `../infrastructure/config-guide.md` |

### 5.3 常量 vs 枚举的判断

```java
// ❌ 禁止：硬编码字符串散落代码中
if ("ADMIN".equals(user.getRole())) { ... }
if ("SUPER_ADMIN".equals(user.getRole())) { ... }

// ✅ 有固定范围 → 枚举
public enum RoleEnum {
    USER,
    ADMIN,
    SUPER_ADMIN
}

// ❌ 禁止：Redis Key 前缀散落各处
stringRedisTemplate.opsForValue().get("user:token:" + userId);

// ✅ 跨文件复用 → 常量类
stringRedisTemplate.opsForValue().get(CacheConstants.USER_TOKEN + userId);
```

### 5.4 常量类规范

```java
// ✅ final 类 + 私有构造 + static 常量
public final class CacheConstants {
    private CacheConstants() {}

    public static final String USER_TOKEN = "user:token:";
    public static final String ORDER_LOCK = "order:lock:";
    public static final String USER_CACHE = "userCache";
}
```

| 规则 | 说明 |
|------|------|
| 类声明 | `public final class`，`private` 构造器 |
| 字段 | `public static final` |
| 命名 | `UPPER_SNAKE` |
| 仅当前模块使用 | 放在该模块的 `constant/` 包下 |
| 多模块共用 | 放在 `com.chenyi.common.constant/` 包下 |

### 5.5 禁止

| 禁止 | 原因 |
|------|------|
| 硬编码字符串散落各处 | 散落难维护，改一处漏一处 |
| 有固定值的状态用字符串 `"admin"` | 应用枚举，有类型检查 |
| 常量类不 `final`、构造器不 `private` | 防止实例化 |
| 常量类互相继承 | 常量类之间无继承关系，各自独立 |

---

## 六、字符串拼接

```java
// ❌ 禁止 String.format 或 + 拼接大量字符串
String sql = "SELECT * FROM " + table + " WHERE id = " + id;

// ❌ 禁止循环内 + 拼接
for (User u : users) { s += u.getName(); }

// ✅ 少量占位用 format
String message = String.format("用户[%s]不存在", username);

// ✅ 大量拼接用 StringBuilder
StringBuilder sb = new StringBuilder();
for (User u : users) { sb.append(u.getName()).append(","); }
```

---

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| `@Autowired` 字段注入 | 见第一章，必须构造注入 |
| Lombok `@SneakyThrows` / `@Cleanup` / `@Synchronized` | 隐藏问题 |
| 集合返回 null | 调用方 NPE |
| 字符串常量代替枚举 | 散落难维护 |
| 循环内字符串 `+` 拼接 | 性能问题 |
| 魔法数字 | 如 `if (status == 1)` — 应用枚举或常量定义 |
| `System.gc()` / `Runtime.gc()` | 不可控，不该手动触发 |
| `finalize()` 方法 | JDK 已废弃 |

---

## 八、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../layered/service-guide.md` | `@RequiredArgsConstructor` 构造注入示例 |
| `../infrastructure/logging-guide.md` | `@Slf4j` 日志声明规范 |
| `../layered/mapper-guide.md` | Entity 用 `@Data`、`@TableName` |
| `../infrastructure/result-guide.md` | Result 泛型使用 |
