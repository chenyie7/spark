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
