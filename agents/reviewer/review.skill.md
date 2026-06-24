---
name: review
description: 双层代码审查 —— 程序预检阻断 + AI 语义检查，输出完整审查报告
---

# /review — 双层代码审查

用法：`/review <path>`，`path` 是要扫描的 Java 代码路径，默认 `src/main/java`。

---

## 执行流程

### Step 1: 程序预检（硬阻断）

执行 Bash 脚本进行确定性规则检查。exit 1 时立即停止，不执行 Step 2。

```bash
bash agents/reviewer/hooks/review-pre-hook.sh {path}
```

- `exit 0`：预检通过，`../../../review-output/{run_id}/pre-check-result.json` 已生成 → 继续 Step 2
- `exit 1`：预检未通过，`../../../review-output/{run_id}/pre-check-result.json` + `../../../review-output/{run_id}/pre-check-report.md` 已生成 → **停止。** 返回 `REVIEW_FAILED`，不执行后续步骤

### Step 2: AI 语义检查

工作目录为 `agents/reviewer/check_system/`（与 Step 1 和 Step 3 保持一致）。产物输出到项目根目录的 `review-output/{run_id}/`，从当前工作目录的引用路径为 `../../../review-output/{run_id}/`。

读取 `agents/reviewer/check_system/rules/review-prompt.md`，严格按照其中的指令执行。

核心输入：
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 语义规则清单（17 项）
- `../../../review-output/{run_id}/pre-check-result.json` — 程序预检的线索和上下文
- `{path}` 下的 Java 源文件

输出：`../../../review-output/{run_id}/review-result.json`

### Step 3: 合并最终报告

```bash
bash agents/reviewer/hooks/review-post-hook.sh
```

将生成的 `../../../review-output/{run_id}/final-review-report.md` 内容展示给用户。

---

## 返回协议

执行完成后，返回以下三种结果之一：

| 返回值 | 含义 |
|--------|------|
| `REVIEW_PASSED` | 预检通过，AI 检查完成，产物完整 |
| `REVIEW_FAILED` | 预检阻断（P0>0），或 AI 检查有 FAIL |
| `REVIEW_ERROR` | 环境/工具异常（python3 不可用、CLI 崩溃等） |
