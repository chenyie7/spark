---
name: review
description: 代码审查 —— fuck-u-code 静态分析 + AI 统一审查，输出完整审查报告
---

# /review — 代码审查

用法：`/review <path>`，`path` 是要扫描的 Java 代码路径，默认 `src/main/java`。

---

## 执行流程

### Step 1: fuck-u-code 静态分析

调用 MCP tool `fuck-u-code analyze` 扫描目标目录。

- 产出 `quality.json`：总体评分、7 维指标、最差文件排行
- 耗时 ~5s，零 Token
- 保存到 `review-output/{run_id}/quality.json`

如果 MCP 调用失败（fuck-u-code 未安装或超时），记录警告，跳过本步，继续 Step 2。
不阻断流程。

### Step 2: AI 统一审查

读取以下输入，执行一次 AI 审查，同时完成规范合规检查和代码深度分析：

**输入：**
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（50 条）
- `review-output/{run_id}/quality.json` — 静态分析结果（如存在）
- `{path}` 下的 Java 源文件

**输出：** `review-output/{run_id}/findings.json`，按以下 schema：

```json
{
  "review_status": "PASSED | FAILED",
  "spec_violations": [
    {
      "rule_id": "BE-QL-14",
      "level": "P0 | P1 | P2",
      "file": "相对路径",
      "line": 42,
      "method": "方法名",
      "description": "问题描述",
      "suggestion": "修复建议"
    }
  ],
  "quality_issues": [
    {
      "file": "相对路径",
      "line": 38,
      "dimension": "N+1查询 | 复杂度 | 重复代码 | ...",
      "severity": "high | medium | low",
      "detail": "问题详情",
      "suggestion": "修复建议"
    }
  ],
  "summary": "AI 给出的总结摘要"
}
```

**判定逻辑：**
- P0 > 0 → `REVIEW_FAILED`
- P1 > 0 且阻断策略 strict → `REVIEW_FAILED`
- 其他 → `REVIEW_PASSED`

### Step 3: 合并最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --quality ../../../review-output/{run_id}/quality.json \
  --findings ../../../review-output/{run_id}/findings.json \
  --output ../../../review-output/{run_id}/final-review-report.md
```

将生成的 `review-output/{run_id}/final-review-report.md` 内容展示给用户。

---

## 返回协议

| 返回值 | 含义 |
|--------|------|
| `REVIEW_PASSED` | 静态分析完成，AI 审查通过，产物完整 |
| `REVIEW_FAILED` | AI 审查发现 P0 问题，或 P1 触发阻断 |
| `REVIEW_ERROR` | 环境/工具异常（python3 不可用、fuck-u-code 未安装且无法继续等） |
