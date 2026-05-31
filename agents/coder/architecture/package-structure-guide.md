# 包结构设计规范

> 适用：Spring Boot 单体项目

---

## 一、包结构总览

```
com.chenyi.{project}/
├── controller/       # 控制层
├── service/          # 服务层接口
│   └── impl/         # 服务层实现
├── mapper/           # 数据访问层（MyBatis-Plus）
├── entity/           # 数据库实体（与表一一对应）
├── dto/              # 请求入参
├── vo/               # 响应出参
├── config/           # Spring 配置类
├── common/           # 公共工具、拦截器、过滤器
├── enums/            # 枚举定义（BusinessErrorEnum 等）
└── {项目名}Application.java  # 启动类，放在根包下
```

---

## 二、各包职责

| 包 | 职责 | 关键注解 | 规则 |
|----|------|---------|------|
| `controller` | 接收请求、参数校验、调用 Service、返回 Result | `@RestController`、`@RequestMapping` | 不写业务逻辑，不直接调 Mapper |
| `service` | 业务接口定义 | — | 接口放在此包，实现放 `impl` |
| `service/impl` | 业务接口实现 | `@Service` | 必须实现 service 层接口 |
| `mapper` | 数据库访问 | `@Mapper` / `@Repository` | 只做数据访问，不写业务逻辑 |
| `entity` | 数据库表映射 | `@TableName`、`@TableId` | 一一对应数据库表，不参与接口出入参 |
| `dto` | 接口入参对象 | `@NotNull`、`@Validated` | 一个接口一个 DTO，不跨接口复用 |
| `vo` | 接口出参对象 | — | 按接口需要裁剪字段，不暴露数据库整表 |
| `config` | Spring Bean 配置 | `@Configuration` | 不做业务逻辑 |
| `common` | 公共工具、异常、拦截器 | — | 通用组件，不依赖具体业务 |
| `enums` | 枚举常量 | — | BusinessErrorEnum、状态枚举等 |

---

## 三、调用链

```
Controller → Service（接口） → Service/impl（实现） → Mapper → DB
     ↓             ↓
   DTO          Entity/VO
```

**硬约束：**

1. Controller **只能**调 Service 接口，**禁止**直接调 Mapper
2. Service 层之间**可以互相调用**，但要避免循环依赖
3. Mapper **只能**被 Service/impl 调用，**禁止**被 Controller 调用
4. DTO **不能**作为 Mapper 参数，Entity **不能**直接返回给 Controller
5. 包依赖方向：controller → service → mapper → entity，上层的 dto/vo 不向下层穿透

---

## 四、命名约定

### 4.1 Controller

```
{业务名}Controller.java

示例：UserController、OrderController
```

### 4.2 Service

```
接口：{业务名}Service.java
实现：{业务名}ServiceImpl.java

示例：UserService / UserServiceImpl
```

### 4.3 Mapper

```
{实体名}Mapper.java

示例：UserMapper
```

### 4.4 Entity

```
{表名转驼峰}.java

示例：sys_user → User，order_item → OrderItem
```

### 4.5 DTO

```
{业务名}{动作}DTO.java

示例：UserCreateDTO、UserUpdateDTO、UserPageQueryDTO
```

### 4.6 VO

```
{业务名}VO.java

示例：UserVO、UserDetailVO、UserPageVO
```

---

## 五、禁止事项

- **禁止**在 `controller` 包下写业务逻辑
- **禁止**在 `entity` 包里放 DTO 或 VO
- **禁止**在 `common` 包里放业务相关代码
- **禁止**跨层调用（Controller → Mapper 直接调用）
- **禁止**不写 Service 接口，直接在 Controller 注入实现类
