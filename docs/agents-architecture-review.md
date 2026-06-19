# Agents 文件夹架构审查报告

> 审查日期：2026-06-04
> 审查范围：`agents/` 目录全量文件（coder 20 个规范 + reviewer 4 个审查文件）

---

## 一、当前架构总览

```
agents/
├── coder/                         # 规范定义层（6 个子目录，20 个规范文件）
│   ├── README.md                  # 任务导向的索引入口
│   ├── architecture/              # 2 个文件：包结构、微服务架构
│   ├── layered/                   # 3 个文件：Controller、Service、Mapper
│   ├── infrastructure/            # 5 个文件：Result、Swagger、Config、Logging、Redis
│   ├── auth/                      # 6 个文件：overview → basic → multi-end/system/sso/oauth2
│   └── quality/                   # 5 个文件：代码风格、JSR303、i18n、错误码、数据库
│
└── reviewer/                      # 审查执行层（4 个文件，平铺）
    ├── README.md                  # 流程索引 + 审查原则
    ├── structure-check.md         # 映射 coder 的 architecture + layered + quality(code-style)
    ├── quality-check.md           # 映射 coder 的 quality + infrastructure + layered
    ├── auth-check.md              # 映射 coder 的 auth + layered(service)
    └── infra-check.md             # 映射 coder 的 infrastructure + quality(i18n)
```

---

## 二、优点

| # | 优点 | 说明 |
|---|------|------|
| 1 | **双层分离清晰** | coder（规范定义）和 reviewer（审查执行）职责分离，各自独立演进 |
| 2 | **审查可追溯** | reviewer 每条检查项都精确引用到 coder 的规范文件+章节，如 `../coder/auth/auth-basic.md #八` |
| 3 | **coder README 任务导向** | 按「新建项目」「写 Controller」「写 Service」等实际任务组织读取路径，对 AI Agent 友好 |
| 4 | **三级严重度分级** | P0/P1/P2 设计合理，P0=阻断（安全/编译），P1=重要（规范违反），P2=建议（风格） |
| 5 | **auth 规范渐进式** | auth-overview → auth-basic → multi-end/system/sso/oauth2 的递进结构，按复杂度逐步加载 |
| 6 | **上下文感知审查** | reviewer auth-check 能判断「纯后台管理」vs「多端场景」，自适应调整检查项 |
| 7 | **全局规则速查** | coder README 底部有「全局规则速查」，覆盖最常用的 10 条规则，减少读取成本 |
| 8 | **交叉引用网络** | 每个规范文件底部有「相关文件」表，清晰展示文件间关联关系 |

---

## 三、缺陷：审查覆盖度不足

### 3.1 coder 中的「禁止事项」大量未被 reviewer 检查 🔴

每个 coder 规范文件末尾都有 `禁止事项` 表，但 reviewer 并未全覆盖。以下是**遗漏的检查项**：

| coder 文件 | 被遗漏的禁止项 | 风险 |
|---|---|---|
| `service-guide.md` | 循环内逐条查数据库 | P1 性能问题 |
| `service-guide.md` | Service 方法返回 Entity 给 Controller | P1 分层穿透 |
| `mapper-guide.md` | Mapper 方法参数不加 `@Param` | P1 XML 引用失败 |
| `mapper-guide.md` | 字符串字段名构建条件 `new QueryWrapper<UserEntity>().eq("username", name)` | P1 编译期不检查 |
| `mapper-guide.md` | JPA 双向关联 `@Data` 导致循环引用 StackOverflow | P1 运行时崩溃 |
| `code-style-guide.md` | 魔法数字 `if (status == 1)` | P2 可读性 |
| `code-style-guide.md` | `System.gc()` / `Runtime.gc()` | P2 |
| `code-style-guide.md` | `finalize()` 方法 | P2 |
| `database-guide.md` | 字段用 `NULL` 不加 `NOT NULL` | P2 查询需额外判空 |
| `database-guide.md` | 表不加 `COMMENT` | P2 |

**统计：约 30% 的 coder 禁止事项在 reviewer 中无对应检查。**

### 3.2 微服务特有规范的审查几乎空白 🔴

`microservice-architecture-guide.md` 定义了完整的微服务架构规范（7 章），但 reviewer 仅检查了其中 2 项（Swagger 聚合、Nacos 配置）。以下微服务规范**完全没有审查覆盖**：

| 微服务规范章节 | 内容 | 是否被审查 |
|---|---|---|
| 二、common 模块规范 | common-result/exception/enums 职责划分 | ❌ |
| 三、api 契约层规范 | DTO/VO 放置规则、HttpExchange 接口定义 | ❌ |
| 四.1 | 跨服务 DTO 放 api 模块 vs 内部 DTO 放 business 模块 | ❌ |
| 五 | 服务调用链正确性 | ❌ |
| 六 | Dockerfile 放置 | ❌ |
| 七 | 模块依赖关系、禁止循环依赖 | ❌ |

**结论：微服务规范有约 70% 的内容处于「写了但没人查」的状态。**

### 3.3 Service 层方法命名约定无审查 🟡

`service-guide.md` 第 5 节定义了详细的方法命名约定（`getById`、`create`、`page`、`list` 等），但 reviewer 没有任何检查项验证 Service 方法是否符合命名约定。structure-check 的命名检查只覆盖了类名（Controller/Service/Mapper 后缀），未覆盖方法名。

### 3.4 Mapper 枚举字段映射无审查 🟡

`mapper-guide.md` 第 5 节定义了枚举字段映射规范（`@EnumValue`、`MybatisEnumTypeHandler`），但 reviewer 中没有对应检查。AI 可能写出裸 `Integer` 类型的状态字段而未被告知。

---

## 四、缺陷：结构性问题

### 4.1 交叉引用网络的维护风险 🟡

每个 coder 规范文件底部都有「相关文件」表，形成了密集的交叉引用网络。好处是关联清晰，但：

- 如果某个中间文件被重命名或删除，**6 个以上的文件需要同步更新**引用
- AI Agent 读取时可能形成循环读取（controller → service → mapper → service…）

### 4.2 reviewer 串行审查模式与修复迭代冲突 🟡

reviewer README 规定的流程是：

```
structure-check → quality-check → auth-check → infra-check
   （前一个维度通过再进入下一个）
```

这是**瀑布式审查**，但实际开发中：
- 修复 structure 问题（如把 DTO 改名）可能引入 quality 问题
- 修复 quality 问题（如改变异常处理方式）可能影响 auth 逻辑
- 串行意味着修复一次就要重跑整个审查链，效率低

**更合理的方式是并行审查 + 汇总修复 + 最终复检。**

### 4.3 认证规范的「分岔路口」逻辑过于复杂 🟡

`auth-basic.md` 在一个文件中同时服务「纯后台管理」和「多端多系统」两种完全不同的场景，通过「分岔路口」章节区分跳读路径。这导致：

- 文件前半部分（StpKit、LoginContextHolder）对纯后台管理项目是噪音
- `auth-check.md` 的审查逻辑也需要到处判断「如果是纯后台管理则跳过」
- 两套逻辑耦合在一个文件中，新人容易读错路径

**更好的做法：拆成 `auth-basic-simple.md` 和 `auth-basic-multi.md` 两个独立文件。**

### 4.4 reviewer 内部检查项缺乏优先级排序 🟡

每个 reviewer 文件内部的检查项是**平铺表格**，没有推荐执行顺序。但实际上：

- 先检查「Controller 是否直接注入 Mapper」比先检查「常量是否 UPPER_SNAKE」更重要
- 同一次审查中，某些检查项可以作为其他检查的前置条件

### 4.5 infrastructure/ 和 quality/ 的分类边界模糊

| 有争议的文件 | 当前位置 | 实际语义 | 建议 |
|---|---|---|---|
| `logging-guide.md` | infrastructure/ | 「日志怎么写」本质是代码质量问题 | 保持现状，在 README 中明确分类原则 |
| `database-guide.md` | quality/ | 建表规范更接近基础设施 | 同上 |
| `result-guide.md` | infrastructure/ | 与 Controller 返回紧密相关 | 同上 |

---

## 五、缺陷：缺失的规范领域

### 5.1 Spring 常用特性规范缺失 🔴

当前规范基于项目实战经验覆盖了核心场景，但以下 Spring Boot 常用特性完全没有规范：

| 特性 | 典型问题（无规范约束时 AI 容易写出） | 建议优先级 |
|---|---|---|
| `@Async` 异步 | 未配置线程池直接用默认，OOM | P1 |
| `@Scheduled` 定时任务 | 未加锁导致多实例重复执行 | P1 |
| `@Cacheable` 缓存 | 缓存穿透、缓存雪崩无防护 | P1 |
| 文件上传/下载 | 未限制大小、未校验类型，安全漏洞 | P0 |
| 消息队列（RocketMQ/Kafka） | 消费幂等、死信队列 | P1 |
| 分布式事务（Seata） | 与 @Transactional 混用问题 | P2 |
| WebSocket | 连接管理、心跳、认证 | P2 |

### 5.2 安全性专项规范缺失 🔴

当前 auth/ 只覆盖了认证授权（SaToken），但安全不止于此：

| 安全领域 | 当前覆盖 | 缺失 |
|---|---|---|
| XSS 防护 | ❌ | 输入输出编码 |
| CSRF 防护 | ❌ | 仅靠 SaToken JWT 不够 |
| SQL 注入 | ❌ | MyBatis `#{}` / `${}` 规则 |
| SSRF | ❌ | HttpExchange 调用外部 URL 校验 |
| CORS 配置 | ❌ | Gateway 跨域配置 |
| 限流 | 仅在 Redis 中提了一句 | 无完整规范 |

---

## 六、缺陷：可用性问题

### 6.1 无参考实现项目 🟡

整个 agents/ 是「规范」，但没有一个配套的 Demo 项目展示「遵守全部规范后代码长什么样」。AI Agent 纯粹靠文字理解规范，缺乏正例参考。

**后果：不同 AI Agent 对同一规范的理解可能产生偏差（如对「复杂查询走 XML」的边界判断）。**

### 6.2 规范文件无版本标识 🟡

任意打开一个规范文件，无法知道：
- 这是最新版还是旧版？
- 谁最后修改的？
- 修改了什么？

如果团队有 3 人维护规范，冲突和覆盖会不可追踪。

**建议：在规范文件头部加元信息块：**
```markdown
> 版本: 1.0 | 更新: 2026-06-04 | 作者: xxx
```

### 6.3 .DS_Store 污染仓库 🟢

macOS 系统文件被 Git 追踪（`agents/.DS_Store`、`agents/coder/.DS_Store`），`.gitignore` 中未配置。

---

## 七、缺陷：CLAUDE.md 引用不存在的目录

`CLAUDE.md` 原先引用 `agents/analyst/README.md` 作为阶段 1，但该目录不存在。（已在初次修复中标注为「未来规划：待建设」。）

---

## 八、改进优先级汇总

### P0 — 必须修复

| # | 问题 | 影响 |
|---|------|------|
| 1 | ~~CLAUDE.md 引用不存在的 analyst 目录~~ | ✅ 已修复 |
| 2 | 30% 的 coder 禁止事项无 reviewer 检查 | 代码可能违反规范但审查通过 |
| 3 | 缺少文件上传安全规范 | 安全漏洞 |

### P1 — 强烈建议修复

| # | 问题 | 影响 |
|---|------|------|
| 4 | 微服务 70% 规范无审查覆盖 | 微服务项目质量无保障 |
| 5 | 缺失 @Async / @Scheduled / @Cacheable 规范 | AI 写出有隐患的代码 |
| 6 | 缺失 XSS / SQL注入 / SSRF 安全规范 | 安全风险 |
| 7 | coder 交叉引用维护成本高 | 文件重命名时多处断裂 |

### P2 — 改善性修复

| # | 问题 | 影响 |
|---|------|------|
| 8 | ~~coder README 缺少 infrastructure/quality 分类说明~~ | ✅ 已修复 |
| 9 | ~~reviewer README 缺少分层维度快速索引~~ | ✅ 已修复 |
| 10 | reviewer 串行审查模式效率低 | 迭代修复时需反复重跑 |
| 11 | auth-basic.md 分岔逻辑复杂 | 新人阅读困难 |
| 12 | reviewer 内部检查项无优先级排序 | 审查效率 |
| 13 | 无参考实现项目 | AI 理解偏差 |
| 14 | 规范文件无版本标识 | 团队协作冲突 |
| 15 | .DS_Store 污染仓库 | 仓库整洁度 |

---

## 九、总结矩阵

| 维度 | 评分 | 关键问题 |
|------|:--:|------|
| coder 规范完整性 | ⭐⭐⭐ | 缺异步/定时/缓存/文件上传等规范 |
| reviewer 覆盖度 | ⭐⭐ | **30% 禁止项无审查**，微服务 70% 无审查 |
| coder↔reviewer 映射精确性 | ⭐⭐⭐⭐ | 大部分映射精确，但存在盲区 |
| 微服务覆盖 | ⭐⭐ | coder 详细但 reviewer 几乎未覆盖 |
| 安全性覆盖 | ⭐⭐ | 只有认证授权，缺 XSS/SQL注入/SSRF 等 |
| 可用性（AI 友好度） | ⭐⭐⭐ | 无参考实现，无版本管理 |
| 可维护性 | ⭐⭐⭐ | 交叉引用多，auth 分岔逻辑复杂 |

---

## 十、建议修复路线图

```
第 1 批（补齐覆盖）:
  ├── 补齐 reviewer 对 coder 禁止事项的覆盖（目标：覆盖度 > 95%）
  ├── 补齐微服务规范的审查覆盖（架构/API契约/模块依赖）
  └── 新增文件上传安全规范

第 2 批（补齐缺失领域）:
  ├── 新增 Spring 常用特性规范（@Async / @Scheduled / @Cacheable）
  └── 新增安全专项规范（XSS / SQL注入 / SSRF / 限流）

第 3 批（改善可用性）:
  ├── 规范文件加版本标识
  ├── reviewer 内部检查项加优先级排序
  ├── auth-basic.md 拆分为 simple + multi
  └── 创建配套参考实现项目

第 4 批（工程化）:
  ├── 配置 .gitignore 排除 .DS_Store
  └── reviewer 引入并行审查模式
```
