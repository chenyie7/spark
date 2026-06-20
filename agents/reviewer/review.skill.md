---
name: review
description: 双层代码审查 —— 程序预检阻断 + AI 语义检查，输出完整审查报告
---

# /review — 双层代码审查

支持三种用法：

| 命令 | 作用 |
|------|------|
| `/review` 或 `/review <path>` | 执行完整代码审查流程 |
| `/review:on` | 激活自动预检 hook（每次写 Java 文件后自动跑 pre-check） |
| `/review:off` | 关闭自动预检 hook |

---

## /review:on — 激活自动预检

将 hook 配置复制到 `.claude/settings.json`。**需要重启 Claude Code 才能生效。**

```bash
cp agents/reviewer/hooks/settings.template.json .claude/settings.json
```

生效后，每次 Write/Edit Java 文件（`src/main/java/**/*.java`）时，会自动运行程序预检。

---

## /review:off — 关闭自动预检

删除 `.claude/settings.json`。**需要重启 Claude Code 才能生效。**

```bash
rm .claude/settings.json
```

关闭后，写 Java 文件不再自动触发预检，但仍可使用 `/review` 手动触发。

---

## /review `<path>` — 完整代码审查

`path` 是要扫描的 Java 代码路径，默认 `src/main/java`。

### Step 1: 程序预检（硬阻断）

```bash
cd agents/reviewer/check_system
python3 -m code_check.cli scan {path}
```

- `exit 0`：预检通过 → 继续 Step 2
- `exit 1`：预检未通过 → **停止。** 告知用户查看 `review-output/pre-check-report.md`，不执行后续步骤

### Step 2: AI 语义检查

读取 `agents/reviewer/check_system/rules/review-prompt.md`，严格按照其中的指令执行。

核心输入：
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 语义规则清单（17 项）
- `review-output/pre-check-result.json` — 程序预检的线索和上下文
- `{path}` 下的 Java 源文件

输出：`review-output/review-result.json`

### Step 3: 合并最终报告

```bash
cd agents/reviewer/check_system
python3 -m code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```

将 `final-review-report.md` 的内容展示给用户。
