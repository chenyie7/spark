# workflow-agent-demo

Java 后端开发规范仓库，用于约束 AI 代码生成行为，并提供**双层校验系统**防止 AI 注意力机制导致的规范遗漏。

**目标技术栈：** Spring Boot 3 + Spring Cloud 微服务。

---

## 项目结构

```
agents/
├── coder/                              # 架构约束：按规范写 Java 代码
│   ├── README.md                       # 入口索引，按任务类型读取规范
│   ├── architecture/                   # 架构规范（包结构、微服务）
│   ├── layered/                        # 分层规范（Controller、Service、Mapper）
│   ├── infrastructure/                 # 基础设施（Result、Swagger、Config、Logging、Redis）
│   ├── auth/                           # 认证授权（SaToken 全场景方案）
│   └── quality/                        # 质量规范（代码风格、JSR303、i18n、错误码、数据库）
│
├── reviewer/                           # 代码审计 + 双层校验系统
│   ├── README.md                       # 审查入口
│   ├── structure-check.md              # 结构审查（包结构、分层、命名、注入）
│   ├── quality-check.md                # 质量审查（异常、日志、Result、数据库、校验）
│   ├── auth-check.md                   # 认证审查（StpKit、登录、权限）
│   ├── infra-check.md                  # 基础设施审查（Swagger、配置、Redis、i18n）
│   │
│   └── check_system/                   # 双层校验系统（Python CLI）
│       ├── code_check/                 # Python 包（models、config、scanner、reporter、cli）
│       ├── tests/                      # 65 个测试
│       ├── rules/                      # 检查规则配置
│       │   ├── program-checks.yaml     # 程序检查规则（确定性，9 项）
│       │   └── ai-checklist.yaml       # AI 检查清单（语义理解，12 项）
│       ├── hooks/                      # Pre/Post hook 脚本
│       └── code-check-config.yaml      # CLI 默认配置
│
docs/
├── superpowers/specs/                  # 设计文档
└── superpowers/plans/                  # 实现计划
```

> 未来规划：阶段 1（analyst）—— 需求 → PRD → 技术规格 → API 设计 → 数据库设计。

---

## 开发流程

```
阶段 1（coder）：按设计文档 + 架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 2（check_system）：双层校验
  ├── Layer 1: 程序预检（Python CLI，零 AI Token）— 确定性匹配
  └── Layer 2: AI 检查清单（Review Agent，逐项确认）— 语义理解

阶段 3（reviewer）：代码审计（可选，check_system 通过后可跳过）
  入口：agents/reviewer/README.md
```

---

## 双层校验系统

解决 AI 编码时注意力机制导致的规范遗漏（如忘记加 `@Validated`、`@Slf4j`、`Result<T>` 包裹等）。

### 工作原理

```
/review 命令
  → Pre-hook: 程序预检（Python CLI）
      ├── 阻断 → 输出 pre-check-report.md，Review Agent 不启动
      └── 通过 → 继续
  → Review Agent: AI 检查清单
      → 输出 review-result.json（纯数据，无装饰）
  → Post-hook: 报告合并
      → 输出 final-review-report.md（零 AI Token）
```

### 两层分工

| | Layer 1: 程序预检 | Layer 2: AI 检查清单 |
|---|---|---|
| 检查方式 | 正则 + 模式匹配 | AI 语义理解 |
| Token 消耗 | **0** | 含代码 + 清单模板 |
| 检查范围 | 9 项确定性规则 | 12 项语义规则 |
| 示例 | `@Validated` 缺失、`System.out` 调用 | 日志质量、异常处理正确性 |

### 阻断策略

| 策略 | 阻断条件 | 适用场景 |
|------|---------|---------|
| strict | 有 P0 或 P1 → 阻断 | 核心业务模块 |
| normal | 有 P0 → 阻断，P1/P2 放行 | 一般业务开发 |
| loose | 仅 P0 阻断 | 快速迭代 |

在 `code-check-config.yaml` 中配置。

---

## 快速开始

### 1. 安装依赖

```bash
pip3 install pyyaml
```

### 2. 配置

编辑 `agents/reviewer/check_system/code-check-config.yaml`：

```yaml
rules_dir: agents/reviewer/check_system/rules/
strategy: strict          # strict | normal | loose
output_dir: ./review-output/
format: json
exclude:
  - "**/test/**"
  - "**/target/**"
```

### 3. 运行程序预检

```bash
cd /path/to/workflow-agent-demo

# 扫描 Java 代码
python3 -m agents.reviewer.check_system.code_check.cli scan src/main/java

# 查看报告
cat review-output/pre-check-report.md
```

### 4. 生成完整报告（含 AI 检查结果）

```bash
python3 -m agents.reviewer.check_system.code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```

### 5. 运行测试

```bash
python3 -m pytest agents/reviewer/check_system/tests/ -v
```

---

## 检查项清单

### 程序检查（9 项，零 AI Token）

| 编码 | 检查内容 | 级别 |
|------|---------|:--:|
| BE-QL-29 | Controller DTO 参数是否加了 `@Validated` / `@Valid` | P1 |
| BE-QL-13 | Controller 返回值是否用 `Result<T>` 包裹 | P1 |
| BE-QL-07 | 是否使用 `System.out.println` / `System.err.println` | P1 |
| BE-QL-08 | Service/Controller 类是否加了 `@Slf4j` | P2 |
| BE-QL-33 | 是否使用了禁止的 Lombok 注解（`@SneakyThrows` 等） | P1 |
| BE-QL-40 | 是否手动声明 `Logger` 字段而未用 `@Slf4j` | P2 |
| BE-QL-42 | 是否调用了 `System.gc()` / `Runtime.gc()` | P2 |
| BE-QL-43 | 是否使用了 `finalize()` 方法 | P2 |
| BE-QL-45 | 是否用字符串字段名构建 MyBatis-Plus 条件 | P1 |

### AI 检查清单（12 项，语义理解）

| 编码 | 检查内容 | 级别 |
|------|---------|:--:|
| BE-QL-01 | 是否写了 `throw new RuntimeException("自由文本")` | P1 |
| BE-QL-02 | 业务异常是否使用 `BusinessException(BusinessErrorEnum.XXX)` | P1 |
| BE-QL-04 | Controller 方法是否包裹了 `try-catch` | P1 |
| BE-QL-05 | Service 中 catch 异常后是否只打日志不抛出 | P1 |
| BE-QL-11 | `log.info` 是否包含关键业务信息（如 orderId、userId） | P2 |
| BE-QL-12 | 循环内是否有大量 `log.info` | P2 |
| BE-QL-14 | 是否返回了裸的 String、boolean、Map | P1 |
| BE-QL-34 | 工具类是否 final + 私有构造 + 全部 static 方法 | P2 |
| BE-QL-35 | 集合返回值是否可能为 null | P1 |
| BE-QL-36 | 跨文件出现 2 次及以上的字符串/数字是否提取为常量 | P2 |
| BE-QL-37 | 有固定范围的状态/角色是否用了枚举 | P2 |
| BE-QL-41 | 是否存在魔法数字 | P2 |
| BE-QL-46 | 循环内是否逐条查数据库 | P1 |

---

## 新增检查项

1. 在 `agents/reviewer/` 对应的规范审查文件中添加一行
2. 在 `agents/reviewer/check_system/rules/program-checks.yaml`（确定性检查）或 `ai-checklist.yaml`（语义检查）中添加一条规则
3. 运行测试确认

---

## License

Internal use.
