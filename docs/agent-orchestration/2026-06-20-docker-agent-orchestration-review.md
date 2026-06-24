# Agent 编排架构 —— Docker 拆分方案评审

> 目标：将 coder 和 reviewer 拆分为两个独立的 Claude Code Docker 镜像，通过编排层实现单入口启动不同 agent。

---

## 一、当前架构总览

```
agents/
├── coder/          # 20 个规范文件，按 architecture/layered/infrastructure/auth/quality 分类
└── reviewer/       # 4 个审查文件 + check_system/ Python CLI 双层校验
    └── check_system/
        ├── Layer 1: Python CLI 程序预检（零 AI Token，确定性规则）
        └── Layer 2: AI 检查清单（语义理解，逐项确认）
```

coder 和 reviewer 在文件层面已经是解耦的，各自有独立的 README、独立的关注点、独立的执行入口。双层校验系统的设计已经成熟（6 种扫描器、39+17 条规则、三档阻断策略）。

---

## 二、Docker 拆分方案的优点

**1. 独立版本管理和发布**
coder 规范更新时不需要重新构建 reviewer 镜像，反之亦然。在规范迭代频繁的团队里非常有价值。

**2. 独立扩展**
如果未来 coder 成为瓶颈，可以启动多个 coder 容器并行处理不同模块，reviewer 保持单实例。

**3. 清晰的契约边界**
Docker 镜像天然强制定义好输入/输出接口。coder 输出 Java 代码 + 元数据，reviewer 消费代码 + 输出审查报告。

**4. 与现有双层校验系统天然契合**
check_system 的 Python CLI 本身就是独立进程，打包进 reviewer 镜像是顺理成章的。

---

## 三、需要认真考虑的问题

### 问题 1：规范文件放哪里？（核心架构决策）

当前规范文件（`agents/coder/*.md`）被 coder 和 reviewer **同时消费**：

- coder 读规范来**生成**代码
- reviewer 读规范来**审查**代码

三种方案：

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| A. 复制两份 | coder-image 和 reviewer-image 各含一份规范 | 镜像自包含，无外部依赖 | 规范更新需同时重建两个镜像，容易不同步 |
| **B. 共享 Volume** | 规范文件挂载为外部 Volume | 单一真相源 | 破坏镜像自包含性，K8s 下 Volume 管理复杂 |
| **C. 基础镜像（推荐）** | `specs-base-image` 含规范 → coder/reviewer FROM 它 | **单一真相源 + 镜像自包含** | 规范更新需重建所有下游镜像 |

**推荐方案 C。** 结构如下：

```dockerfile
# specs-base-image: 规范文件 + 共享工具
FROM ubuntu:latest
COPY agents/ /agents/
# 规范文件只读，单一真相源

# coder-image: 基础镜像 + Claude Code + coder 入口
FROM specs-base:latest
COPY coder-entrypoint.sh /
ENTRYPOINT ["/coder-entrypoint.sh"]

# reviewer-image: 基础镜像 + Claude Code + Python CLI + reviewer 入口
FROM specs-base:latest
COPY check_system/ /check_system/
COPY reviewer-entrypoint.sh /
ENTRYPOINT ["/reviewer-entrypoint.sh"]
```

### 问题 2：代码如何流转？

coder 写完代码后，reviewer 需要读取这些代码。当前是同目录直接读，Docker 化后需要考虑：

```
coder 容器  ──(产出 Java 代码)──>  共享存储  ──(读取)──>  reviewer 容器
```

三种流转方案：

| 方案 | 做法 | 适用场景 |
|------|------|---------|
| **Git-based（推荐）** | coder 提交到临时分支 → reviewer checkout 该分支审查 | 开发规范校验，最自然 |
| Volume-based | 共享 Volume 挂载到两个容器 | 简单但不够解耦 |
| Artifact-based | coder 产出 tar/zip → 上传到制品库 → reviewer 下载 | CI/CD 生产流水线 |

对于当前场景（开发规范校验，不是 CI/CD 生产流水线），**Git-based 是最自然的选择**——coder 生成代码提交到分支，reviewer 拉取分支进行审查。

### 问题 3：编排层的复杂度边界

"启动一个 Docker 镜像启动不同的 agent" 有两种理解：

**理解 A：单一 orchestrator 镜像，内置 coder + reviewer 逻辑**

```bash
docker run orchestrator --mode=coder     # 以 coder 模式运行
docker run orchestrator --mode=reviewer  # 以 reviewer 模式运行
```

→ 简单，但本质上是一个镜像两种模式，不是"两个独立镜像"

**理解 B（推荐）：orchestrator 是薄编排层，按需拉起 coder/reviewer 容器**

```bash
docker run orchestrator --pipeline="coder→review" --repo=xxx
# orchestrator 内部:
#   1. docker run coder-image ...     → 产出代码
#   2. docker run reviewer-image ...  → 产出审查报告
```

→ 真正独立镜像，但 orchestrator 需要 Docker socket 权限（docker-in-docker 或 sidecar）

**如果目标是"两个独立镜像"+"一个入口"，理解 B 是正确的方向。** orchestrator 本身是一个相对薄的层，主要做：

1. 参数解析和校验
2. 按顺序启动 coder/reviewer 容器
3. 传递中间产物（代码路径、commit SHA）
4. 汇总最终结果

### 问题 4：check_system Python CLI 的位置

当前 CLI 是 reviewer 的一部分。Docker 化后应该放在哪里？

**推荐：放进 reviewer-image。** 理由：

- Layer 1 程序预检是 reviewer 的前置步骤，逻辑上属于 reviewer
- Python 依赖（PyYAML）只在 reviewer 需要，不污染 coder 镜像
- 如果未来 coder 也想用程序预检做自我检查，可以在 specs-base-image 中包含 CLI

---

## 四、推荐的最终架构

```
┌──────────────────────────────────────────────────┐
│                  specs-base-image                  │
│  /agents/coder/*.md    (20 个规范文件，只读)        │
│  /agents/reviewer/*.md (4 个审查规范，只读)         │
│  /check_system/        (Python CLI，预检工具)      │
└──────────┬───────────────────────────┬───────────┘
           │                           │
    ┌──────┴───────┐           ┌──────┴───────┐
    │  coder-image  │           │ reviewer-image│
    │  Claude Code  │           │  Claude Code  │
    │  + coder      │           │  + reviewer   │
    │   入口脚本     │           │   入口脚本     │
    │  输入: 需求    │           │  输入: 代码路径 │
    │  输出: 代码    │           │  输出: 审查报告 │
    └──────┬───────┘           └──────┬───────┘
           │                           │
           └───────────┬───────────────┘
                       │
               ┌───────┴────────┐
               │  orchestrator   │
               │  (编排容器)      │
               │  输入: 任务描述   │
               │  输出: 代码+报告  │
               │                 │
               │  Pipeline:      │
               │  coder →        │
               │  pre-check →    │
               │  reviewer →     │
               │  final-report   │
               └────────────────┘
```

### 容器间协议（标准化接口）

每个 agent 镜像需要标准化接口：

```yaml
# coder 容器契约
输入:
  - TASK_DESCRIPTION: 任务描述（环境变量或挂载文件）
  - SPECS_VERSION: 规范版本标签（确保用哪个版本的规范）
输出:
  - /output/code/         # 生成的 Java 代码
  - /output/metadata.json # {files_changed, specs_version, timestamp}

# reviewer 容器契约
输入:
  - /input/code/          # 待审查的 Java 代码（从 coder 产出挂载）
  - STRATEGY: strict|normal|loose
输出:
  - /output/pre-check-result.json    # Layer 1 程序预检
  - /output/review-result.json       # Layer 2 AI 检查
  - /output/final-review-report.md   # 最终报告
```

### orchestrator 的工作流程

```
1. 接收任务 → 解析参数
2. docker run coder-image → 等待完成 → 获取代码
3. docker run reviewer-image → 等待完成 → 获取报告
4. 汇总输出 → 展示给用户
```

---

## 五、代价分析：当前 vs Docker 拆分

| 维度 | 当前（单仓库） | Docker 拆分后 |
|------|-------------|-------------|
| 开发调试 | 直接改文件即生效 | 需重建镜像或 Volume 挂载 |
| 规范更新 | 改一个文件，全局生效 | 需重建 specs-base + 下游镜像 |
| 部署复杂度 | `git clone` 即可 | 需要 Docker registry + 镜像管理 |
| 隔离性 | 无，依赖 Python/Node 环境 | 完全隔离 |
| 水平扩展 | 不支持 | 天然支持 |

---

## 六、建议实施路线

### 第一步（优先做）：不拆 Docker 镜像，先把编排层做起来

- 用 Shell 脚本或简单的 Python 脚本串联 `claude` CLI 的 coder 模式和 reviewer 模式
- 验证编排流程：coder → pre-check → reviewer → report
- 打磨容器间的契约接口

### 第二步（验证后再做）：Docker 化

- 抽取 specs-base-image
- 构建 coder-image / reviewer-image
- 实现 orchestrator 容器

**这样可以避免过早 Docker 化带来的调试成本。当编排流程稳定后，Docker 化就是纯粹的打包工作。**

---

## 七、总结

| 维度 | 评分 | 说明 |
|------|:--:|------|
| 架构方向正确性 | ⭐⭐⭐⭐⭐ | coder/reviewer 职责天然可拆分，方向完全正确 |
| 当前解耦程度 | ⭐⭐⭐⭐ | 文件层面已解耦，Python CLI 独立运行 |
| Docker 化收益 | ⭐⭐⭐⭐ | 独立版本管理、隔离、扩展 |
| Docker 化紧迫度 | ⭐⭐ | 当前单仓库运作良好，Docker 化是锦上添花不是雪中送炭 |
| 编排层设计空间 | ⭐⭐⭐⭐⭐ | 干净的分层结构，接口清晰 |

**结论：架构方向完全正确，建议先做编排脚本验证流程，稳定后再 Docker 化。**
