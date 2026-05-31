# Java 开发规范索引

> **优先读取本文件**，根据任务类型跳转到对应的规范文件。不要修改任何规范文件，只能读取并遵守。

---

## 一、规范文件清单

```
architecture/                        # 架构规范
├── package-structure-guide.md       # 单体项目包结构
└── microservice-architecture-guide.md  # 微服务项目架构

layered/                             # 分层规范
├── controller-guide.md              # Controller 层
├── service-guide.md                 # Service 层
└── mapper-guide.md                  # Mapper/数据访问层

infrastructure/                      # 基础设施
├── result-guide.md                  # 统一 Result 返回体
├── swagger-guide.md                 # Swagger/Knife4j 文档
├── config-guide.md                  # 配置管理
└── logging-guide.md                 # 日志规范

quality/                             # 质量规范
├── code-style-guide.md              # 代码风格
├── i18n-guide.md                    # 国际化
└── error-code-reference.md          # 错误码参考
```

---

## 二、按任务类型读取

### 新建项目/模块

```
1. 先读 architecture/package-structure-guide.md       → 确定包结构
2. 再读 infrastructure/config-guide.md                → 配置多环境
3. 接着读 quality/code-style-guide.md                 → 命名和 Lombok 习惯
4. 微服务再读 architecture/microservice-architecture-guide.md
```

### 写 Controller 接口

```
1. 先读 layered/controller-guide.md       → URL 设计、参数约束、返回体
2. 再读 infrastructure/result-guide.md    → Result<T> 返回
3. 再读 quality/i18n-guide.md             → JSR 303 分组校验
4. 需要加文档时读 infrastructure/swagger-guide.md
```

### 写 Service 业务逻辑

```
1. 先读 layered/service-guide.md          → 事务、Bean 转换、上下文获取
2. 再读 quality/code-style-guide.md       → 构造注入、命名约定
3. 报错参考 quality/error-code-reference.md → BusinessErrorEnum
```

### 写 Mapper / 数据库访问

```
1. 先读 layered/mapper-guide.md   → SQL 写法选择、Entity 定义、分页
2. 再读 quality/code-style-guide.md → 命名约定
```

### 写异常处理 / 错误码

```
1. 先读 quality/error-code-reference.md  → 错误码号段、GlobalExceptionHandler
2. 再读 quality/i18n-guide.md            → 国际化消息同步
```

### 写日志

```
读 infrastructure/logging-guide.md → 日志级别、Filter 统一拦截、禁止事项
```

### 微服务拆分 / 服务间调用

```
1. 先读 architecture/microservice-architecture-guide.md → 项目结构、依赖关系
2. 再读 infrastructure/config-guide.md                   → Nacos 配置中心
3. 再读 infrastructure/swagger-guide.md                  → 网关文档聚合
```

---

## 三、全局规则速查

> 以下规则适用于所有代码，不读对应文件也要遵守：

- 包结构：`controller → service/impl → mapper → entity/dto/vo`
- 返回值：统一 `Result<T>`
- 注入：构造注入 `@RequiredArgsConstructor`，不用 `@Autowired` 字段注入
- 日志：`@Slf4j`，不打敏感信息
- 异常：抛 `BusinessException`，不写自由文本
- SQL：简单查 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 `@Select`
- 参数：>3 个收敛到 DTO
- URL：RESTful 复数名词，CRUD 不用动词
