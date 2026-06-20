---
name: review
description: 双层代码审查 —— 程序预检阻断 + AI 语义检查，输出完整审查报告
---

# /review — 双层代码审查

## 触发方式

```bash
/review <path>
```

`path` 是要扫描的 Java 代码路径，相对于项目根目录。默认 `src/main/java`。

---

## Step 1: 程序预检（硬阻断）

运行程序预检 CLI。如果预检不通过，**必须立即停止，不执行 Step 2**。

```bash
cd agents/reviewer/check_system
python3 -m code_check.cli scan {path}
```

- `exit 0`：预检通过 → 继续 Step 2
- `exit 1`：预检未通过 → **停止。** 告知用户查看 `review-output/pre-check-report.md`，不执行后续步骤，不消耗 AI Token

---

## Step 2: AI 语义检查

预检通过后，读取 `agents/reviewer/check_system/rules/review-prompt.md`，严格按照其中的指令执行 AI 检查。

核心输入：
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 待检查的语义规则清单（~15 项）
- `review-output/pre-check-result.json` — 程序预检的线索和上下文
- `{path}` 下的 Java 源文件

输出：`review-output/review-result.json`

---

## Step 3: 合并最终报告

```bash
cd agents/reviewer/check_system
python3 -m code_check.cli report \
  --pre review-output/pre-check-result.json \
  --ai review-output/review-result.json \
  --output review-output/final-review-report.md
```

将 `final-review-report.md` 的内容展示给用户。
