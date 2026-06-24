# Benchmarks 系统全面改进计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐采集维度（模型、错误）、增加效率指标（修复效率、阶段对比）、修复 reviewer 数据缺失、增加跨运行对比

**Architecture:** 3 个现有文件改造 + 1 个新文件。dump-agent-payload.sh 新增 pipeline 标签字段区分 pipeline Agent vs 开发子 Agent；schema.py 修复缓存公式和 round 推断逻辑，新增效率指标和阶段拆解；新增 compare.py 做跨运行横向对比

**Tech Stack:** Python 3, Bash, JSON, PyYAML

**关键根因分析：**
- reviewer 数据缺失：`_infer_rounds` 用 `review|审查` 正则匹配 description，把 "Spec review Task 1" 等开发子 Agent 也当成 reviewer，导致真实 pipeline coder/reviewer 被搞混。解决方案：在 dump 阶段加 `pipeline_role` 标签（通过检测 subagent_type 和 description 中的关键特征来区分）
- 缓存命中率 973%：公式 `cache_read / input_tokens` 应为 `cache_read / (cache_read + input_tokens)`

---

## 文件结构

```
benchmarks/
├── hooks/
│   ├── dump-agent-payload.sh      # 修改：新增字段采集
│   ├── schema.py                  # 修改：核心逻辑大改
│   ├── synthesize-benchmark.sh    # 修改：配置读取
│   └── compare.py                 # 新增：跨运行对比
├── dumps/                          # 不变
└── run-*.json, run-*.md           # 旧产物保留
```

---

### Task 1: dump-agent-payload.sh — 补齐采集维度 + 区分 pipeline Agent

**Files:**
- Modify: `benchmarks/hooks/dump-agent-payload.sh`

- [ ] **Step 1: 新版 RECORD 构造**

当前 RECORD 只取 9 个字段。替换 RECORD 的 Python inline 脚本为增强版（增加 5 个字段）：

```bash
RECORD=$(echo "$RAW" | python3 -c "
import sys, json, time

d = json.load(sys.stdin)
ti = d.get('tool_input', {})
tr = d.get('tool_response', {})
content = tr.get('content', [])
last_msg = ''
if content and isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            last_msg = block.get('text', '')
            break
last_msg_snippet = last_msg[:500] if last_msg else ''

usage = tr.get('usage', {})

# ── 新增：提取 model 信息 ──
model = usage.get('model', '') or ''
# 从 last_msg 检测判定结果
verdict = ''
if 'REVIEW_PASSED' in last_msg:
    verdict = 'REVIEW_PASSED'
elif 'REVIEW_FAILED' in last_msg:
    verdict = 'REVIEW_FAILED'
elif 'REVIEW_ERROR' in last_msg:
    verdict = 'REVIEW_ERROR'

# ── 新增：检测失败/错误 ──
has_error = 'error' in last_msg[:200].lower() or 'failed' in last_msg[:200].lower() or 'Traceback' in last_msg

# ── 新增：区分 pipeline Agent vs 开发子 Agent ──
desc = ti.get('description', '')
subagent_type = ti.get('subagent_type', '')
# pipeline agent 的特征：description 中包含 'Task' 的是 subagent-driven-development 的任务 Agent
# 真正的 pipeline coder/reviewer 由 build.skill.md 启动，description 不含 'Task'
is_dev_agent = 'Task' in desc and 'Implement' in desc or 'review Task' in desc.lower() or 'Spec review' in desc or 'Code quality review' in desc or 'Fix Task' in desc

rec = {
    'ts': int(time.time()),
    'session_id': d.get('session_id', ''),
    'tool_use_id': d.get('tool_use_id', ''),
    'description': desc,
    'subagent_type': subagent_type,
    'duration_ms': tr.get('totalDurationMs', 0),
    'total_tokens': tr.get('totalTokens', 0),
    'total_tool_uses': tr.get('totalToolUseCount', 0),
    'usage': usage,
    'last_message_snippet': last_msg_snippet,
    # 新增字段
    'model': model,
    'verdict': verdict,
    'has_error': has_error,
    'is_dev_agent': is_dev_agent,
}

print(json.dumps(rec, ensure_ascii=False))
" 2>/dev/null)
```

- [ ] **Step 2: 手动验证 RECORD 输出**

```bash
cd /Users/chenyi/ai-project/workflow-agent-demo && \
echo '{"session_id":"test","tool_use_id":"call_1","tool_input":{"description":"Implement Task 1: something","subagent_type":"general-purpose"},"tool_response":{"totalDurationMs":1000,"totalTokens":500,"totalToolUseCount":2,"usage":{"model":"claude-sonnet-4-6","input_tokens":100,"output_tokens":50},"content":[{"type":"text","text":"Task done. REVIEW_PASSED"}]}}' | \
bash benchmarks/hooks/dump-agent-payload.sh 2>/dev/null && \
cat benchmarks/dumps/session-test.jsonl | python3 -m json.tool
```

验证输出包含 `model`, `verdict`, `has_error`, `is_dev_agent` 字段。

- [ ] **Step 3: 清理测试数据 & Commit**

```bash
rm -f benchmarks/dumps/session-test.jsonl
git add benchmarks/hooks/dump-agent-payload.sh
git commit -m "feat: add model/verdict/error detection and pipeline agent tagging to dump hook

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: schema.py — 修复核心逻辑 + 增加效率指标

**Files:**
- Modify: `benchmarks/hooks/schema.py`

改动点：
1. `_infer_rounds` — 用 `is_dev_agent` 字段过滤开发子 Agent，只保留 pipeline coder/reviewer
2. 新增 `_compute_fix_efficiency` — 计算 tokens/P0-fixed、每轮修复数
3. 新增 `_compute_phase_breakdown` — 按阶段（generate/fix/review）拆解 tokens 和时间
4. `_compute_summary` — 增加新指标
5. `render_md` — 增加阶段拆解表、修复效率表、模型信息
6. 修复缓存命中率公式

- [ ] **Step 1: 修复 _infer_rounds**

在函数的 for 循环开头，过滤开发 Agent：

```python
    for rec in records:
        # 跳过开发子 Agent（subagent-driven-development 的任务 Agent）
        if rec.get("is_dev_agent"):
            continue

        desc = rec.get("description", "")
        is_reviewer = bool(REVIEW_PATTERNS.search(desc))
        # ... 后续逻辑不变
```

- [ ] **Step 2: 修复 _compute_summary 中的缓存命中率公式**

将：
```python
cache_ratio = (total_cache_read / total_input) if total_input > 0 else 0.0
```

改为：
```python
total_cache_base = total_cache_read + total_input
cache_ratio = (total_cache_read / total_cache_base) if total_cache_base > 0 else 0.0
```

- [ ] **Step 3: 新增 _compute_fix_efficiency 函数**

在 `_compute_convergence` 函数之后添加：

```python
def _compute_fix_efficiency(rounds: list[dict]) -> dict:
    """计算修复效率指标。

    Returns:
        {
            "tokens_per_p0_fixed": float | None,   # 每修复一个 P0 消耗的 tokens
            "new_issues_per_fix_round": list[int],  # 每修复轮引入的新问题数
            "p0_reduction_rate": float | None,      # P0 减少速率（每轮）
        }
    """
    fix_rounds = []
    p0_series = []

    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            issues = rv.get("issues", {})
            p0 = issues.get("P0", 0)
            p0_series.append(p0)

        coder = r.get("coder")
        if coder is not None and coder.get("phase") == "fix":
            fix_rounds.append(r)

    # tokens per P0 fixed
    tokens_per_p0 = None
    if len(p0_series) >= 2:
        total_fix_tokens = sum(
            r["coder"]["total_tokens"] for r in fix_rounds
            if r.get("coder") is not None
        )
        p0_fixed = p0_series[0] - p0_series[-1]
        if p0_fixed > 0:
            tokens_per_p0 = round(total_fix_tokens / p0_fixed)

    # P0 reduction rate per round
    reduction_rate = None
    if len(p0_series) >= 2 and p0_series[0] > 0:
        n = len(p0_series) - 1
        reduction_rate = round((p0_series[0] - p0_series[-1]) / p0_series[0] * 100, 1)

    # New issues introduced (P1/P2 increase during fix rounds)
    new_issues_per_fix = []
    prev_total = None
    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            issues = rv.get("issues", {})
            current_total = issues.get("P1", 0) + issues.get("P2", 0)
            if prev_total is not None and current_total > prev_total:
                new_issues_per_fix.append(current_total - prev_total)
            else:
                new_issues_per_fix.append(0)
            prev_total = current_total

    return {
        "tokens_per_p0_fixed": tokens_per_p0,
        "p0_reduction_rate_pct": reduction_rate,
        "new_issues_per_fix_round": new_issues_per_fix,
    }
```

- [ ] **Step 4: 新增 _compute_phase_breakdown 函数**

```python
def _compute_phase_breakdown(rounds: list[dict]) -> dict:
    """按阶段拆解 tokens 和时间。

    Returns:
        { "generate": {...}, "fix": {...}, "review": {...} }
    """
    breakdown = {}
    for phase_name in ("generate", "fix", "review"):
        breakdown[phase_name] = {
            "calls": 0,
            "total_tokens": 0,
            "total_duration_ms": 0,
        }

    for r in rounds:
        for role_key in ("coder", "reviewer"):
            entry = r.get(role_key)
            if entry is None:
                continue
            phase = entry.get("phase", "")
            if phase in breakdown:
                breakdown[phase]["calls"] += 1
                breakdown[phase]["total_tokens"] += entry.get("total_tokens", 0)
                breakdown[phase]["total_duration_ms"] += entry.get("duration_ms", 0)

    # 去掉 0 调用的阶段
    return {k: v for k, v in breakdown.items() if v["calls"] > 0}
```

- [ ] **Step 5: 更新 from_jsonl 集成新函数**

在 `from_jsonl` 函数中，rounds 推断之后添加 issue 挂载的上方，新增：

```python
    # 4b. 修复效率
    fix_efficiency = _compute_fix_efficiency(rounds)

    # 4c. 阶段拆解
    phase_breakdown = _compute_phase_breakdown(rounds)
```

更新 return dict，在 `"summary"` 之前添加：

```python
        "fix_efficiency": fix_efficiency,
        "phase_breakdown": phase_breakdown,
```

- [ ] **Step 6: 更新 _compute_summary 增加模型信息**

在 `_compute_summary` 中增加提取模型名的逻辑。函数签名增加 `records` 参数来获取 model 信息：

```python
def _compute_summary(rounds: list[dict], convergence: dict, records: list[dict] = None) -> dict:
```

在汇总 stats 循环之后、return 之前，新增模型汇总：

```python
    # 模型使用统计
    models_used = {}
    if records:
        for rec in records:
            model = rec.get("model", "")
            if model:
                models_used[model] = models_used.get(model, 0) + 1
```

在 return dict 中添加：
```python
        "models_used": models_used,
```

- [ ] **Step 7: 更新 render_md 渲染新增内容**

在 `render_md` 中：

1. 在 "汇总" 表之后、"缓存命中率" 之前，新增阶段拆解表：
```python
    # 阶段拆解
    if data.get("phase_breakdown"):
        lines.append("## 阶段拆解")
        lines.append("")
        lines.append("| 阶段 | 调用次数 | Tokens | 耗时(s) |")
        lines.append("|------|---------|--------|---------|")
        pb = data["phase_breakdown"]
        for phase_name in ("generate", "fix", "review"):
            if phase_name in pb:
                p = pb[phase_name]
                lines.append(
                    f"| {phase_name} | {p['calls']} | {p['total_tokens']:,} "
                    f"| {p['total_duration_ms'] / 1000:.0f} |"
                )
        lines.append("")
```

2. 在缓存命中率之后，新增修复效率：
```python
    # 修复效率
    fe = data.get("fix_efficiency", {})
    if fe.get("tokens_per_p0_fixed") is not None:
        lines.append(f"- **每修复一个 P0 消耗 Token**: {fe['tokens_per_p0_fixed']:,}")
    if fe.get("p0_reduction_rate_pct") is not None:
        lines.append(f"- **P0 减少率**: {fe['p0_reduction_rate_pct']}%")
```

3. 新增模型信息：
```python
    # 模型信息
    models = summary.get("models_used", {})
    if models:
        lines.append("")
        lines.append("## 模型使用")
        lines.append("")
        lines.append("| Model | 调用次数 |")
        lines.append("|-------|---------|")
        for model, count in models.items():
            lines.append(f"| {model} | {count} |")
        lines.append("")
```

- [ ] **Step 8: 运行全量测试确认无回归**

```bash
cd /Users/chenyi/ai-project/workflow-agent-demo/agents/scheduler && python3 -m pytest tests/ -q
```

- [ ] **Step 9: Commit**

```bash
git add benchmarks/hooks/schema.py
git commit -m "feat: fix cache formula, add fix efficiency & phase breakdown metrics

- Fix cache hit ratio: cache_read / (cache_read + input_tokens)
- Filter dev subagents in _infer_rounds using is_dev_agent field
- Add _compute_fix_efficiency: tokens/P0-fixed, P0 reduction rate
- Add _compute_phase_breakdown: generate/fix/review token & time breakdown
- Enrich summary with models_used
- Enrich render_md with phase breakdown and fix efficiency sections

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: synthesize-benchmark.sh — 配置读取修复

**Files:**
- Modify: `benchmarks/hooks/synthesize-benchmark.sh`

- [ ] **Step 1: 从 pipeline.yaml 读取 block_strategy**

当前 block_strategy 写死为 "strict"。改为从 `code-check-config.yaml` 读取：

```bash
# ── 配置 ──
REVIEW_DIR="$PROJECT_DIR/agents/reviewer/check_system/review-output"
MAX_RETRIES=3
BLOCK_STRATEGY="strict"

# ── 尝试从 pipeline.yaml 读取 max_retries ──
PIPELINE_YAML="$PROJECT_DIR/agents/scheduler/pipeline.yaml"
if [ -f "$PIPELINE_YAML" ]; then
    MAX_RETRIES=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('defaults', {}).get('max_retries', 3))
except Exception:
    print(3)
" "$PIPELINE_YAML" 2>/dev/null || echo 3)
fi

# ── 尝试从 code-check-config.yaml 读取 strategy ──
CONFIG_YAML="$PROJECT_DIR/agents/reviewer/check_system/code-check-config.yaml"
if [ -f "$CONFIG_YAML" ]; then
    BLOCK_STRATEGY=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('strategy', 'strict'))
except Exception:
    print('strict')
" "$CONFIG_YAML" 2>/dev/null || echo "strict")
fi
```

- [ ] **Step 2: 传递 block_strategy 给 schema.py**

当前调用：
```bash
python3 "$SCHEMA_SCRIPT" \
    "$SESSION_ID" \
    "$JSONL_PATH" \
    "$REVIEW_DIR" \
    "$PROJECT_DIR" \
    "" \
    "$MAX_RETRIES"
```

修改为传递 block_strategy（作为第 7 个参数）：
```bash
python3 "$SCHEMA_SCRIPT" \
    "$SESSION_ID" \
    "$JSONL_PATH" \
    "$REVIEW_DIR" \
    "$PROJECT_DIR" \
    "" \
    "$MAX_RETRIES" \
    "$BLOCK_STRATEGY"
```

- [ ] **Step 3: 更新 schema.py CLI 读取 block_strategy**

在 `schema.py` 的 `if __name__ == "__main__":` 中：

```python
    bs = sys.argv[7] if len(sys.argv) > 7 else "strict"
```

调用 `from_jsonl` 时传入：
```python
    data = from_jsonl(sid, jpath, rdir, pdir, req, mr, bs)
```

- [ ] **Step 4: Commit**

```bash
git add benchmarks/hooks/synthesize-benchmark.sh benchmarks/hooks/schema.py
git commit -m "fix: read block_strategy from actual config instead of hardcoding

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: compare.py — 跨运行对比

**Files:**
- Create: `benchmarks/hooks/compare.py`

- [ ] **Step 1: 写 compare.py**

```python
#!/usr/bin/env python3
"""跨运行性能对比工具。

从 benchmarks/ 目录下所有 JSON 文件生成横向对比报告。
用法: python3 compare.py [benchmarks_dir] [-o output.md]
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict


def load_all_benchmarks(bench_dir: str) -> list[dict]:
    """加载所有 benchmark JSON 文件，按时间排序。"""
    results = []
    for fname in sorted(os.listdir(bench_dir)):
        if fname.endswith(".json") and fname.startswith("run-"):
            fpath = os.path.join(bench_dir, fname)
            try:
                with open(fpath, "r") as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return results


def render_comparison_md(runs: list[dict]) -> str:
    """从多份 benchmark JSON 渲染横向对比 Markdown 报告。"""
    if not runs:
        return "# 跨运行对比报告\n\n*暂无运行数据。*\n"

    lines = [
        "# 跨运行对比报告",
        "",
        f"**对比运行数**: {len(runs)}",
        "",
    ]

    # ── 运行概览表 ──
    lines.append("## 运行概览")
    lines.append("")
    lines.append("| Run ID | 时间 | 需求 | 轮次 | 收敛 | 总耗时(s) | 总 Token |")
    lines.append("|--------|------|------|------|------|-----------|----------|")
    for r in runs:
        meta = r["meta"]
        summary = r["summary"]
        conv = r["convergence"]
        converged = "✅" if summary.get("converged") else "❌"
        rounds_count = len(r.get("rounds", []))
        lines.append(
            f"| `{meta['run_id']}` | {meta['timestamp_start'][:10]} "
            f"| {meta.get('requirement_slug', '')[:20]} "
            f"| {rounds_count} | {converged} "
            f"| {summary['total_duration_ms'] / 1000:.0f} "
            f"| {summary['total_tokens']:,} |"
        )
    lines.append("")

    # ── 趋势：Token 消耗 ──
    lines.append("## Token 消耗趋势")
    lines.append("")
    lines.append("| Run ID | 总 Token | Coder | Reviewer | 缓存命中率 |")
    lines.append("|--------|----------|-------|----------|-----------|")
    for r in runs:
        meta = r["meta"]
        s = r["summary"]
        ce = s.get("cache_efficiency", {})
        ch = ce.get("cache_hit_ratio", 0) * 100
        lines.append(
            f"| `{meta['run_id']}` | {s['total_tokens']:,} "
            f"| {s['coder']['total_tokens']:,} "
            f"| {s['reviewer']['total_tokens']:,} "
            f"| {ch:.1f}% |"
        )
    lines.append("")

    # ── 趋势：收敛性 ──
    lines.append("## 收敛趋势")
    lines.append("")
    conv_runs = [r for r in runs if r["convergence"].get("series")]
    if conv_runs:
        lines.append("| Run ID | 起始 P0 | 最终 P0 | 收敛轮次 | 终止原因 |")
        lines.append("|--------|---------|---------|----------|----------|")
        for r in runs:
            meta = r["meta"]
            conv = r["convergence"]
            series = conv.get("series", [])
            if series:
                start_p0 = series[0].get("P0", "-")
                end_p0 = series[-1].get("P0", "-")
                lines.append(
                    f"| `{meta['run_id']}` | {start_p0} | {end_p0} "
                    f"| {conv.get('rounds_to_converge', '-')} "
                    f"| {conv.get('termination_reason', '-')} |"
                )
        lines.append("")

    # ── 修复效率对比 ──
    lines.append("## 修复效率对比")
    lines.append("")
    lines.append("| Run ID | Tokens/P0-Fixed | P0 减少率 |")
    lines.append("|--------|----------------|-----------|")
    for r in runs:
        meta = r["meta"]
        fe = r.get("fix_efficiency", {})
        tpp = fe.get("tokens_per_p0_fixed")
        prr = fe.get("p0_reduction_rate_pct")
        lines.append(
            f"| `{meta['run_id']}` | "
            f"{tpp if tpp is not None else '-'} | "
            f"{prr if prr is not None else '-'} |"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    bench_dir = sys.argv[1] if len(sys.argv) > 1 else "benchmarks"
    output = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "-o" else None

    data = load_all_benchmarks(bench_dir)

    if output:
        md = render_comparison_md(data)
        with open(output, "w") as f:
            f.write(md)
        print(f"Comparison report saved: {output}", file=sys.stderr)
    else:
        print(render_comparison_md(data))
```

- [ ] **Step 2: 用现有数据验证**

```bash
cd /Users/chenyi/ai-project/workflow-agent-demo && python3 benchmarks/hooks/compare.py benchmarks
```

- [ ] **Step 3: Commit**

```bash
git add benchmarks/hooks/compare.py
git commit -m "feat: add cross-run comparison report generator

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 用现有 JSONL dump 重新合成 benchmark**

```bash
cd /Users/chenyi/ai-project/workflow-agent-demo && \
python3 benchmarks/hooks/schema.py \
  "98fcdd02-671a-40f1-82ab-4cc0ecda51da" \
  "benchmarks/dumps/session-98fcdd02-671a-40f1-82ab-4cc0ecda51da.jsonl" \
  "agents/reviewer/check_system/review-output" \
  "." \
  "test-regeneration" \
  3 \
  "strict"
```

验证新生成的 JSON 包含 `fix_efficiency`、`phase_breakdown`、`models_used` 字段。

- [ ] **Step 2: 验证对比报告**

```bash
python3 benchmarks/hooks/compare.py benchmarks
```

- [ ] **Step 3: 验证 dump hook 新字段**

用 pipeline 数据手动测试 dump hook 输出（检查 `is_dev_agent`、`model`、`verdict`、`has_error` 字段）。

- [ ] **Step 4: Commit 最终结果**

```bash
git add benchmarks/
git commit -m "chore: regenerate benchmark with enriched metrics"
```
