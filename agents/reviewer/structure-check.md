# 结构审查

> 审查代码的骨架是否正确：包结构、分层调用、命名约定、依赖注入

---

## 一、包结构

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 1.1 | 包结构是否为 `controller/service/impl/mapper/entity/dto/vo/config` | P1 | `../coder/architecture/package-structure-guide.md #一` |
| 1.2 | `service/` 下是否有 `impl/` 子包，实现类是否放在 `impl/` 中 | P1 | `../coder/architecture/package-structure-guide.md #二` |
| 1.3 | 启动类是否放在根包 `com.chenyi.{project}` 下 | P2 | `../coder/architecture/package-structure-guide.md #一` |

---

## 二、分层调用

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 2.1 | Controller 是否**直接注入** Mapper（禁止） | P0 | `../coder/architecture/package-structure-guide.md #三.3` |
| 2.2 | Service 是否只有实现类没有接口（禁止） | P1 | `../coder/layered/service-guide.md #一` |
| 2.3 | Mapper 是否被 Controller 直接调用（禁止） | P0 | `../coder/layered/controller-guide.md #六` |
| 2.4 | Service Impl 中是否有业务逻辑写在 Controller 层 | P2 | `../coder/layered/controller-guide.md #六` |

---

## 三、DTO / VO / Entity 放置

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 3.1 | Entity 是否直接返回给 Controller（禁止） | P1 | `../coder/architecture/package-structure-guide.md #三.4` |
| 3.2 | DTO 是否被用作 Mapper 参数（禁止） | P1 | `../coder/architecture/package-structure-guide.md #三.4` |
| 3.3 | Controller 参数 > 3 个是否收敛到 DTO | P2 | `../coder/layered/controller-guide.md #三.1` |
| 3.4 | GET 请求是否使用了 DTO 或 `@RequestBody`（禁止） | P1 | `../coder/layered/controller-guide.md #三.3` |
| 3.5 | DTO 作为 `@RequestBody` 入参时是否加了 `@NoArgsConstructor` | P1 | `../coder/quality/code-style-guide.md #一.1` |
| 3.6 | 微服务模式下，跨服务契约 DTO/VO 是否放在 api 模块（不在 business 模块） | P1 | `../coder/architecture/microservice-architecture-guide.md #四.1` |

---

## 四、命名约定

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 4.1 | Controller 类名是否以 `Controller` 结尾 | P2 | `../coder/architecture/package-structure-guide.md #四.1` |
| 4.2 | Service 接口是否以 `Service` 结尾，实现类是否以 `ServiceImpl` 结尾 | P2 | `../coder/architecture/package-structure-guide.md #四.2` |
| 4.3 | Mapper 类名是否以 `Mapper` 结尾 | P2 | `../coder/architecture/package-structure-guide.md #四.3` |
| 4.4 | Entity 类名是否以 `Entity` 结尾 | P2 | `../coder/quality/code-style-guide.md #二` |
| 4.5 | DTO 命名是否为 `{业务名}{动作}DTO` | P2 | `../coder/architecture/package-structure-guide.md #四.5` |
| 4.6 | 包名是否全部小写 | P2 | `../coder/quality/code-style-guide.md #二` |
| 4.7 | 常量命名是否用 `UPPER_SNAKE` | P2 | `../coder/quality/code-style-guide.md #二` |
| 4.8 | 方法名是否用 `lowerCamelCase` | P2 | `../coder/quality/code-style-guide.md #二` |

---

## 五、依赖注入

| # | 检查项 | 级别 | 规范依据 |
|---|--------|------|---------|
| 5.1 | 是否使用 `@Autowired` 字段注入（禁止） | P1 | `../coder/quality/code-style-guide.md #一.3` |
| 5.2 | 是否使用 `@RequiredArgsConstructor` + `private final` 构造注入 | P1 | `../coder/quality/code-style-guide.md #一.3` |
| 5.3 | 构造注入参数是否 > 7 个（说明需要拆分） | P2 | `../coder/quality/code-style-guide.md #一.4` |

---

## 六、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../coder/architecture/package-structure-guide.md` | 包结构、调用链、命名约定 |
| `../coder/architecture/microservice-architecture-guide.md` | 微服务模块拆分、DTO 放置规则 |
| `../coder/layered/controller-guide.md` | Controller 参数约束、分层调用 |
| `../coder/layered/service-guide.md` | Service 接口+实现强制 |
| `../coder/quality/code-style-guide.md` | 构造注入、Lombok、命名约定 |
