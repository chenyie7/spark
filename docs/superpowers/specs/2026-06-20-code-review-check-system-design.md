# 代码审查框架 —— 双层校验系统设计

> 目标：解决 AI 编码时因注意力机制导致的规范遗漏问题（如忘记加 JSR303 校验），在 coder 写完代码后、reviewer 执行前，增加一道自动化校验门，输出结构化审查报告。

---

## 一、问题背景

现有架构中，coder 按规范写代码，reviewer 事后审查。但两个环节都依赖 AI 的"注意力"：

- Coder 可能因注意力遗漏导致生成代码缺少规范要求的注解（如 `@Validated`、`Result<T>` 等）
- Reviewer 做多维度审查时，46 个检查项全靠"自由回忆"，也可能在注意力漂移中漏掉检查项

**核心痛点：** 自由回忆 → 不可靠；需要变成 逐项确认 → 可靠。

---

## 二、整体架构

```
agents/reviewer/check_system/rules/
├── program-checks.yaml       # 程序检查规则（确定性，零 AI 参与）
└── ai-checklist.yaml         # AI 检查清单模板（语义理解，逐项确认）

执行流程:

  /review 命令
    │
    ▼
┌─────────────────────────────────────────────┐
│  Pre-hook: 程序预检（Python CLI）             │
│  → 读取 program-checks.yaml                  │
│  → 扫描目标目录下所有 Java 文件                │
│  → 输出 pre-check-result.json                │
│  → 判断阻断策略                               │
│      │                                        │
│      ├── 阻断（有阻断级问题）                   │
│      │    → 直接生成 pre-check-report.md       │
│      │    → 通知用户，Review Agent 不启动      │
│      │    → 零 AI Token 消耗                   │
│      │                                        │
│      └── 通过                                 │
│           → pre-check-result.json 传给下一步     │
└─────────────────────────────────────────────┘
    │ (通过)
    ▼
┌─────────────────────────────────────────────┐
│  Review Agent: AI 检查清单                   │
│  → 输入: Java 代码 + pre-check-result.json    │
│          + ai-checklist.yaml                 │
│  → AI 逐项确认，只处理 check_type=ai 的项目     │
│  → 输出: review-result.json（纯数据，无装饰）   │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Post-hook: 报告生成（Python CLI，零 AI Token）│
│  → 读取 pre-check-result.json                │
│  → 读取 review-result.json                   │
│  → 判断阻断策略 → 最终结论                     │
│  → 按模板输出 final-review-report.md          │
└─────────────────────────────────────────────┘
```

### 关键设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 程序检查 vs AI 检查 | 分成两个配置文件，各司其职 | 程序检查确定性，不需 AI 再看 |
| 阻断策略 | strict/normal/loose 三档，yaml 可配 | 适应不同质量要求的项目 |
| AI 输出 | 纯 JSON，禁止 icon/emoji/表格 | 节省 Token，装饰由脚本负责 |
| Markdown 报告 | Post-hook Python 脚本生成 | 零 AI Token |
| 两份报告分开展示 | 不合并 | 来源不同，责任不同 |
| 触发方式 | `/review` 命令 + Pre-hook | 用户显式控制，精确命中 |
| 预检阻断时 | 直接返回报告，不启动 Review Agent | 确定性错误不需要 AI 兜底，节省 Token |
| AI 不重复程序结果 | 去掉 ALREADY_FOUND 冗余 | 信息已在程序预检 JSON 中 |
| reviewer 规范文件 | 保持不动 | 作为真相数据源，只读 |
| 实现语言 | Python 3，做成 CLI | 轻量、零编译、改完就跑 |

---

## 三、阻断策略

三档可配置，拒绝写死：

| 策略 | 阻断条件 | 适用场景 |
|------|---------|---------|
| strict | 有 P0 或 P1 → 阻断 | 代码质量要求高，如核心业务模块 |
| normal | 有 P0 → 阻断，P1/P2 放行 | 一般业务开发 |
| loose | 仅 P0 阻断 | 快速迭代，允许风格差异 |

阻断时：输出报告，流程结束，不启动 Review Agent。不阻断时：带着警告继续执行 AI 检查。

---

## 四、检查类型分工

### 程序检查（program-checks.yaml）

**负责：** 确定性的"有没有"问题，正则 + 模式匹配即可判断，零歧义。

| 检查类型 | 示例 | 扫描方式 |
|---------|------|---------|
| 注解缺失 | Controller DTO 参数缺 `@Validated` | 上下文扫描 |
| 类型不匹配 | 返回值不是 `Result<T>` | 方法签名匹配 |
| 禁止调用 | `System.out.println` | 文本 grep |
| 禁止注解 | `@Autowired` 字段注入 | 注解扫描 |
| 模式违规 | 工具类不是 `final + 私有构造` | 类结构扫描 |

**配置结构示例：**

```yaml
BE-QL-29:
  description: "Controller 方法的 DTO 参数是否加了 @Validated 或 @Valid"
  level: P1
  program:
    scanner: "java-annotation"
    on_class: "RestController|Controller"
    target: "method_param"
    match_param_type: "DTO|Request|Command"
    missing_annotation: "@Validated|@Valid"
  message: "{method} 缺少 @Validated/@Valid 注解 DTO 参数"
```

### AI 检查（ai-checklist.yaml）

**负责：** 需要语义理解的"对不对"问题——程式无法判断，需要 AI 理解代码意图。

| 检查类型 | 示例 |
|---------|------|
| 日志质量 | `log.info` 是否包含关键业务信息 |
| 异常处理正确性 | Service catch 后是否只打日志不抛出 |
| 集合返回安全 | 集合返回值是否为 null |
| 魔法数字 | `if (status == 1)` 是否应提取为枚举 |
| 代码重复 | 跨文件出现 2 次以上的字符串是否应提取常量 |

**配置结构示例：**

```yaml
BE-QL-11:
  description: "log.info 是否包含关键业务信息（如 orderId、userId）"
  level: P2
  ai:
    prompt_hint: "检查每个 log.info 语句的参数是否包含了当前操作的关键业务标识（如订单号、用户ID等），而非仅打印静态文本"
```

### 程序线索注入

程序预检结果中的 `hints_for_ai` 字段，用于帮助 AI 聚焦注意力——程序扫出可疑行（如含 `token` 关键词的日志），标注后注入给 AI 做参考，但最终判断由 AI 做出。

---

## 五、结构化输出格式

### 程序预检输出（pre-check-result.json）

由 Python CLI 生成，零 AI Token。

```json
{
  "metadata": {
    "module": "user-management",
    "scan_scope": {
      "base_path": "src/main/java/com/example/user",
      "file_count": 12,
      "breakdown": {
        "controller": 2,
        "service": 3,
        "mapper": 2,
        "entity": 2,
        "dto": 3
      }
    },
    "timestamp": "2026-06-20T10:30:00Z",
    "blocking_strategy": "strict",
    "passed": false
  },
  "file_reports": [
    {
      "file": "UserController.java",
      "findings": [
        {
          "code": "BE-QL-29",
          "level": "P1",
          "line": 24,
          "method": "createUser",
          "message": "createUser 缺少 @Validated/@Valid 注解 DTO 参数",
          "evidence": "public Result<Void> createUser(CreateUserDTO dto)"
        }
      ]
    }
  ],
  "summary": {
    "total_checks": 25,
    "passed": 22,
    "failed": [
      {"code": "BE-QL-29", "count": 2},
      {"code": "BE-QL-13", "count": 1}
    ]
  },
  "hints_for_ai": [
    {
      "file": "UserController.java",
      "line": 45,
      "code": "BE-QL-09",
      "snippet": "log.info(\"用户登录成功，token: {}\", token);"
    }
  ]
}
```

**设计原则：**
- `scan_scope` 用结构化统计替代文件名大数组，避免数组膨胀
- `file_reports` 只包含有问题的文件，通过的文件不出现
- `evidence` 截取关键代码行，不截取大段代码
- `hints_for_ai` 只提供给 AI 做注意力线索，不是检查结论

### AI 检查输出（review-result.json）

Review Agent 输出，纯数据 JSON。

```json
{
  "metadata": {
    "module": "user-management",
    "timestamp": "2026-06-20T10:35:00Z",
    "precheck_passed": false,
    "precheck_issues": ["BE-QL-29 (x2)", "BE-QL-13 (x1)"]
  },
  "items": [
    {
      "code": "BE-QL-11",
      "category": "日志",
      "result": "FAIL",
      "file": "UserServiceImpl.java",
      "line": 67,
      "evidence": "log.info(\"更新完成\");",
      "suggestion": "应改为 log.info(\"用户信息更新完成, userId={}\", userId);"
    },
    {
      "code": "BE-QL-11",
      "category": "日志",
      "result": "PASS",
      "file": "UserServiceImpl.java",
      "line": 34,
      "evidence": "log.info(\"创建用户成功, username={}\", dto.getUsername());",
      "suggestion": null
    }
  ],
  "summary": {
    "total": 21,
    "pass": 19,
    "fail": 2,
    "na": 0
  }
}
```

**设计原则：**
- AI 只输出自己负责的 check_type=ai 检查项，不重复程序已发现的内容
- `result` 只有三种值：`PASS` / `FAIL` / `NA`
- 所有字段为纯文本，禁止 icon/emoji/markdown 格式
- `suggestion` 在 PASS 时为 null

---

## 六、Markdown 报告模板

由 Post-hook Python 脚本从两份 JSON 生成，零 AI Token。

### 整体结构（固定顺序，不可变）

```
1. 标题 + 元信息块
2. 程序预检章节
3. AI 检查章节
4. 汇总章节
5. 结论
```

### 模板

```markdown
# 代码审查报告

| 属性 | 值 |
|------|-----|
| 模块 | {module_name} |
| 扫描范围 | {base_path}（{file_count} 个文件） |
| 阻断策略 | {strategy} |
| 检查时间 | {timestamp} |
| 结论 | {pass_icon} {conclusion_text} |

---

## 一、程序预检

> 确定性规则匹配，零 AI 参与

| 编码 | 级别 | 文件:行号 | 方法 | 问题 | 证据 |
|------|------|----------|------|------|------|
| {code} | {level_icon} | {file}:{line} | {method} | {message} | `{evidence}` |

**程序预检统计**: 检查 {total} 项 | 通过 {pass} | 未通过 {fail}

---

## 二、AI 检查

> 语义理解检查，基于 ai-checklist.yaml 逐项确认

| 编码 | 分类 | 结果 | 文件:行号 | 问题 | 修复建议 |
|------|------|------|----------|------|---------|
| {code} | {category} | {result_icon} | {file}:{line} | {description} | {suggestion} |

**AI 检查统计**: 检查 {total} 项 | 通过 {pass} | 未通过 {fail} | 不适用 {na}

---

## 三、汇总

| 来源 | 🔴 P0 | 🟡 P1 | 🟢 P2 | 小计 |
|------|-------|-------|-------|------|
| 程序预检 | {pre_p0} | {pre_p1} | {pre_p2} | {pre_total} |
| AI 检查 | {ai_p0} | {ai_p1} | {ai_p2} | {ai_total} |
| **合计** | {sum_p0} | {sum_p1} | {sum_p2} | {sum_total} |

---

## 四、结论

**{pass_or_fail}** — {detail}

{修复指引（失败时显示）}
```

### 渲染规则

| 规则 | 说明 |
|------|------|
| level_icon | P0 → 🔴，P1 → 🟡，P2 → 🟢 |
| result_icon | PASS → ✅，FAIL → ❌，NA → ➖ |
| 程序预检表格 | 按 level 降序，同级按 code 升序 |
| AI 检查表格 | 按 category 分组，组内按 code 升序 |
| PASS 项 | 不出现在表格中（减少冗余行） |
| 全部通过 | 表格替换为 "✅ 检查 {total} 项，全部通过，无问题发现。" |

### 结论规则

| 场景 | pass_or_fail | detail | 修复指引 |
|------|-------------|--------|---------|
| 通过 | ✅ 通过 | 所有检查项通过，代码质量符合规范。 | 不显示 |
| 程序预检阻断 | ❌ 未通过 | 程序预检发现 {n} 个问题，其中阻断级 {m} 个。 | 请先修复以上 **程序预检** 中标记的问题，再重新执行检查。 |
| AI 检查有建议 | ⚠️ 通过（有建议） | 程序预检通过，AI 检查发现 {n} 个建议项。 | 以上 **AI 检查** 中标记的项目为建议修复，不阻塞流程。 |

### 边界情况

| 边界情况 | 处理方式 |
|---------|---------|
| 无 Java 文件 | file_count: 0，结论为"无文件可检查" |
| 检查规则为空 | 显示"无检查规则配置" |
| AI JSON schema 不匹配 | AI 检查章节改为"AI 检查输出格式异常，无法解析" |
| 全部 PASS/NA | 汇总正常，结论为通过 |

---

## 七、AI 输出约束

Review Agent 输出 JSON 时必须遵守：

- **禁止字段：** icon、emoji、markdown 表格、多级标题、代码块
- **result 枚举：** 只能是 `PASS` / `FAIL` / `NA`
- **suggestion 规则：** PASS 时为 `null`，FAIL 时必填
- **不重复程序结果：** 不输出已在 `pre-check-result.json` 中标记为 FAIL 的检查项
- **文件/行号：** 必填，用来定位；找不到明确位置时填 `"-"`

---

## 八、Hook 配置设计

### 工作流

```
/review <path> → Pre-hook → Review Agent → Post-hook → 最终报告
```

### Pre-hook

```
命令: code-check scan <path> --strategy strict --format json
输入: program-checks.yaml + Java 源文件
输出: pre-check-result.json
行为:
  - 有阻断问题 → 生成 pre-check-report.md，阻止 Review Agent 启动
  - 通过 → 将 pre-check-result.json 传给 Review Agent
```

### Post-hook

```
命令: code-check report --pre pre-check-result.json --ai review-result.json --output final-review-report.md
输入: 两份 JSON
输出: final-review-report.md
行为: 纯数据合并 + 模板填充，零 AI 参与
```

---

## 九、CLI 接口设计

所有 CLI 命令以 `code-check` 为入口，配置有三级优先级：

```
命令行参数  >  配置文件  >  内置默认值
```

### 简化使用

```bash
# 有配置文件时，最简用法：
code-check scan src/main/java/com/example/user

# 等价于完整写法（无需手写长串参数）：
code-check scan src/main/java/com/example/user \
  --rules-dir agents/reviewer/check_system/rules/ \
  --strategy strict \
  --format json \
  --output ./review-output/
```

### 命令

```
code-check scan <path> [options]
  --rules-dir     规则目录路径（默认: agents/reviewer/check_system/rules/）
  --strategy      strict|normal|loose（默认: strict）
  --format        json|md（默认: json）
  --output        输出目录路径（默认: ./review-output/）
  --config        配置文件路径（默认: agents/reviewer/check_system/code-check-config.yaml）

code-check report [options]
  --pre           程序预检 JSON 路径
  --ai            AI 检查 JSON 路径
  --output        输出 Markdown 路径
  --config        配置文件路径（默认: agents/reviewer/check_system/code-check-config.yaml）
```

### CLI 配置文件（code-check-config.yaml）

放在项目根目录，命令行参数为空时自动读取默认值：

```yaml
# code-check 配置文件 —— 放在项目根目录

# 检查规则目录
rules_dir: agents/reviewer/check_system/rules/

# 阻断策略：strict | normal | loose
strategy: strict

# 输出目录
output_dir: ./review-output/

# 输出格式（scan 命令默认输出）：json | md
format: json

# 扫描排除目录
exclude:
  - "**/test/**"
  - "**/target/**"
  - "**/node_modules/**"

# 默认扫描路径（不传 path 参数时使用）
# default_path: src/main/java/
```

**工作方式：**
1. CLI 启动先读 `agents/reviewer/check_system/code-check-config.yaml`（如果存在）
2. 用户传了命令行参数 → 覆盖配置文件的对应值
3. 都没传 → 使用内置默认值
4. Hook 调用时只需 `code-check scan <path>`，配置自动生效

---

## 十、需要新建的文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `agents/reviewer/check_system/code-check-config.yaml` | 配置 | CLI 默认配置文件，简化日常使用，避免重复传参 |
| `agents/reviewer/check_system/rules/program-checks.yaml` | 配置 | 程序检查规则定义，从 reviewer 规范提取可机械化检查的项 |
| `agents/reviewer/check_system/rules/ai-checklist.yaml` | 配置 | AI 检查清单模板，从 reviewer 规范提取需语义理解的项 |
| `agents/reviewer/check_system/code_check/__init__.py` | Python | CLI 包入口 |
| `agents/reviewer/check_system/code_check/scanner.py` | Python | Java 文件扫描引擎，读取 yaml 执行匹配 |
| `agents/reviewer/check_system/code_check/reporter.py` | Python | 报告生成模块，JSON → Markdown 转换 |
| `agents/reviewer/check_system/code_check/cli.py` | Python | 命令行接口，click/argparse |
| `hooks/review-pre-hook.sh` | Hook | Pre-hook 入口脚本 |
| `hooks/review-post-hook.sh` | Hook | Post-hook 入口脚本 |

---

## 十一、reviewer 规范文件的定位

| | 现在的角色 | 设计后的角色 |
|---|---|---|
| review/*.md | AI 阅读执行的检查说明书 | 检查系统的数据源和真相源 |
| 检查项编码 | 文档里的编号 | 程序脚本和 AI 清单共用的唯一标识 |
| 级别 P0/P1/P2 | 给人看的标签 | 脚本的阻断规则输入 |
| 错误消息模板 | 参考文案 | 程序/AI 输出报告的消息模板 |

**reviewer 规范文件保持不动，只读。** 新增检查项时，在 reviewer 文件加一行 + 在 check-rules 对应 yaml 中加一条规则即可。

---

## 十二、Token 消耗估算

场景：5-8 个 Java 文件的小功能模块

| 环节 | 输入 Token | 输出 Token | 说明 |
|------|-----------|-----------|------|
| 程序预检 | **0** | **0** | Python 脚本，不走 AI |
| AI 检查清单 | 8,500-16,500 | 3,000-8,000 | 含代码 + 清单模板 + 预检报告 |
| 报告生成 | **0** | **0** | Python 脚本 |
| **总计** | **~12,000-25,000** | | |
| 对比现方案 | **+20%-40%** | | 换来 100% 检查覆盖率 |
