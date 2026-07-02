
<p align="center">
  <h1 align="center">AI Workflow Agent</h1>
  <p align="center">
    <strong>Java 后端代码生成与审查流水线</strong><br>
    让 AI 按规范写代码、自动审查、循环修复 — 一套约束 AI 代码生成行为的开源方案
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Java-17+-orange" alt="Java 17+">
  <img src="https://img.shields.io/badge/Spring_Boot-3.x-green" alt="Spring Boot 3">
  <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Claude_Code-Compatible-purple" alt="Claude Code">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License MIT">
</p>

---

## 目录

- [为什么需要这个项目](#为什么需要这个项目)
- [核心设计理念](#核心设计理念)
- [架构总览](#架构总览)
- [项目结构](#项目结构)
- [快速上手](#快速上手)
- [核心工作流](#核心工作流)
  - [一键流水线 `/build`](#一键流水线-build)
  - [单独审查 `/review`](#单独审查-review)
- [规范体系](#规范体系)
- [双层审查系统](#双层审查系统)
- [流水线引擎](#流水线引擎)
- [测试](#测试)
- [基准测试](#基准测试)
- [路线图](#路线图)
- [贡献指南](#贡献指南)
- [License](#license)

---

## 为什么需要这个项目

AI 代码生成工具（Claude Code、Copilot、Cursor）虽然高效，但在企业级场景中存在一个共同问题：

> **生成的代码风格不一致、规范不统一、质量不可控。**

Java 后端开发有大量细致的规范约束 — 分层架构、异常处理、日志规范、认证安全、数据库设计等 — 单次 Prompt 很难让 AI 一次性记住并遵守所有规则。

本项目的解决方案是：

**将规范从 Prompt 中解耦出来，建立一套独立于具体需求的结构化规范知识库，并通过「生成 → 审查 → 修复」的多阶段 Agent 流水线强制执行这些规范。**

### 核心价值

| 特性 | 说明 |
|------|------|
| 规范知识库 | 22 个结构化的 Markdown 规范文件，按任务类型索引，AI 按需读取 |
| 双层审查 | Layer 1 fuck-u-code MCP 静态分析（零 AI Token）+ Layer 2 AI 统一语义审查 |
| 自动修复循环 | 审查发现 P0 问题 → 自动回到 coder 修复 → 再审查，最多 3 轮 |
| 标准化输出 | JSON + Markdown 报告，可直接集成 CI/CD 流水线 |
| DAG 编排 | 通过 YAML 声明 Agent 依赖和流转规则，调度引擎自动执行 |
| 性能可观测 | 自动采集每次运行的 Token/耗时/P0 收敛数据，支持跨运行对比和异常检测 |

**适用技术栈**：Spring Boot 3 + Spring Cloud 微服务，标准分层架构（Controller → Service → Mapper → Entity/DTO/VO）。

---

## 核心设计理念

### 1. 规范即代码（Spec as Code）

规范文件与业务代码放在同一个仓库中，版本化管理。每次 AI 写代码时，先读取 `agents/coder/README.md`（规范索引），根据任务类型跳转到对应规范文件，按需加载 — 不浪费上下文窗口。

```
agents/coder/
├── README.md          # 入口索引 — 按任务类型指引 AI 读取哪些规范
├── architecture/      # 架构规范（包结构、微服务项目骨架）
├── layered/           # 分层规范（Controller、Service、Mapper）
├── infrastructure/    # 基础设施规范（Result、Swagger、配置、日志、Redis、文件上传）
├── auth/              # 认证授权规范（基础 → 多端 → SSO → OAuth2）
└── quality/           # 质量规范（代码风格、JSR303校验、国际化、错误码、数据库）
```

### 2. 双层审查防线（Defense in Depth）

```
Layer 1: fuck-u-code MCP 静态分析
  ├── 零 AI Token，~5s 完成
  ├── 7 维质量指标 + 总体评分
  └── 覆盖代码质量指标 — 复杂度、重复代码、N+1 查询等

         ↓ 通过后

Layer 2: AI 统一审查（Review Agent）
  ├── 对照 ai-checklist.yaml 逐项检查
  ├── 理解代码意图和上下文
  └── 覆盖规范合规 — 分层架构、异常处理、认证安全、日志质量
```

### 3. 流水线即 DAG

通过 YAML 定义 Agent 节点和边（依赖关系），Python 调度引擎按拓扑顺序驱动执行：

```
coder ────▶ reviewer ────▶ DONE（REVIEW_PASSED）
                │
                └──▶ coder（REVIEW_FAILED, 重试 ≤ 3 轮）
                │
                └──▶ DONE（REVIEW_ERROR）
```

### 4. 性能可观测（Performance Observability）

每次 `/build` 运行通过 Claude Code Hooks 自动采集性能数据，无需手动操作：

```
PostToolUse hook            Stop hook
(每次 Agent 调用)           (会话结束时)
    │                          │
    ▼                          ▼
dump-agent-payload.sh     synthesize-benchmark.sh
→ benchmarks/dumps/       → schema.py 合成
  session-{id}.jsonl        · run-{ts}-{slug}.json（结构化）
                            · run-{ts}-{slug}.md（可读报告）
```

采集维度包括：Token 消耗、耗时、缓存命中率、P0 收敛曲线、修复效率、模型使用统计。支持通过 `compare.py` 进行跨运行横向对比，检测规范变更对性能的影响。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户入口                                  │
│              /build <需求>          /review <路径>               │
└─────────────────────┬───────────────────────┬───────────────────┘
                      │                       │
         ┌────────────▼───────────┐  ┌────────▼──────────────────┐
         │   scheduler/           │  │   reviewer/                │
         │   pipeline_engine      │  │   review.skill.md          │
         │   (Python CLI 引擎)     │  │   (Claude Code Skill)      │
         └────────────┬───────────┘  └────────┬──────────────────┘
                      │                       │
         ┌────────────▼───────────┐  ┌────────▼──────────────────┐
         │  Coder Agent           │  │  fuck-u-code 静态分析      │
         │  读取规范 → 生成代码     │  │  → quality.json（零Token）  │
         └────────────┬───────────┘  └────────┬──────────────────┘
                      │                       │
         ┌────────────▼───────────┐  ┌────────▼──────────────────┐
         │  Reviewer Agent        │  │  AI 统一审查               │
         │  双 Layers 审查         │  │  ai-checklist.yaml         │
         └────────────┬───────────┘  └────────┬──────────────────┘
                      │                       │
         ┌────────────▼───────────┐  ┌────────▼──────────────────┐
         │  修复循环 (≤ 3轮)       │  │  合并报告                   │
         │  P0>0 → 回到 coder      │  │  final-review-report.md    │
         └────────────────────────┘  └───────────────────────────┘
                      │                       │
         ┌────────────▼───────────────────────▼───────────┐
         │  benchmarks/hooks/                              │
         │  PostToolUse → dump-agent-payload.sh            │
         │  Stop → synthesize-benchmark.sh → schema.py     │
         │  产出 run-{ts}-{slug}.json + .md                 │
         └────────────────────────────────────────────────┘
```

---

## 项目结构

```
workflow-agent-demo/
├── README.md                           # 本文件
├── CLAUDE.md                           # Claude Code 项目指令
├── BENCHMARK-REPORT.md                 # 三版本横向基准测试对比报告
├── ROOT-CAUSE-ANALYSIS.md              # 审查盲区根因分析
├── .mcp.json                           # MCP 服务器配置（fuck-u-code）
│
├── agents/
│   ├── coder/                          # 阶段 1: 编码规范库
│   │   ├── README.md                   #   规范入口索引 — AI 写代码前先读这个
│   │   ├── architecture/               #   2 个架构规范
│   │   │   ├── package-structure-guide.md       # 单体项目包结构
│   │   │   └── microservice-architecture-guide.md  # 微服务架构
│   │   ├── layered/                    #   3 个分层规范
│   │   │   ├── controller-guide.md     # Controller 层编写规范
│   │   │   ├── service-guide.md        # Service 层编写规范
│   │   │   └── mapper-guide.md         # Mapper/数据访问层规范
│   │   ├── infrastructure/             #   6 个基础设施规范
│   │   │   ├── result-guide.md         #   统一 Result<T> 返回体
│   │   │   ├── swagger-guide.md        #   Swagger/Knife4j 文档
│   │   │   ├── config-guide.md         #   多环境配置管理
│   │   │   ├── logging-guide.md        #   日志规范
│   │   │   ├── redis-guide.md          #   Redis 开发规范
│   │   │   └── file-upload-guide.md    #   文件上传/下载安全
│   │   ├── auth/                       #   6 个认证授权规范（从基础到 OAuth2）
│   │   │   ├── auth-overview.md        #   总览索引 — 选择认证方案
│   │   │   ├── auth-basic.md           #   单应用 + Sa-Token + RBAC
│   │   │   ├── auth-multi-end.md       #   多端隔离（用户端/管理端）
│   │   │   ├── auth-multi-system.md    #   多系统隔离
│   │   │   ├── auth-sso.md             #   SSO 统一认证
│   │   │   └── auth-oauth2.md          #   OAuth2 第三方登录
│   │   └── quality/                    #   5 个质量规范
│   │       ├── code-style-guide.md     #   代码风格 + 命名约定
│   │       ├── jsr303-guide.md         #   JSR 303 参数校验
│   │       ├── i18n-guide.md           #   国际化
│   │       ├── error-code-reference.md #   错误码号段定义
│   │       └── database-guide.md       #   数据库建表规范
│   │
│   ├── reviewer/                       # 阶段 2+3: 代码审查系统
│   │   ├── README.md                   #   审查系统文档
│   │   ├── review.skill.md             #   /review 斜杠命令 Skill 定义
│   │   └── check_system/               #   双层校验系统实现
│   │       ├── code_check/             #   Python 包
│   │       │   ├── cli.py              #     CLI 入口 — report 命令
│   │       │   ├── models.py           #     数据模型（SpecViolation, QualityIssue, FindingsResult）
│   │       │   └── reporter.py         #     报告渲染器（quality.json + findings.json → Markdown）
│   │       ├── rules/                  #   检查规则（YAML 格式）
│   │       │   └── ai-checklist.yaml   #     AI 检查清单（涵盖结构、质量、认证、基础设施等多维度）
│   │       └── tests/                  #   单元测试
│   │           ├── conftest.py         #     测试 fixture
│   │           ├── test_models.py      #     数据模型测试
│   │           ├── test_reporter.py    #     报告渲染测试
│   │           └── test_cli.py         #     CLI 测试
│   │
│   └── scheduler/                      # 流水线调度器
│       ├── build.skill.md              #   /build 斜杠命令 Skill 定义
│       ├── pipeline.yaml               #   DAG 配置（节点 + 边 + 流转规则）
│       ├── pipeline_engine/            #   Python 调度引擎（独立包）
│       │   ├── cli.py                  #     CLI 入口（start/next/report/status/reset）
│       │   ├── engine.py               #     核心引擎（拓扑排序 + 条件流转 + 状态持久化）
│       │   ├── config.py               #     YAML 配置加载与校验
│       │   ├── models.py               #     数据模型（PipelineState, NodeResult, NextAction）
│       │   └── reporter.py             #     报告生成
│       ├── requirements.txt            #   Python 依赖（PyYAML）
│       └── tests/                      #   单元测试（engine / config / models / cli）
│
├── benchmarks/                          # 基准测试系统
│   ├── hooks/                           #   采集与合成脚本
│   │   ├── dump-agent-payload.sh        #     PostToolUse hook：采集 Agent 性能数据到 JSONL
│   │   ├── synthesize-benchmark.sh      #     Stop hook：调用 schema.py 合成 JSON + MD 报告
│   │   ├── schema.py                    #     性能日志合成引擎（指纹/收敛/问题分布/修复质量）
│   │   └── compare.py                   #     跨运行对比工具（基线/异常检测/趋势图/变更归因）
│   ├── dumps/                           #   session JSONL 原始数据（gitignored）
│   └── run-*.json / run-*.md            #   单次运行报告（gitignored）
│
└── admin-test-01/                       # 示例项目：按规范生成的后台管理系统
    ├── pom.xml
    └── src/main/java/cn/xxx/admin/
        ├── AdminApplication.java
        ├── auth/
        │   ├── controller/AuthController.java
        │   ├── dto/AuthLoginDTO.java
        │   ├── service/AuthService.java
        │   ├── service/impl/AuthServiceImpl.java
        │   └── vo/LoginVO.java
        └── common/base/BaseEntity.java
```

---

## 快速上手

### 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行 CLI 工具和调度引擎 |
| Node.js | 18+ | 运行 fuck-u-code MCP server（可选） |
| Claude Code | 最新版 | AI Agent 运行环境 |

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/workflow-agent-demo.git
cd workflow-agent-demo

# 2. 安装 Python 依赖（调度引擎只需要 PyYAML）
pip install pyyaml

# 3. 配置 MCP（可选但推荐 — 用于 fuck-u-code 静态分析）
# 编辑 .mcp.json 或通过 Claude Code 的 MCP 配置面板添加 fuck-u-code 服务器
```

### 验证安装

```bash
# 验证调度引擎
PYTHONPATH="${PWD}/agents/scheduler" python3 -m pipeline_engine.cli status \
  --state-file /tmp/test-state.json
# 预期输出: {"error": "未找到流水线状态。"}

# 验证审查系统
cd agents/reviewer/check_system && python3 -c "from code_check.models import FindingsResult; print('OK')"
# 预期输出: OK
```

### 目录初始化

`/build` 命令会在首次运行时自动创建 `review-output/` 目录。如需手动创建：

```bash
mkdir -p review-output
```

### 三种使用方式

#### 方式一：一键流水线（推荐）

在 Claude Code 中直接使用 `/build` 命令：

```
/build 实现用户登录功能，包括用户名密码登录和验证码登录
```

流水线自动执行：**生成代码 → 审查 → 修复循环 → 输出报告**。你只需要描述需求。

#### 方式二：仅审查代码

```
/review src/main/java
```

执行：**静态分析 → AI 语义审查 → 合并报告**。

#### 方式三：CLI 生成报告

```bash
cd agents/reviewer/check_system

python3 -m code_check.cli report \
  --quality review-output/quality.json \
  --findings review-output/findings.json \
  --output review-output/final-review-report.md
```

---

## 核心工作流

### 一键流水线 `/build`

```
用户输入需求
    │
    ▼
┌─────────────────┐
│  Phase 0: 初始化  │  解析参数 → 创建 run_id → 写入 pipeline-state.json
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 1: Coder  │  读取 agents/coder/README.md（规范索引）
│  Agent           │  → 按任务类型跳转规范文件
│                  │  → 生成 Controller/Service/Mapper/Entity/DTO/VO
│                  │  → 写入 output_dir/src/main/java
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 2:        │  Layer 1: fuck-u-code MCP 静态分析
│  Reviewer Agent  │  Layer 2: AI 统一审查 → 对照 ai-checklist.yaml 逐项确认
│                  │  产出 findings.json + final-review-report.md
└────────┬────────┘
         │
    ┌────┴────────────────────────────┐
    │  REVIEW_PASSED?                  │
    ├── YES ──▶ DONE（流水线成功）   │
    │                                  │
    ├── NO, retry < 3 ──▶ 回到 Phase 1 │
    │   Coder 在「修复模式」下重新生成    │
    │   读取 review_context 定位问题     │
    │                                  │
    └── NO, retry = 3 ──▶ DONE     │
        达到最大重试次数（3 轮）         │
```

**关键特性**：
- **状态持久化**：pipeline-state.json 记录当前进度，支持 `/build --resume` 续接中断的流水线
- **并行执行**：同一轮次中的多个节点调度引擎并行发起
- **修复上下文**：coder 在修复轮次会收到前一轮的 review 结果，针对性修复
- **性能自动采集**：流水线运行期间，Hooks 自动记录每轮 Agent 的 Token/耗时/模型等数据，会话结束后合成基准测试报告

### 单独审查 `/review`

```
┌───────────────────────────────┐
│  Step 1: fuck-u-code 静态分析  │
│  MCP tool analyze 扫描源码      │
│  → quality.json                │
│  · 总体评分 (0-100)             │
│  · 7 维质量指标                 │
│  · 最差文件 Top 10              │
│  · Shit-Gas 指数               │
│  耗时 ~5s · 零 AI Token         │
│  （MCP 不可用时跳过，不阻断）    │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Step 2: AI 统一审查            │
│  输入:                         │
│  · ai-checklist.yaml           │
│  · quality.json（如存在）       │
│  · Java 源文件                  │
│  → findings.json               │
│  · spec_violations[]           │
│    按 P0/P1/P2 分级             │
│  · quality_issues[]            │
│    按 high/medium/low 分级      │
│  · review_status: PASSED/FAILED│
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Step 3: 合并最终报告            │
│  quality.json + findings.json  │
│  → final-review-report.md      │
│  四大板块：                      │
│  ① 静态质量概览                  │
│  ② 规范合规检查（P0/P1/P2）      │
│  ③ 代码深度问题（高/中/低）       │
│  ④ 汇总统计 + 结论               │
└───────────────────────────────┘
```

**返回协议**：

| 返回值 | 含义 |
|--------|------|
| `REVIEW_PASSED` | 审查通过，无 P0 问题 |
| `REVIEW_FAILED` | 存在 P0 问题（或 P1 触发 strict 阻断） |
| `REVIEW_ERROR` | 环境/工具异常 |

---

## 规范体系

### 全局规则速查

> 以下规则适用于所有生成的代码，不读对应规范文件也必须遵守：

| 规则 | 说明 |
|------|------|
| 包结构 | `controller → service/impl → mapper → entity/dto/vo` |
| 返回值 | 统一使用 `Result<T>` 包裹，禁止返回裸类型 |
| 依赖注入 | 构造注入 `@RequiredArgsConstructor`，禁用 `@Autowired` 字段注入 |
| 日志 | 使用 `@Slf4j`，禁止打印密码、Token 等敏感信息 |
| 异常 | 抛出 `BusinessException(BusinessErrorEnum.XXX)`，不写自由文本 |
| SQL | 简单查询用 `LambdaQueryWrapper`，复杂/联表/子查询走 XML，禁用 `@Select` |
| 参数 | 超过 3 个必须收敛到一个 DTO |
| URL | RESTful 复数名词，CRUD 不写动词；非 CRUD 动作（cancel、reset）允许动词 |

### 按任务类型读取规范

AI Agent 写代码前，先读 `agents/coder/README.md`（规范索引），再根据任务类型加载对应规范：

| 任务 | 必读规范（按顺序） |
|------|------|
| 新建项目 | `architecture/` → `infrastructure/config-guide.md` → `quality/code-style-guide.md` |
| 写 Controller | `layered/controller-guide.md` → `infrastructure/result-guide.md` → `quality/jsr303-guide.md` |
| 写 Service | `layered/service-guide.md` → `quality/code-style-guide.md` → `quality/error-code-reference.md` |
| 写 Mapper | `layered/mapper-guide.md` → `quality/code-style-guide.md` |
| 认证授权 | `auth/auth-overview.md`（先确认场景）→ `auth-basic.md` + 对应扩展 |
| 建表 | `quality/database-guide.md` |

---

## 双层审查系统

位于 `agents/reviewer/check_system/`，是一套完整的代码审查基础设施。

### Layer 1: AI 检查清单

所有规则来源于 `agents/coder/` 下 12 个规范文件，逐条提取而成，保证与规范文件同步。

配置在 `rules/ai-checklist.yaml`，每条规则格式：

```yaml
BE-MP-01:
  description: "是否使用了 @Select/@Update/@Insert 注解写 SQL（禁止）"
  level: P0
  check: "检查 Mapper 接口方法上是否有 @Select、@Update、@Insert、@Delete 注解。
          SQL 必须写在 XML 文件中，注解里写 SQL 不可格式化、不可 DTD 校验"
```

覆盖维度：

| 维度 | 编码前缀 | 规则数 | 检查内容示例 |
|------|:--:|:--:|------|
| 分层架构 | `BE-ST-` | 4 | Controller 是否直注 Mapper、Service 是否暴露 Entity |
| Controller 层 | `BE-CT-` | 4 | GET 是否用 DTO 参数、分页是否用 POST、URL 是否含动词 |
| Service 层 | `BE-SV-` | 3 | @Transactional 回滚配置、Servlet API 注入、方法命名 |
| Mapper 层 | `BE-MP-` | 6 | 禁用注解写 SQL、雪花 ID、审计字段自动填充、LambdaQueryWrapper |
| 异常处理 | `BE-QL-` | 5 | RuntimeException、BusinessException、try-catch、吞异常 |
| 日志 | `BE-QL-` | 2 | 日志信息完整性、循环内日志 |
| 代码质量 | `BE-QL/CS-` | 10 | 裸返回类型、集合 null、字符串拼接、魔法数字、N+1 查询 |
| Result | `BE-RS-` | 3 | Result 包裹、新增操作返回值、成功消息 |
| Swagger | `BE-SW-` | 3 | @Tag、@Operation、@Schema 注解 |
| 数据库 | `BE-QL/DB-` | 7 | 审计字段、雪花 ID、逻辑删除、表前缀、时间字段 |
| 认证安全 | `BE-AU-` | 2 | BCrypt 加密、多端 StpKit 使用 |

### Layer 2: 报告渲染器

`code_check/reporter.py` 将审查数据渲染为结构化的 Markdown 报告：

```
# 代码审查报告
状态: PASSED  /  FAILED
扫描路径: /path/to/src
文件数量: 15 个
质量评分: 85/100

## 静态质量概览       ← 总体评分 + 7 维指标 + 最差文件 Top 10
## 规范合规检查        ← P0/P1/P2 分级表格，含文件、行号、方法、建议
## 代码深度问题        ← high/medium/low 分级，含 N+1、复杂度、重复代码
## 汇总               ← 数量统计 + 质量评分
## 结论               ← 最终判定 + 总结建议
```

### 严重级别

| 级别 | 含义 | 行为 |
|:--:|------|------|
| P0 | 安全漏洞、崩溃风险、数据错误 | **必须修复**，阻断流水线，无法通过审查 |
| P1 | 违反核心规范、可能引发线上问题 | 强烈建议修复，strict 策略下阻断 |
| P2 | 风格建议、轻微改进 | 可议，不阻断 |

### 阻断策略

可通过配置文件调整阻断行为：

| 策略 | P0 | P1 | 适用场景 |
|------|:--:|:--:|------|
| `strict` | 阻断 | 阻断 | 核心业务模块，P1 也不放过 |
| `normal` | 阻断 | 通过 | 一般业务开发（推荐） |
| `loose` | 阻断 | 通过 | 快速迭代，P2 规则跳过 |

---

## 流水线引擎

`agents/scheduler/pipeline_engine/` 是一个独立的 Python 包，负责解析 DAG 配置并按拓扑顺序驱动 Agent 执行。

### 设计原理

```
┌──────────────────────────────────────┐
│          pipeline.yaml                │
│  ┌─────────┐     ┌──────────┐        │
│  │  coder  │────▶│ reviewer │        │
│  └─────────┘     └────┬─────┘        │
│       ▲               │              │
│       │   on FAILED   │  on PASSED   │
│       └───────────────┘  ──▶ DONE    │
└──────────────────────────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  PipelineEngine  │  │  pipeline_state │
│  · start()       │  │  .json          │
│  · next()        │  │  (持久化)        │
│  · report()      │  │                 │
│  · status()      │  │                 │
│  · reset()       │  │                 │
└─────────────────┘  └─────────────────┘
```

### CLI 命令参考

```bash
# 启动新流水线
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/pipeline-state.json \
  --base-path "." --project-name "admin-test-01" \
  --requirement "实现用户登录功能"

# 获取下一个待执行节点（返回 JSON，含渲染后的 prompt）
python3 -m pipeline_engine.cli next \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/pipeline-state.json

# 上报节点执行结果
python3 -m pipeline_engine.cli report \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file review-output/pipeline-state.json \
  --node coder \
  --status success \
  --summary "5 files generated" \
  --verdict REVIEW_PASSED

# 查看流水线状态
python3 -m pipeline_engine.cli status \
  --state-file review-output/pipeline-state.json

# 重置（清除状态）
python3 -m pipeline_engine.cli reset \
  --state-file review-output/pipeline-state.json
```

### DAG 配置

`agents/scheduler/pipeline.yaml` 定义节点和流转规则：

```yaml
name: coder-reviewer-pipeline
version: "1.0"

defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]

nodes:
  - id: coder
    type: agent
    agent: coder
    prompt_template: |
      根据用户需求生成 Java 代码...
      用户需求：{requirement}
      代码输出目录：{output_dir}/src/main/java
    timeout: 900s

  - id: reviewer
    type: agent
    agent: reviewer
    prompt_template: |
      对 coder 产出的代码执行双层审查...
    depends_on: [coder]

edges:
  - from: coder → reviewer (on_success)
  - from: reviewer → coder (REVIEW_FAILED, retry < max_retries)
  - from: reviewer → DONE  (REVIEW_PASSED)
  - from: reviewer → DONE  (REVIEW_FAILED, retry = max_retries)
  - from: reviewer → DONE  (REVIEW_ERROR)
```

### 关键机制

- **拓扑排序**：按 DAG 边的依赖关系确定执行顺序，支持并行节点
- **条件流转**：根据 `agent_verdict`（REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR）决定下一步
- **修复上下文注入**：`{review_context}` 和 `{run_id}` 模板变量，在修复轮次自动注入前一轮的审查结果
- **状态持久化**：JSON 文件记录完整状态，支持 `/build --resume` 断点续接
- **边界约束**：coder 只能修改 `{output_dir}/` 下的代码，禁止修改 `agents/` 审查系统文件

---

## 测试

```bash
# 审查系统测试
cd agents/reviewer/check_system && python3 -m pytest tests/ -v

# 调度引擎测试
cd agents/scheduler && python3 -m pytest tests/ -v

# 全部测试
python3 -m pytest agents/*/tests/ -v
```

| 测试模块 | 覆盖内容 |
|------|------|
| `test_models.py` | 数据模型序列化/反序列化、P0/P1 统计、quality_issue 统计 |
| `test_reporter.py` | 报告渲染（PASSED/FAILED、空数据、quality 缺失、指标表格） |
| `test_cli.py` | CLI 命令行参数解析、缺失参数错误处理 |
| `test_engine.py` | 流水线引擎完整状态机：启动/执行/重试/DONE 判定/状态恢复/并发上报保护 |
| `test_config.py` | YAML 配置加载、节点/边校验 |
| `test_cli.py`（scheduler） | CLI start/next/report/status/reset 命令 |

---

## 基准测试

项目内置了一套完整的流水线性能基准测试系统，用于追踪每次 `/build` 运行的性能数据、分析修复效率、横向对比规范变更带来的影响。

### 系统架构

```
Claude Code Hooks
    │
    ├── PostToolUse (Agent)  →  dump-agent-payload.sh
    │    每次 Agent 调用完成时采集：时长、Token、模型、判定结果
    │    写入 benchmarks/dumps/session-{id}.jsonl
    │
    └── Stop (会话结束)       →  synthesize-benchmark.sh
         调用 schema.py 合成完整报告，产出：
         · benchmarks/run-{timestamp}-{slug}.json   (结构化数据)
         · benchmarks/run-{timestamp}-{slug}.md     (可读报告)
```

### 单次运行报告

每次 `/build` 完成后自动生成，包含以下分析维度：

**Agent 版本指纹**

记录 coder（规范文件）和 reviewer（检查规则 + Python 代码）的 SHA256 指纹，追踪规范变更对每次运行的影响：

```
| Agent    | Fingerprint | 源文件数 |
|----------|-------------|---------|
| coder    | a1b2c3d4    | 22      |
| reviewer | e5f6g7h8    | 8       |
```

**收敛曲线**

追踪每轮审查中 P0/P1/P2 数量的变化，直到收敛或达到最大重试：

```
| Round | P0 | P1 | P2 | AI_FAIL |
|-------|----|----|----|---------|
| 0     | 5  | 3  | 2  | 2       |
| 1     | 2  | 1  | 1  | 0       |
| 2     | 0  | 0  | 1  | 0       |
```

**各轮次详情**

记录每个 Agent 调用阶段的耗时、Token 消耗、工具调用次数、缓存命中率、审查结果。

**阶段拆解**

按 generate（初始生成）、fix（修复轮次）、review（审查）三个阶段分别统计 Token 和时间开销，量化修复成本。

**问题分布**

- 按文件聚合 P0/P1/P2 数量，定位问题集中的热点文件
- 按规则类别聚合 FAIL 数量，发现高频违规类型

**修复质量分析**

| 指标 | 说明 |
|------|------|
| 反复问题 | 同一规则码在多轮审查中持续出现，标记为顽固问题 |
| 修复副作用 | 修复过程中引入的新问题（上一轮没有，本轮新增） |
| 修复有效率 | 每轮修复后，上一轮的 FAIL 项在本轮被修复的比例 |
| 边际修复成本 | 每一轮修复消耗的 Token，及相比上一轮的增长/下降趋势 |

**汇总指标**

| 指标 | 说明 |
|------|------|
| 总耗时 / 总 Token / 总 Tool Uses | 端到端统计 |
| Coder vs Reviewer 占比 | 生成与审查的 Token 和耗时对比 |
| 缓存命中率 | cache_read / (cache_read + input) 比例 |
| 审查开销占比 | Reviewer Token / 总 Token |
| 每修复一个 P0 消耗 Token | 修复效率的量化指标 |
| P0 减少率 | 首次审查到最终审查的 P0 降低比例 |
| 模型使用统计 | 各模型调用次数分布 |

### 跨运行对比

`compare.py` 脚本加载 `benchmarks/` 目录下所有 `run-*.json` 文件，生成横向对比报告。

```bash
python3 benchmarks/hooks/compare.py benchmarks -o benchmarks/comparison-report.md
```

**基线计算与异常检测**

从所有历史运行计算均值与标准差，对当前运行进行 >2σ 偏离告警：

```
| 指标   | 均值      | 标准差    |
|--------|-----------|----------|
| 起始 P0 | 3.5       | ±1.2     |
| 总 Token | 185,000  | ±32,000  |
| 收敛轮次 | 2.1      | ±0.8     |
| 缓存命中率 | 34.2%   | ±8.5%    |
```

**ASCII 趋势图**

Token 消耗、P0 数量、收敛轮次、缓存命中率四个维度的可视化趋势，使用 8 级高度字符：

```
   185,000 ┤ ▁▃▅▇█
           └────────
            R1 R2 R3
```

**变更归因**

对比相邻运行的 git commit，检测 coder/reviewer 规范文件的变更，自动计算性能影响：

```
| 运行      | Commit   | 变更 Agent | 文件数 | Token 变化 | P0 变化 |
|-----------|----------|-----------|--------|-----------|---------|
| run-...1  | a1b2c3d  | reviewer  | 3      | +12.3%    | -2      |
```

### 实际案例：三版本横向对比

项目内置了 `admin-test-01`、`admin-test-02`、`admin-test-03` 三个版本的基准测试对比报告（`BENCHMARK-REPORT.md`），从以下维度进行量化对比：

| 维度 | admin-test-01 | admin-test-02 | admin-test-03 |
|------|:---:|:---:|:---:|
| 架构纯度 | 较差 | 较差 | 优秀 |
| RBAC 权限安全 | 缺失 | 缺失 | 完整 |
| SQL 规范 | 未使用 LambdaQuery | 合规 | 合规 |
| 参数校验覆盖 | 41 | 33 | 44 |
| 审查通过 | 无记录 | 90/99 | 0 P0/P1 |
| 综合评分 | 61/100 | 80/100 | 80/100 |

报告还包含根因分析（Coder 遗漏 vs Reviewer 审查盲区）、优缺点矩阵、待修复清单等章节。详见 [BENCHMARK-REPORT.md](BENCHMARK-REPORT.md) 和 [ROOT-CAUSE-ANALYSIS.md](ROOT-CAUSE-ANALYSIS.md)。

### Hook 配置

基准测试通过 Claude Code hooks 自动采集，配置在项目 `.claude/settings.json` 中：

- **PostToolUse hook**（matcher: `Agent`）：每次 Agent 工具调用后触发，采集性能数据
- **Stop hook**：会话结束时触发，合成完整 JSON + Markdown 报告

无需手动操作，流水线性能数据自动记录。

---

## 路线图

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| Phase 1-3 | Coder 规范库 + Reviewer 双层审查 + Pipeline 引擎 | Done |
| Phase 4 | **Analyst Agent** — 需求 → PRD → 技术规格 → API 设计 → 数据库设计 | Planned |
| Phase 5 | **CI/CD 集成** — GitHub Actions / GitLab CI 一键接入 | Planned |
| Phase 6 | **多语言支持** — Python、Go、TypeScript 规范库 | Planned |
| Phase 7 | **历史分析** — 审查趋势、团队质量报表、问题闭环率 | Planned |

---

## 贡献指南

我们欢迎任何形式的贡献！无论是新增规范、改进检查规则、优化报告格式，还是修复 Bug。

### 贡献流程

```bash
# 1. Fork 仓库 & 创建分支
git checkout -b feat/your-feature

# 2. 编写代码 & 测试
# 修改代码后运行测试确保通过
python3 -m pytest agents/*/tests/ -v

# 3. 提交 & 发起 PR
git commit -m "feat: 描述你的改动"
git push origin feat/your-feature
```

### 贡献方向

- 新增规范文件：补充当前规范库未覆盖的领域（如消息队列、定时任务）
- 扩展检查清单：在 `ai-checklist.yaml` 中添加新的检查规则
- 改进报告模板：优化 Markdown 报告的可读性和信息密度
- 增强调度引擎：支持更复杂的 DAG 流转逻辑
- 增加测试覆盖：补充边界场景的测试用例
- 完善基准测试：扩展 schema.py/compare.py 的分析维度（如成本预估、修复时间预测）

---

## License

MIT © 2025

---

<p align="center">
  <sub>Built for the Java backend community. If this project helps you, please consider giving it a star.</sub>
</p>
