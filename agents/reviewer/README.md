# 代码审查系统

> 双层校验：程序预检（零 AI Token）+ AI 语义检查，确保代码遵守 `agents/coder/` 中定义的开发规范。

---

## 一、审查架构

```
┌─────────────────────────────────────────────────────┐
│                  /review <path>                      │
│                 (review.skill.md)                    │
├─────────────────────────────────────────────────────┤
│  Layer 1: 程序预检 (check_system/)                    │
│  Python CLI · 零 AI Token · 确定性"有没有"问题         │
│  6 种扫描器 · 39 条规则 · P0/P1 阻断                  │
├─────────────────────────────────────────────────────┤
│  Layer 2: AI 检查清单 (check_system/rules/)           │
│  Review Agent · 语义理解 · "对不对"问题                │
│  17 条规则 · PASS/FAIL/NA 判定                       │
├─────────────────────────────────────────────────────┤
│  输出: review-output/final-review-report.md          │
└─────────────────────────────────────────────────────┘
```

---

## 二、快速使用

### 开启/关闭 Hook

```
/review:on   → 安装 PostToolUse hook，每次 Write/Edit Java 文件后自动预检
/review:off  → 移除 hook
```

### 手动扫描

```bash
cd agents/reviewer/check_system

# 扫描指定目录
python3 -m code_check.cli scan ../../../src/main/java

# 使用默认配置扫描（从 code-check-config.yaml 读取路径）
python3 -m code_check.cli scan

# 生成最终报告
python3 -m code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```

### 完整审查流程

```
/review <path>   → 程序预检 → AI 语义检查 → 合并报告
```

---

## 三、配置

编辑 `check_system/code-check-config.yaml`：

```yaml
strategy: strict          # strict | normal | loose（阻断策略）
default_scan_path: ../../../src/main/java   # 默认扫描路径
exclude:                  # 排除目录
  - "**/test/**"
  - "**/target/**"
```

阻断策略：
- `strict`：P0 或 P1 → 阻断，Review Agent 不启动
- `normal`：仅 P0 → 阻断
- `loose`：仅 P0 阻断，跳过 P2 规则

---

## 四、规则体系

### 程序检查规则（39 条，6 种扫描器）

| 扫描器 | 覆盖维度 | 规则数 |
|--------|---------|:--:|
| `text-grep` | 行级正则匹配（日志、注入、密码等） | 24 |
| `java-annotation` | 注解检查（校验、日志、Swagger 等） | 11 |
| `java-return-type` | Controller 返回类型（Result<T>） | 2 |
| `package-structure` | 包结构（标准子包、service/impl） | 2 |
| `file-naming` | 文件命名（Controller/Service/Mapper 等） | 8 |
| `config-check` | 配置文件（明文密码、knife4j 等） | 3 |

> 规则定义：`check_system/rules/program-checks.yaml`

### AI 检查清单（17 条，4 个维度）

| 维度 | 规则数 |
|------|:--:|
| 分层架构 | 3 |
| 异常处理 | 5 |
| 日志质量 | 2 |
| 代码质量 | 5 |
| 数据库规范 | 2 |

> 规则定义：`check_system/rules/ai-checklist.yaml`

### 严重级别

| 级别 | 含义 | 处理 |
|------|------|------|
| P0 | 安全漏洞、崩溃、数据错误 | 必须修复 |
| P1 | 违反核心规范、可能导致线上问题 | 强烈建议修复 |
| P2 | 风格建议、轻微改进 | 可议 |

---

## 五、目录结构

```
reviewer/
├── README.md                    # 本文件
├── review.skill.md              # /review 斜杠命令定义
├── check_system/                # 双层校验系统
│   ├── code_check/              # Python 包
│   │   ├── cli.py               # CLI 入口（scan + report）
│   │   ├── scanner.py           # 6 种扫描器引擎
│   │   ├── config.py            # 配置加载器
│   │   ├── models.py            # 数据模型
│   │   └── reporter.py          # 报告生成器（Markdown）
│   ├── rules/                   # 检查规则
│   │   ├── program-checks.yaml  # 程序检查规则（39 条）
│   │   ├── ai-checklist.yaml    # AI 检查清单（17 条）
│   │   └── review-prompt.md     # AI 审查指令模板
│   ├── tests/                   # 126 个测试
│   └── code-check-config.yaml  # CLI 配置文件
├── hooks/                       # Git Hook 脚本
│   ├── settings.template.json   # Hook 配置模板（/review:on 使用）
│   ├── review-pre-hook.sh       # 程序预检脚本
│   └── review-post-hook.sh      # 报告合并脚本
├── structure-check.md           # [参考] 结构审查规范原文
├── quality-check.md             # [参考] 质量审查规范原文
├── auth-check.md                # [参考] 认证审查规范原文
└── infra-check.md               # [参考] 基础设施审查规范原文
```

> `*check.md` 文件为原始规范文档，规范内容已编码到 `check_system/rules/` 中。保留作为参考，备份分支：`backup/original-reviewer-files`。

---

## 六、编码体系

每条检查项有唯一编码 `BE-{维度}-{序号}`：

| 编码前缀 | 维度 |
|:--|------|
| `BE-ST-` | 结构审查 |
| `BE-QL-` | 质量审查 |
| `BE-AU-` | 认证审查 |
| `BE-IN-` | 基础设施审查 |

---

## 七、审查原则

- **对照规范，不凭经验**：每条问题对应具体规则文件
- **区分强制和建议**：P0 阻断，P1 强烈建议，P2 可议
- **双层互补**：程序检查覆盖确定性"有没有"，AI 覆盖语义"对不对"
- **只检查不修改**：审查不自动修复代码，除非用户明确要求
