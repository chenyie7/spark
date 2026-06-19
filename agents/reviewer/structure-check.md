# 结构审查

> 审查代码的骨架是否正确：包结构、分层调用、DTO/VO/Entity 放置、命名约定、依赖注入

---

## 一、包结构

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-ST-01 | 包结构 | 包结构是否为 `controller/service/impl/mapper/entity/dto/vo/config` | P1 | "{pkg} 不符合包结构规范，缺少标准子包" | `../coder/architecture/package-structure-guide.md #一` |
| BE-ST-02 | 包结构 | `service/` 下是否有 `impl/` 子包，实现类是否放在 `impl/` 中 | P1 | "{pkg} 缺少 service/impl 子包" | `../coder/architecture/package-structure-guide.md #二` |
| BE-ST-03 | 包结构 | 启动类是否放在根包 `com.chenyi.{project}` 下 | P2 | "{class} 启动类应放在根包下" | `../coder/architecture/package-structure-guide.md #一` |

---

## 二、分层调用

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-ST-04 | 分层调用 | Controller 是否直接注入 Mapper | P0 | "{class} 直接注入了 Mapper，应通过 Service 调用" | `../coder/architecture/package-structure-guide.md #三.3` |
| BE-ST-05 | 分层调用 | Service 是否只有实现类没有接口 | P1 | "{class} 缺少 Service 接口，AOP 代理将失效" | `../coder/layered/service-guide.md #一` |
| BE-ST-06 | 分层调用 | Service Impl 中是否有业务逻辑写在 Controller 层 | P2 | "{method} 的业务逻辑应下沉到 Service 层" | `../coder/layered/controller-guide.md #六` |
| BE-ST-07 | 分层调用 | Service 方法是否返回 Entity 给 Controller | P1 | "{method} 返回了 Entity，应转换为 VO 后返回" | `../coder/layered/service-guide.md #六` |

---

## 三、DTO / VO / Entity 放置

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-ST-08 | DTO/VO/Entity | Entity 是否直接返回给 Controller | P1 | "{method} 返回了 Entity，应转换为 VO" | `../coder/architecture/package-structure-guide.md #三.4` |
| BE-ST-09 | DTO/VO/Entity | DTO 是否被用作 Mapper 参数 | P1 | "{method} 将 DTO 传入了 Mapper，应转换为 Entity" | `../coder/architecture/package-structure-guide.md #三.4` |
| BE-ST-10 | DTO/VO/Entity | Controller 参数 > 3 个是否收敛到 DTO + POST | P2 | "{method} 参数超过 3 个，应收敛到 DTO" | `../coder/layered/controller-guide.md #三.1` |
| BE-ST-11 | DTO/VO/Entity | GET 请求是否使用了 DTO 或 `@RequestBody` | P1 | "{method} GET 请求使用了 DTO/RequestBody，应改用 @RequestParam" | `../coder/layered/controller-guide.md #三.3` |
| BE-ST-12 | DTO/VO/Entity | DTO 作为 `@RequestBody` 入参时是否加了 `@NoArgsConstructor` | P1 | "{class} 缺少 @NoArgsConstructor，Jackson 反序列化将失败" | `../coder/quality/code-style-guide.md #一.1` |
| BE-ST-13 | DTO/VO/Entity | 微服务模式下，跨服务契约 DTO/VO 是否放在 api 模块 | P1 | "{class} 跨服务 DTO/VO 应放在 api 模块" | `../coder/architecture/microservice-architecture-guide.md #四.1` |

---

## 四、命名约定

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-ST-14 | 命名 | Controller 类名是否以 `Controller` 结尾 | P2 | "{class} 不符合 Controller 命名规范" | `../coder/architecture/package-structure-guide.md #四.1` |
| BE-ST-15 | 命名 | Service 接口是否以 `Service` 结尾 | P2 | "{class} 不符合 Service 接口命名规范" | `../coder/architecture/package-structure-guide.md #四.2` |
| BE-ST-16 | 命名 | ServiceImpl 类名是否以 `ServiceImpl` 结尾 | P2 | "{class} 不符合 ServiceImpl 命名规范" | `../coder/architecture/package-structure-guide.md #四.2` |
| BE-ST-17 | 命名 | Mapper 类名是否以 `Mapper` 结尾 | P2 | "{class} 不符合 Mapper 命名规范" | `../coder/architecture/package-structure-guide.md #四.3` |
| BE-ST-18 | 命名 | Entity 类名是否以 `Entity` 结尾 | P2 | "{class} 不符合 Entity 命名规范" | `../coder/quality/code-style-guide.md #二` |
| BE-ST-19 | 命名 | DTO 命名是否为 `{业务名}{动作}DTO` | P2 | "{class} 不符合 DTO 命名规范" | `../coder/architecture/package-structure-guide.md #四.5` |
| BE-ST-20 | 命名 | 包名是否全部小写 | P2 | "{pkg} 包名应全部小写" | `../coder/quality/code-style-guide.md #二` |
| BE-ST-21 | 命名 | 常量命名是否用 `UPPER_SNAKE` | P2 | "{field} 常量命名应使用 UPPER_SNAKE 风格" | `../coder/quality/code-style-guide.md #二` |

---

## 五、依赖注入

| 编码 | 分类 | 检查项 | 级别 | 错误消息模板 | 规范依据 |
|------|------|--------|:--:|-------------|---------|
| BE-ST-22 | 依赖注入 | 是否使用 `@Autowired` 字段注入 | P1 | "{class} 使用了 @Autowired 字段注入，应改用构造注入" | `../coder/quality/code-style-guide.md #一.3` |
| BE-ST-23 | 依赖注入 | 是否使用 `@RequiredArgsConstructor` + `private final` 构造注入 | P1 | "{class} 应使用 @RequiredArgsConstructor + private final 构造注入" | `../coder/quality/code-style-guide.md #一.3` |
| BE-ST-24 | 依赖注入 | 构造注入参数是否 > 7 个 | P2 | "{class} 构造注入参数过多，应拆分 Service" | `../coder/quality/code-style-guide.md #一.4` |

---

## 六、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/architecture/package-structure-guide.md` | 包结构、调用链、命名约定 |
| `../coder/architecture/microservice-architecture-guide.md` | 微服务模块拆分、DTO 放置规则 |
| `../coder/layered/controller-guide.md` | Controller 参数约束、分层调用 |
| `../coder/layered/service-guide.md` | Service 接口+实现强制、Entity 禁止返回 |
| `../coder/quality/code-style-guide.md` | 构造注入、Lombok、命名约定 |
