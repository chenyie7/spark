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
│  Python CLI · 零 AI Token · 确定性机械检查               │
│  46 条规则 · P0/P1 阻断 · 零误报                        │
├─────────────────────────────────────────────────────┤
│  Layer 2: AI 检查清单 (check_system/rules/)           │
│  Review Agent · 语义理解 · "对不对"问题                │
│  23 条规则 · PASS/FAIL/NA 判定                       │
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

所有规则以 YAML 格式统一管理在 `check_system/rules/` 目录下，分为两大类：

### 程序检查规则（Scanner — 零误报、纯机械匹配）

程序检查只包含「100% 确定」的机械性规则，报出来的就是问题，不会有误报。

> Scanner 规则：`check_system/rules/program-checks.yaml`（46 条）

> Scanner 阻断级别：P0（安全/崩溃/数据错误）、P1（违反核心规范）

### AI 语义检查清单（AI — 需要理解代码意图和上下文）

AI 检查覆盖程序判断不了的语义问题，能理解「这个 Service 是否真的在处理密码」「这个场景该用 StpUtil 还是 StpKit」等语境。

> AI 规则：`check_system/rules/ai-checklist.yaml`（23 条）

> AI 检查指令模板：`check_system/rules/review-prompt.md`

| 维度 | Scanner 规则数 | AI 规则数 |
|------|:--:|:--:|
| 结构审查 (BE-ST) | 10 | 4 |
| 质量审查 (BE-QL) | 17 | 13 |
| 基础设施 (BE-IN) | 13 | 0 |
| 认证安全 (BE-AU) | 6 | 2 |

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
│   │   ├── scanner.py           # Scanner 引擎（AST + 结构 + 命名 + 配置）
│   │   ├── config.py            # 配置加载器
│   │   ├── models.py            # 数据模型
│   │   └── reporter.py          # 报告生成器（Markdown）
│   ├── rules/                   # 检查规则（纯 YAML 格式）
│   │   ├── program-checks.yaml  # Scanner 规则（46 条 — 零误报机械检查）
│   │   ├── ai-checklist.yaml    # AI 检查清单（23 条 — 语义理解）
│   │   └── review-prompt.md     # AI 审查指令模板
│   ├── tests/                   # 测试
│   └── code-check-config.yaml  # CLI 配置文件
├── hooks/                       # Shell Hook 脚本
│   ├── settings.template.json   # Hook 配置模板（/review:on 使用）
│   ├── review-pre-hook.sh       # 程序预检脚本
│   └── review-post-hook.sh      # 报告合并脚本
```

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
