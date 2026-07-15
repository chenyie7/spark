<p align="center">
  <h1 align="center">Spark ⚡</h1>
  <p align="center">
    <strong>约束 AI，写规范的 Java 代码</strong><br>
    多 Agent 协作的代码生成、审查、自动修复流水线
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Java-17+-orange" alt="Java 17+">
  <img src="https://img.shields.io/badge/Spring_Boot-3.x-green" alt="Spring Boot 3">
  <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Claude_Code-Compatible-purple" alt="Claude Code">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License MIT">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
</p>

---

## 为什么需要 Spark

AI 代码生成工具虽然高效，但在企业级 Java 开发中存在一个共同问题：

> **生成的代码风格不一致、规范不统一、质量不可控。**

单次 Prompt 很难让 AI 一次性记住所有规范约束——分层架构、异常处理、日志规范、认证安全、数据库设计……遗漏一个就可能造成线上事故。

**Spark 的解决思路**：将规范从 Prompt 中解耦，建立结构化的规范知识库，通过「生成 → 审查 → 修复」的多 Agent 流水线强制执行这些规范。

| 特性 | 说明 |
|------|------|
| 📚 规范知识库 | 22 个结构化 Markdown 规范文件，按任务类型索引，AI 按需读取 |
| 🛡️ 双层审查 | Layer 1 静态分析（零 AI Token）+ Layer 2 AI 语义审查 |
| 🔄 自动修复循环 | P0 问题自动回到 coder 修复 → 再审查，最多 3 轮 |
| 📊 标准化输出 | JSON + Markdown 报告，可直接集成 CI/CD |
| ⚙️ DAG 编排 | YAML 声明 Agent 依赖和流转规则，调度引擎自动执行 |
| 📈 性能可观测 | Hook 自动采集 → Stop 自动合成，支持 `/spark:benchmarks` 性能分析 |

**适用技术栈**：Spring Boot 3 + Spring Cloud 微服务，标准分层架构（Controller → Service → Mapper → Entity/DTO/VO）。

---

## 快速上手

### 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行 CLI 和调度引擎 |
| Node.js | 18+ | 运行静态分析 MCP server（可选） |
| Claude Code | 最新版 | AI Agent 运行环境 |

### 三步开始

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/spark.git
cd spark

# 2. 安装依赖
pip install pyyaml jsonschema

# 3. 在 Claude Code 中直接使用
# /build 实现用户登录功能，包括用户名密码登录和验证码登录
```

就是这么简单。你描述需求，流水线自动完成：**生成代码 → 双层审查 → 修复循环 → 输出报告**。

### 三种使用方式

| 方式 | 命令 | 说明 |
|------|------|------|
| 一键流水线 | `/build <需求>` | 推荐：需求 → 代码 → 审查 → 修复，全自动 |
| 仅审查 | `/review <路径>` | 对已有代码执行双层审查，输出报告 |
| CLI 报告 | `python3 -m code_check.cli report ...` | 将审查 JSON 渲染为 Markdown 报告 |
| 性能分析 | `/spark:benchmarks <run_id>` | 读取 benchmark 数据进行性能对比 |

---

## 核心工作流

### `/build` 一键流水线

```
用户输入需求
    │
    ▼
┌─────────────────┐
│  Phase 0: 初始化  │  解析参数 → 创建 run_id → 写入状态
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 1: Coder  │  读取规范索引 → 按任务类型加载规范
│                  │  → 生成 Controller/Service/Mapper/Entity/DTO/VO
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phase 2:        │  Layer 1: fuck-u-code 静态分析 (~5s, 零 Token)
│  Reviewer        │  Layer 2: AI 统一审查 → 对照 ai-checklist.yaml
│                  │  产出 findings.json + final-review-report.md
└────────┬────────┘
         │
    ┌────┴────────────────────────────┐
    │  REVIEW_PASSED?                  │
    ├── YES ──▶ ✅ DONE               │
    ├── NO, retry < 3 ──▶ 🔄 回到 Coder│
    │   修复模式下重新生成，注入审查上下文  │
    └── NO, retry = 3 ──▶ ⚠️ DONE     │
```

**关键特性**：状态持久化支持 `--resume` 续接、同一轮次多节点并行、修复上下文自动注入、性能数据自动采集。

### `/review` 单独审查

```
┌───────────────────────────────┐
│  Step 1: fuck-u-code 静态分析  │  → quality.json · 评分 · 7维指标
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Step 2: AI 统一审查           │  → findings.json · P0/P1/P2 分级
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Step 3: 合并最终报告           │  → final-review-report.md
└───────────────────────────────┘
```

**返回结果**：

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
| URL | RESTful 复数名词，CRUD 不写动词；非 CRUD 动作允许动词 |

### 按任务类型加载规范

AI 写代码前先读 `agents/coder/README.md`（规范索引），再按任务跳转：

| 任务 | 必读规范 |
|------|------|
| 新建项目 | `architecture/` → `config-guide` → `code-style-guide` |
| 写 Controller | `controller-guide` → `result-guide` → `jsr303-guide` |
| 写 Service | `service-guide` → `code-style-guide` → `error-code-reference` |
| 写 Mapper | `mapper-guide` → `code-style-guide` |
| 认证授权 | `auth-overview`（先确认场景）→ 对应认证方案 |
| 建表 | `database-guide` |

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
         │  benchmarks/                                    │
         │  Hook 采集 → 自动合成 → 7 天保留 → Skill 分析    │
         └────────────────────────────────────────────────┘
```

---

## 项目结构

```
spark/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── CLAUDE.md                     # Claude Code 项目指令
├── .mcp.json                     # MCP 服务器配置
│
├── agents/
│   ├── pm/                       # 需求沟通 Agent
│   │   └── pm.skill.md
│   ├── coder/                    # 编码规范库（22 个规范文件）
│   │   ├── README.md             #   规范入口索引
│   │   ├── architecture/         #   2 个架构规范
│   │   ├── layered/              #   3 个分层规范
│   │   ├── infrastructure/       #   6 个基础设施规范
│   │   ├── auth/                 #   6 个认证授权规范
│   │   └── quality/              #   5 个质量规范
│   ├── reviewer/                 # 代码审查系统
│   │   ├── review.skill.md       #   /review 命令定义
│   │   └── check_system/         #   双层校验系统（Python CLI）
│   │       ├── code_check/       #   cli.py / models.py / reporter.py
│   │       ├── rules/            #   ai-checklist.yaml 检查清单
│   │       └── tests/            #   单元测试
│   └── scheduler/                # 流水线调度器
│       ├── build.skill.md        #   /build 命令定义
│       ├── pipeline.yaml         #   DAG 配置（节点 + 边 + 流转规则）
│       ├── pipeline_engine/      #   Python 调度引擎
│       └── tests/
│
├── benchmarks/                   # 基准测试系统
│   ├── config.yaml               #   集中配置（保留天数、路径映射）
│   ├── benchmark_lib/            #   纯 Python 逻辑包（7 个模块）
│   ├── hooks/                    #   数据采集 Hook
│   ├── dumps/                    #   原始性能数据（按 run_id）
│   └── {run_id}/                 #   合成产物（按运行分组）
│       ├── pipeline-log.jsonl    #     结构轮次日志
│       ├── benchmark.json        #     结构性能数据
│       └── report.md             #     可读报告
│
└── docs/                         # 项目文档
    └── superpowers/              #   设计 Spec + 实现 Plan
```

---

## 双层审查系统

### 严重级别

| 级别 | 含义 | 行为 |
|:--:|------|------|
| P0 | 安全漏洞、崩溃风险、数据错误 | **必须修复**，阻断流水线 |
| P1 | 违反核心规范、可能引发线上问题 | 强烈建议修复，strict 策略下阻断 |
| P2 | 风格建议、轻微改进 | 可议，不阻断 |

### 阻断策略

| 策略 | P0 | P1 | 适用场景 |
|------|:--:|:--:|------|
| `strict` | 阻断 | 阻断 | 核心业务模块，P1 也不放过 |
| `normal` | 阻断 | 通过 | 一般业务开发（推荐） |
| `loose` | 阻断 | 通过 | 快速迭代 |

### 检查清单覆盖维度

`rules/ai-checklist.yaml` 涵盖 11 个维度，规则来源于 22 个规范文件：

| 维度 | 编码前缀 | 检查内容示例 |
|------|:--:|------|
| 分层架构 | `BE-ST-` | Controller 是否直注 Mapper、Service 是否暴露 Entity |
| Controller 层 | `BE-CT-` | URL 是否含动词、分页是否用 POST |
| Service 层 | `BE-SV-` | @Transactional 回滚配置、方法命名 |
| Mapper 层 | `BE-MP-` | 禁用注解写 SQL、LambdaQueryWrapper |
| 异常处理 | `BE-QL-` | RuntimeException、BusinessException、吞异常 |
| 日志 | `BE-QL-` | 日志完整性、敏感信息 |
| 代码质量 | `BE-QL/CS-` | 裸返回类型、集合 null、魔法数字、N+1 |
| Result | `BE-RS-` | Result 包裹、新增操作返回值 |
| Swagger | `BE-SW-` | @Tag、@Operation、@Schema 注解 |
| 数据库 | `BE-QL/DB-` | 审计字段、雪花 ID、逻辑删除 |
| 认证安全 | `BE-AU-` | BCrypt 加密、多端 StpKit |

---

## 核心设计理念

### 1. 规范即代码

规范文件与业务代码同仓，版本化管理。AI 写代码时按索引按需加载——不浪费上下文窗口。

```
agents/coder/
├── README.md          # 入口索引 — 按任务类型指引 AI 读取哪些规范
├── architecture/      # 架构规范
├── layered/           # 分层规范
├── infrastructure/    # 基础设施规范
├── auth/              # 认证授权规范
└── quality/           # 质量规范
```

### 2. 双层审查防线

```
Layer 1: fuck-u-code 静态分析 ~5s, 零 AI Token, 7 维质量指标
         ↓ 通过后
Layer 2: AI 统一审查 → 对照 ai-checklist.yaml 逐项检查，理解代码意图
```

### 3. 流水线即 DAG

YAML 定义 Agent 节点和边，Python 调度引擎按拓扑顺序驱动：

```
coder ────▶ reviewer ────▶ DONE (REVIEW_PASSED)
                │
                └──▶ coder (REVIEW_FAILED, 重试 ≤ 3 轮)
                │
                └──▶ DONE (REVIEW_ERROR)
```

### 4. 性能可观测

每次 `/build` 通过 Claude Code Hooks 自动采集性能数据，产出结构化的 `benchmark.json` + `report.md`。

---

## 流水线引擎

`agents/scheduler/pipeline_engine/` 是独立的 Python 包，解析 DAG 配置并按拓扑顺序驱动 Agent。

**关键机制**：

- **拓扑排序**：按 DAG 边的依赖关系确定执行顺序，支持并行节点
- **条件流转**：根据 `agent_verdict`（PASSED / FAILED / ERROR）决定下一步
- **修复上下文注入**：在修复轮次自动注入前一轮的审查结果
- **状态持久化**：JSON 文件记录完整状态，支持 `--resume` 断点续接
- **边界约束**：coder 只能修改输出目录下的代码，禁止修改审查系统文件

```bash
# CLI 命令一览
python3 -m pipeline_engine.cli start   # 启动流水线
python3 -m pipeline_engine.cli next    # 获取下一节点
python3 -m pipeline_engine.cli report  # 上报执行结果
python3 -m pipeline_engine.cli status  # 查看状态
python3 -m pipeline_engine.cli reset   # 重置
```

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
| `test_models.py` | 数据模型序列化、P0/P1 统计 |
| `test_reporter.py` | 报告渲染（PASSED/FAILED、空数据、quality 缺失） |
| `test_cli.py` | CLI 命令行参数解析 |
| `test_engine.py` | 流水线完整状态机：启动/重试/DONE/恢复/并发保护 |
| `test_config.py` | YAML 配置加载、节点/边校验 |

---

## 基准测试

每次 `/build` 通过 PostToolUse Hook 自动采集性能数据，Stop hook 自动合成结构化的 `benchmark.json` + `report.md`。支持 7 天数据保留、JSON Schema v2.0 校验、手动的 `/spark:benchmarks` 性能分析。

---

## 路线图

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| Phase 1-3 | Coder 规范库 + Reviewer 双层审查 + Pipeline 引擎 | ✅ Done |
| Phase 4 | **Analyst Agent** — 需求 → PRD → 技术规格 → API/DB 设计 | 🔨 Planned |
| Phase 5 | **CI/CD 集成** — GitHub Actions / GitLab CI 一键接入 | 🔨 Planned |
| Phase 6 | **多语言支持** — Python、Go、TypeScript 规范库 | 🔨 Planned |
| Phase 7 | **历史分析** — 审查趋势、团队质量报表 | 🔨 Planned |

---

## 贡献

我们欢迎任何形式的贡献！详见 **[贡献指南](CONTRIBUTING.md)**。

参与前请阅读 **[行为准则](CODE_OF_CONDUCT.md)**。

---

## License

[MIT](LICENSE) © 2025-present

---

<p align="center">
  <sub>Built for the Java backend community. If this project helps you, please consider giving it a ⭐</sub>
</p>
