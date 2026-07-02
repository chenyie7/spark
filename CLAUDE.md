# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

这是一个 Java 后端开发规范仓库，用于约束 AI 代码生成行为。规范的目标技术栈为 Spring Boot 3 + Spring Cloud 微服务。

包含四个阶段的 Agent：
1. **pm/** — 需求沟通：和用户对话澄清需求，产出 spec 设计文档和 plan 实现计划
2. **coder/** — 架构约束：按规范写 Java 代码
3. **reviewer/check_system/** — 双层校验：fuck-u-code MCP 静态分析 + AI 统一审查，防止规范遗漏
4. **reviewer/** — 代码审计：多维度审查 AI 生成的代码

## 如何使用

### 开发流程

🚀 **一键流程**：`/build <需求描述>` — 自动执行 PM（需求对话）→ Coder（代码生成）→ Reviewer（审查修复循环）
  入口：`agents/scheduler/build.skill.md`

```
阶段 1（PM）：需求沟通 → spec 设计文档 → plan 实现计划
  入口：agents/pm/pm.skill.md

阶段 2（coder）：读 spec + plan，按架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 3（reviewer）：双层审查 — coder 产出 → 审查 → 修复循环
  入口：agents/reviewer/README.md
```

### 生成最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --quality review-output/{run_id}/quality.json \
  --findings review-output/{run_id}/findings.json \
  --output review-output/{run_id}/final-review-report.md
```

### 已有设计文档时

在编写任何 Java 代码前，先读取 `agents/coder/README.md`（规范索引），根据当前任务类型找到对应的规范文件，读取并遵守。

规范文件禁止修改，只读。

## 目录结构

```
agents/
├── pm/                          # 需求沟通（PM Agent）
│   └── pm.skill.md              # /pm 斜杠命令定义
├── coder/                       # 架构约束
│   ├── README.md                # 入口索引，按任务类型指引读取
│   ├── architecture/           # 架构规范（包结构、微服务项目结构）
│   ├── layered/                # 分层规范（Controller、Service、Mapper）
│   ├── infrastructure/         # 基础设施（Result、Swagger、配置、日志）
│   ├── auth/                   # 认证授权（基础→SSO→OAuth2）
│   └── quality/                # 质量规范（代码风格、国际化、错误码、数据库）
├── reviewer/                   # 代码审计
│   ├── README.md               # 审查入口，按流程执行
│   ├── review.skill.md          # /review 斜杠命令定义
│   ├── structure-check.md      # 结构审查（包结构、分层调用、命名、注入）
│   ├── quality-check.md        # 质量审查（异常、日志、Result、数据库、校验）
│   ├── auth-check.md           # 认证审查（StpKit、登录、拦截器、权限）
│   ├── infra-check.md          # 基础设施审查（Swagger、配置、Redis、国际化）
│   └── check_system/           # 双层校验系统（Python CLI）
│       ├── code_check/         # Python 包
│       │   ├── cli.py          # CLI 入口 — report 命令
│       │   ├── models.py       # 数据模型
│       │   └── reporter.py     # 报告渲染器（JSON → Markdown）
│       ├── tests/              # 单元测试
│       └── rules/              # 检查规则配置
│           └── ai-checklist.yaml    # AI 检查清单
└── scheduler/                   # 调度器
    ├── build.skill.md           # /build 斜杠命令定义
    └── pipeline.yaml            # Coder-Reviewer 流水线 DAG 配置
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

## 会话自检

- 每次会话开始时，检查项目根目录是否存在 `.pipeline-active` 标记文件
- 如存在，读取 `review-output/.current-run` 获取 run_id：
  - 如 `pipeline-state.json` 中 status 为 `running` 或 `pending` → 提醒用户「⚠️ 有一条未完成的流水线 (run_id: {run_id})，可以 `/build --resume {run_id}` 恢复」
  - 如 status 为 `completed` 或 `error`，或状态文件不存在 → 提醒用户「`.pipeline-active` 是残留标记，建议手动删除：`rm .pipeline-active && rm -f review-output/.current-run`」
