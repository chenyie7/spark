# 文档与代码修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复重构后遗留的过期文档引用、错误数字、代码死路径和僵尸依赖，并在 README 中补充新手引导。

**Architecture:** 按依赖顺序执行 — 先修代码（无依赖），再修核心文档（reviewer/README.md），再修关联文档（CLAUDE.md、skill 文件），最后更新 README 并全局复查。

**Tech Stack:** Markdown 编辑、Python 代码修改

---

### Task 1: 修复 cli.py — 删除已失效的 code-check-config.yaml 同步代码

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py:59-68`

- [ ] **Step 1: 删除 L58-L68 的 YAML 同步逻辑**

`code-check-config.yaml` 在 commit `86d8740` 中已被删除。`cmd_start` 中尝试读写该文件的代码（L58-68）现在是死代码，需要删除。

在 `agents/scheduler/pipeline_engine/cli.py` 中，将 L56-L68：

```python
    run_id = state.run_id
    output_dir = state.output_dir

    # 同步更新 code-check-config.yaml，确保 reviewer 的扫描路径和输出目录正确
    import yaml as _yaml
    _config_path = Path("agents/reviewer/check_system/code-check-config.yaml")
    if _config_path.exists():
        with open(_config_path, "r") as f:
            _cfg = _yaml.safe_load(f) or {}
        _cfg["default_scan_path"] = f"../../../{output_dir}src/main/java"
        _cfg["output_dir"] = f"../../../{state.base_path}/review-output/{state.project_name}/{run_id}/"
        with open(_config_path, "w") as f:
            _yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)

    print(json.dumps({
```

替换为：

```python
    run_id = state.run_id
    output_dir = state.output_dir

    print(json.dumps({
```

- [ ] **Step 2: 验证 cli.py 语法正确**

```bash
python3 -c "import py_compile; py_compile.compile('agents/scheduler/pipeline_engine/cli.py', doraise=True)" && echo "OK"
```

- [ ] **Step 3: 提交**

```bash
git add agents/scheduler/pipeline_engine/cli.py
git commit -m "fix: 删除 cli.py 中对已删除文件 code-check-config.yaml 的同步逻辑

code-check-config.yaml 在重构中被删除，该同步代码已成为死代码。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 清理 requirements.txt 僵尸依赖

**Files:**
- Modify: `agents/reviewer/check_system/requirements.txt`

- [ ] **Step 1: 删除 tree-sitter 依赖**

将 `agents/reviewer/check_system/requirements.txt` 的内容从：

```
tree-sitter>=0.23.0
tree-sitter-java>=0.23.0
```

替换为空的（或删除该文件）。这两个依赖在 scanner.py 删除后已无任何代码使用。文件保留为空，因为其他 Python 依赖（如 PyYAML）由 scheduler 的 requirements.txt 管理。

```bash
# 清空文件内容
echo "" > agents/reviewer/check_system/requirements.txt
```

或者直接删除该文件：

```bash
rm agents/reviewer/check_system/requirements.txt
```

推荐清空保留，因为 `check_system/` 目录仍在使用中（reporter.py, models.py, cli.py），保留 requirements.txt 占位方便未来添加实际依赖。

- [ ] **Step 2: 提交**

```bash
git add agents/reviewer/check_system/requirements.txt
git commit -m "fix: 清理 requirements.txt 中的僵尸依赖 tree-sitter

scanner.py 已被删除，tree-sitter 和 tree-sitter-java 不再使用。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 重写 reviewer/README.md — 反映当前审查架构

**Files:**
- Modify: `agents/reviewer/README.md`

- [ ] **Step 1: 用新内容完全重写该文件**

旧文件描述的是基于 scanner.py + code-check-config.yaml 的双层审查系统，已被替换为 "fuck-u-code MCP 静态分析 + AI 统一审查"。用以下内容完全替换：

```markdown
# 代码审查系统

> 双层审查：fuck-u-code MCP 静态分析（零 AI Token）+ AI 统一语义审查，确保代码遵守 `agents/coder/` 中定义的开发规范。

---

## 一、审查架构

```
┌─────────────────────────────────────────────────────┐
│                  /review <path>                      │
│                 (review.skill.md)                    │
├─────────────────────────────────────────────────────┤
│  Layer 1: fuck-u-code MCP 静态分析                    │
│  零 AI Token · ~5s 完成 · 7 维质量指标                  │
│  产出 quality.json                                   │
├─────────────────────────────────────────────────────┤
│  Layer 2: AI 统一审查                                 │
│  Review Agent · 语义理解 · 对照 ai-checklist.yaml     │
│  产出 findings.json                                  │
├─────────────────────────────────────────────────────┤
│  合并: final-review-report.md                        │
└─────────────────────────────────────────────────────┘
```

---

## 二、快速使用

### 完整审查流程

```
/review <path>   → fuck-u-code 静态分析 → AI 语义检查 → 合并报告
```

### 生成最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --quality ../../../review-output/{run_id}/quality.json \
  --findings ../../../review-output/{run_id}/findings.json \
  --output ../../../review-output/{run_id}/final-review-report.md
```

---

## 三、规则体系

所有 AI 审查规则以 YAML 格式统一管理，来源于 `agents/coder/` 下的规范文件。

> AI 规则：`check_system/rules/ai-checklist.yaml`

覆盖维度：

| 维度 | 编码前缀 | 检查内容示例 |
|------|:--:|------|
| 分层架构 | `BE-ST-` | Controller 是否直注 Mapper、Service 是否暴露 Entity |
| Controller 层 | `BE-CT-` | GET 是否用 DTO 参数、分页是否用 POST、URL 是否含动词 |
| Service 层 | `BE-SV-` | @Transactional 回滚配置、Servlet API 注入、方法命名 |
| Mapper 层 | `BE-MP-` | 禁用注解写 SQL、雪花 ID、审计字段自动填充 |
| 异常处理 | `BE-QL-` | RuntimeException、BusinessException、try-catch、吞异常 |
| 日志 | `BE-QL-` | 日志信息完整性、循环内日志 |
| 代码质量 | `BE-QL/CS-` | 裸返回类型、集合 null、字符串拼接、魔法数字、N+1 查询 |
| Result | `BE-RS-` | Result 包裹、新增操作返回值、成功消息 |
| Swagger | `BE-SW-` | @Tag、@Operation、@Schema 注解 |
| 数据库 | `BE-QL/DB-` | 审计字段、雪花 ID、逻辑删除、表前缀、时间字段 |
| 认证安全 | `BE-AU-` | BCrypt 加密、多端 StpKit 使用 |

### 严重级别

| 级别 | 含义 | 处理 |
|------|------|------|
| P0 | 安全漏洞、崩溃、数据错误 | 必须修复 |
| P1 | 违反核心规范、可能导致线上问题 | 强烈建议修复 |
| P2 | 风格建议、轻微改进 | 可议 |

---

## 四、目录结构

```
reviewer/
├── README.md                    # 本文件
├── review.skill.md              # /review 斜杠命令定义
├── check_system/                # 审查系统
│   ├── code_check/              # Python 包
│   │   ├── cli.py               # CLI 入口 — report 命令
│   │   ├── models.py            # 数据模型
│   │   └── reporter.py          # 报告渲染器（Markdown）
│   ├── rules/                   # 检查规则（YAML 格式）
│   │   └── ai-checklist.yaml    # AI 检查清单
│   └── tests/                   # 单元测试
```

---

## 五、编码体系

每条检查项有唯一编码 `BE-{维度}-{序号}`：

| 编码前缀 | 维度 |
|:--|------|
| `BE-ST-` | 结构审查 |
| `BE-QL-` | 质量审查 |
| `BE-AU-` | 认证审查 |
| `BE-IN-` | 基础设施审查 |

---

## 六、审查原则

- **对照规范，不凭经验**：每条问题对应具体规则文件
- **区分强制和建议**：P0 阻断，P1 强烈建议，P2 可议
- **双层互补**：fuck-u-code 覆盖代码质量指标，AI 覆盖规范语义合规
- **只检查不修改**：审查不自动修复代码，除非用户明确要求
```

- [ ] **Step 2: 提交**

```bash
git add agents/reviewer/README.md
git commit -m "docs: 重写 reviewer/README.md 反映当前审查架构

- 删除所有对已删除文件的引用（scanner.py, config.py, code-check-config.yaml, program-checks.yaml, hooks/）
- 用 fuck-u-code MCP + AI 统一审查替换旧的 Python CLI 扫描描述
- 去掉具体规则数字，改为维度描述
- 精简目录结构为实际存在的文件

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 修复 CLAUDE.md — 多处过期内容

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 修改 L12 — 更新 check_system 描述**

将 L12：

```
3. **reviewer/check_system/** — 双层校验：程序预检 + AI 检查清单，防止规范遗漏
```

替换为：

```
3. **reviewer/check_system/** — 双层校验：fuck-u-code MCP 静态分析 + AI 统一审查，防止规范遗漏
```

- [ ] **Step 2: 删除 L33-L54 — "使用 CLI 进行程序预检" 整个章节**

删除从 `### 使用 CLI 进行程序预检` 到 `### 生成最终报告` 之间的 `scan` 命令示例和阻断策略描述。具体删除 L33-L54（含空行）。

同时更新 L56-L63 的 `report` 命令示例，将旧参数改为当前 CLI 支持的参数：

将：

```
### 生成最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```
```

替换为：

```
### 生成最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --quality review-output/{run_id}/quality.json \
  --findings review-output/{run_id}/findings.json \
  --output review-output/{run_id}/final-review-report.md
```
```

- [ ] **Step 3: 更新 L91-L103 — check_system 目录结构**

将目录结构中 `check_system/` 部分：

```
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
│       │   └── ai-checklist.yaml    # AI 检查清单（17 项语义规则）
│       ├── hooks/              # Pre/Post hook 脚本
│       └── code-check-config.yaml   # CLI 默认配置
```

替换为：

```
│   └── check_system/           # 双层校验系统（Python CLI）
│       ├── code_check/         # Python 包
│       │   ├── cli.py          # CLI 入口 — report 命令
│       │   ├── models.py       # 数据模型
│       │   └── reporter.py     # 报告渲染器（JSON → Markdown）
│       ├── tests/              # 单元测试
│       └── rules/              # 检查规则配置
│           └── ai-checklist.yaml    # AI 检查清单
```

- [ ] **Step 4: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 修复 CLAUDE.md 过期引用和目录结构

- 更新 check_system 描述为 fuck-u-code MCP + AI 统一审查
- 删除已废弃的 scan CLI 命令示例
- 更新 report 命令参数（--quality/--findings 替换 --pre/--ai）
- 更新目录结构为实际存在的文件
- 去掉具体规则数字

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 修复 review.skill.md 和 pipeline.yaml — 去掉规则数字

**Files:**
- Modify: `agents/reviewer/review.skill.md`
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 修改 review.skill.md L30**

将：

```
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（50 条）
```

替换为：

```
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（涵盖结构、质量、认证、基础设施等多维度）
```

- [ ] **Step 2: 修改 pipeline.yaml L71**

将：

```
2. 读取 agents/reviewer/check_system/rules/ai-checklist.yaml（50条审查清单）
```

替换为：

```
2. 读取 agents/reviewer/check_system/rules/ai-checklist.yaml（涵盖结构、质量、认证、基础设施等多维度审查清单）
```

- [ ] **Step 3: 提交**

```bash
git add agents/reviewer/review.skill.md agents/scheduler/pipeline.yaml
git commit -m "docs: 去掉 review.skill.md 和 pipeline.yaml 中的具体规则数字

用维度描述替换 "50条"，避免规则数量变更后文档过期。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 修复 build.skill.md — 删除不存在的 --continue 引用

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 修改 L224**

将错误处理表中的行：

```
| `/build --continue` 无状态 | 「没有可续接的流水线，请使用 /build <需求> 开始新的构建」 |
```

替换为：

```
| `/build --resume` 无状态 | 「没有可续接的流水线，请使用 /build <需求> 开始新的构建」 |
```

- [ ] **Step 2: 提交**

```bash
git add agents/scheduler/build.skill.md
git commit -m "docs: 修正 build.skill.md 中不存在的 --continue 参数引用

--continue 从未实现，实际参数为 --resume。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 更新 README.md — 修复过期数字 + 增强快速上手

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 修复 L58 — "核心价值"表格中的数字**

将：

```
| 双层审查 | Layer 1 程序预检（46 条规则，零 AI Token）+ Layer 2 AI 语义检查（50 条规则） |
```

替换为：

```
| 双层审查 | Layer 1 fuck-u-code MCP 静态分析（零 AI Token）+ Layer 2 AI 统一语义审查 |
```

- [ ] **Step 2: 修复 L86-L98 — "双层审查防线"中的数字**

将：

```
Layer 1: 程序预检（Python CLI）
  ├── 46 条确定性规则，正则 + 模式匹配
  ├── 零 AI Token，零误报
  └── 覆盖「有没有」问题 — 注解缺失、结构违反、命名错误

         ↓ 通过后

Layer 2: AI 语义审查（Review Agent）
  ├── 50 条检查清单，逐项对照
  ├── 理解代码意图和上下文
  └── 覆盖「对不对」问题 — 日志质量、异常处理正确性、认证安全
```

替换为：

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

- [ ] **Step 3: 修复 L220 — 项目结构中 check_system 部分**

将：

```
│   │       ├── rules/                  #   检查规则（YAML 格式）
│   │       │   ├── program-checks.yaml #     46 条程序检查规则（确定性，零误报）
│   │       │   └── ai-checklist.yaml   #     50 条 AI 检查清单（语义理解）
│   │       ├── hooks/                  #   Pre/Post Hook 脚本
```

替换为：

```
│   │       ├── rules/                  #   检查规则（YAML 格式）
│   │       │   └── ai-checklist.yaml   #     AI 检查清单（涵盖结构、质量、认证、基础设施等多维度）
```

- [ ] **Step 4: 修复 L349-L352 — 核心工作流中的数字**

将：

```
│  Phase 2:        │  Layer 1: Python CLI 程序预检 → 46 条确定性规则
│  Reviewer Agent  │  Layer 2: AI 语义审查 → 50 条检查清单逐项确认
```

替换为：

```
│  Phase 2:        │  Layer 1: fuck-u-code MCP 静态分析
│  Reviewer Agent  │  Layer 2: AI 统一审查 → 对照 ai-checklist.yaml 逐项确认
```

- [ ] **Step 5: 修复 L367 — --continue 引用**

将：

```
- **状态持久化**：pipeline-state.json 记录当前进度，支持 `/build --continue` 续接中断的流水线
```

替换为：

```
- **状态持久化**：pipeline-state.json 记录当前进度，支持 `/build --resume` 续接中断的流水线
```

- [ ] **Step 6: 修复 L391-L392 — /review 流程中的数字**

将：

```
│  Step 2: AI 统一审查            │
│  输入:                         │
│  · ai-checklist.yaml（50条）    │
```

替换为：

```
│  Step 2: AI 统一审查            │
│  输入:                         │
│  · ai-checklist.yaml           │
```

- [ ] **Step 7: 修复 L461 — "50 条语义规则"**

将：

```
### Layer 1: AI 检查清单（50 条语义规则）
```

替换为：

```
### Layer 1: AI 检查清单
```

- [ ] **Step 8: 修复 L633 — 另一个 --continue 引用**

将：

```
- **状态持久化**：JSON 文件记录完整状态，支持 `/build --continue` 断点续接
```

替换为：

```
- **状态持久化**：JSON 文件记录完整状态，支持 `/build --resume` 断点续接
```

- [ ] **Step 9: 增强"快速上手"章节 — 添加更详细的引导**

在"环境要求"表格之后、"安装"代码块之后，"三种使用方式"之前，将安装步骤改为更详细的内容。

将现有的安装代码块：

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/workflow-agent-demo.git
cd workflow-agent-demo

# 2. 安装调度引擎依赖
pip install -r agents/scheduler/requirements.txt

# 3. 安装审查系统依赖
cd agents/reviewer/check_system
pip install pyyaml
cd ../../..

# 4. 安装 MCP 依赖（可选 — 用于 fuck-u-code 静态分析）
npm install -g fuck-u-code-mcp
```

替换为：

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/workflow-agent-demo.git
cd workflow-agent-demo

# 2. 安装 Python 依赖
pip install pyyaml
# 调度引擎只需要 PyYAML，无需额外安装

# 3. 配置 MCP（可选但推荐 — 用于 fuck-u-code 静态分析）
# 编辑 .mcp.json 或通过 Claude Code 的 MCP 配置面板添加 fuck-u-code 服务器
# 参考: https://github.com/your-username/fuck-u-code
```

同时在"安装"之后新增一个子章节：

```markdown
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

`/build` 命令会在首次运行时自动创建 `review-output/` 目录。如果需要手动创建：

```bash
mkdir -p review-output
```
```

- [ ] **Step 10: 提交**

```bash
git add README.md
git commit -m "docs: 修复 README.md 过期数字和引用，增强快速上手章节

- 去掉所有具体规则数字（46条、50条），改为维度描述
- 更新双层审查描述为 fuck-u-code MCP + AI 统一审查
- 修正 --continue 为 --resume
- 删除对 program-checks.yaml 的引用
- 增强安装步骤和验证指引

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 全局复查 — 确保无遗漏

**Files:**
- 无新建/修改，仅验证

- [ ] **Step 1: 检查是否还有对已删除文件的引用**

```bash
grep -rn "scanner\.py\|program-checks\|code-check-config\.yaml" --include="*.md" --include="*.yaml" --include="*.py" . && echo "FOUND - needs review" || echo "CLEAN"
```

预期：仅在 git 历史或无关上下文中出现，无功能性引用。如果 `program-checks` 在 `ai-checklist.yaml` 的注释中出现（作为来源说明），可以保留。

- [ ] **Step 2: 检查是否还有具体规则数字（46、50 等）**

```bash
grep -rn "46 条\|50 条\|46条\|50条\| 50 \| 46 " --include="*.md" . && echo "FOUND - needs review" || echo "CLEAN"
```

预期：CLEAN。

- [ ] **Step 3: 检查 --continue 引用**

```bash
grep -rn "\-\-continue" --include="*.md" . && echo "FOUND - needs review" || echo "CLEAN"
```

预期：CLEAN（或仅在非本项目上下文中出现）。

- [ ] **Step 4: 检查 tree-sitter 引用**

```bash
grep -rn "tree.sitter" --include="*.txt" --include="*.py" . && echo "FOUND - needs review" || echo "CLEAN"
```

预期：CLEAN。

- [ ] **Step 5: 如有遗漏，修复并提交；如全部 CLEAN，标记完成**

```bash
# 如果一切 CLEAN，无需额外提交
echo "复查完成，无遗漏"
```
