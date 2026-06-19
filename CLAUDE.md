# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

这是一个 Java 后端开发规范仓库，用于约束 AI 代码生成行为。规范的目标技术栈为 Spring Boot 3 + Spring Cloud 微服务。

包含三个阶段的 Agent：
1. **coder/** — 架构约束：按规范写 Java 代码
2. **reviewer/check_system/** — 双层校验：程序预检 + AI 检查清单，防止规范遗漏
3. **reviewer/** — 代码审计：多维度审查 AI 生成的代码

> 未来规划：阶段 1（analyst）—— 需求 → PRD → 技术规格 → API 设计 → 数据库设计。待建设。

## 如何使用

### 开发流程

```
阶段 1（coder）：按设计文档 + 架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 2（check_system）：双层校验 — 代码写完后的第一道防线
  入口：agents/reviewer/check_system/
  ├── Layer 1: 程序预检（Python CLI，零 AI Token，确定性匹配）
  └── Layer 2: AI 检查清单（Review Agent，逐项确认，语义理解）

阶段 3（reviewer）：多维度审查 — 可选的第二道防线
  入口：agents/reviewer/README.md
```

### 使用 CLI 进行程序预检

在编写 Java 代码完成后，在提交给 reviewer 之前运行：

```bash
# 从项目根目录运行
cd agents/reviewer/check_system && python3 -m code_check.cli scan <目标目录>

# 例如
cd agents/reviewer/check_system && python3 -m code_check.cli scan ../../../src/main/java
```

**行为：**
- 自动读取 `agents/reviewer/check_system/code-check-config.yaml` 配置
- 扫描所有 `.java` 文件，执行 9 项程序检查
- 无阻断问题 → exit 0，输出 `review-output/pre-check-result.json`
- 有阻断问题 → exit 1，输出 `review-output/pre-check-report.md`

**阻断策略**（在 `code-check-config.yaml` 中配置）：
- `strict`：有 P0 或 P1 → 阻断，Review Agent 不启动
- `normal`：有 P0 → 阻断
- `loose`：仅 P0 阻断

### 生成最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```

### 已有设计文档时

在编写任何 Java 代码前，先读取 `agents/coder/README.md`（规范索引），根据当前任务类型找到对应的规范文件，读取并遵守。

规范文件禁止修改，只读。

## 目录结构

```
agents/
├── coder/                      # 架构约束
│   ├── README.md               # 入口索引，按任务类型指引读取
│   ├── architecture/           # 架构规范（包结构、微服务项目结构）
│   ├── layered/                # 分层规范（Controller、Service、Mapper）
│   ├── infrastructure/         # 基础设施（Result、Swagger、配置、日志）
│   ├── auth/                   # 认证授权（基础→SSO→OAuth2）
│   └── quality/                # 质量规范（代码风格、国际化、错误码、数据库）
├── reviewer/                   # 代码审计
│   ├── README.md               # 审查入口，按流程执行
│   ├── structure-check.md      # 结构审查（包结构、分层调用、命名、注入）
│   ├── quality-check.md        # 质量审查（异常、日志、Result、数据库、校验）
│   ├── auth-check.md           # 认证审查（StpKit、登录、拦截器、权限）
│   ├── infra-check.md          # 基础设施审查（Swagger、配置、Redis、国际化）
│   └── check_system/           # 双层校验系统（Python CLI）
│       ├── code_check/         # Python 包
│       │   ├── models.py       # 数据模型（dataclasses + enums）
│       │   ├── config.py       # 配置加载器（PyYAML）
│       │   ├── scanner.py      # Java 文件扫描引擎（3 种扫描器）
│       │   ├── reporter.py     # 报告生成器（JSON → Markdown）
│       │   └── cli.py          # CLI 入口（argparse scan + report）
│       ├── tests/              # 65 个测试
│       ├── rules/              # 检查规则配置
│       │   ├── program-checks.yaml  # 程序检查规则（9 项确定性规则）
│       │   └── ai-checklist.yaml    # AI 检查清单（12 项语义规则）
│       ├── hooks/              # Pre/Post hook 脚本
│       └── code-check-config.yaml   # CLI 默认配置
```

## 全局规则速查

> 以下规则适用于所有代码，不读对应文件也要遵守：

- 包结构：`controller → service/impl → mapper → entity/dto/vo`
- 返回值：统一 `Result<T>`
- 注入：构造注入 `@RequiredArgsConstructor`，不用 `@Autowired` 字段注入
- 日志：`@Slf4j`，不打敏感信息
- 异常：抛 `BusinessException`，不写自由文本
- SQL：简单查 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 `@Select`
- 参数：>3 个收敛到 DTO
- URL：RESTful 复数名词，CRUD 不用动词（非 CRUD 业务动作如取消、重置允许动词）
