# 基准测试系统 Phase 1 + Phase 2 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基准测试系统全面升级：问题定位 + 修复质量 + 成本归因 + 基线告警 + ASCII 趋势图 + 变更归因

**Architecture:** 修正 hooks 路径适配 `{run_id}` 子目录 → schema.py 新增 3 个分析函数 → compare.py 新增 4 个分析函数。schema.py 负责单次运行深度分析，compare.py 负责跨运行趋势和归因。

**Tech Stack:** Python 3 (json、hashlib、subprocess、re)、Bash

---

## 文件结构

| 文件 | 职责 | Phase |
|------|------|-------|
| `benchmarks/hooks/dump-agent-payload.sh` | 修正 reviewer 产物归档路径 | P1 |
| `benchmarks/hooks/synthesize-benchmark.sh` | 从 config 读取 output_dir 定位产物 | P1 |
| `benchmarks/hooks/schema.py` | 单次运行：问题定位 + 修复质量 + 成本归因 + 报告渲染 | P1 |
| `benchmarks/hooks/compare.py` | 跨运行：基线告警 + ASCII 趋势图 + 变更归因 + 对比报告 | P1+P2 |

---

### Task 1: 路径修正 — dump-agent-payload.sh + synthesize-benchmark.sh

**Files:**
- Modify: `benchmarks/hooks/dump-agent-payload.sh:97-111`
- Modify: `benchmarks/hooks/synthesize-benchmark.sh:50-55`

- [ ] **Step 1: 修正 dump-agent-payload.sh 的 reviewer 产物路径**

将第 101 行 `REVIEW_DIR` 从硬编码旧路径改为从 `code-check-config.yaml` 读取：

```bash
# 从 code-check-config.yaml 读取 output_dir，定位 reviewer 产物
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"
CONFIG_YAML="$CHECK_SYSTEM_DIR/code-check-config.yaml"

if echo "$DESC" | grep -qiE 'review|审查'; then
    # 从 config 读取 output_dir（相对于 check_system 目录）
    if [ -f "$CONFIG_YAML" ]; then
        OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CONFIG_YAML" 2>/dev/null)
        REVIEW_DIR="$(cd "$CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL" 2>/dev/null && pwd || echo "$PROJECT_DIR/review-output")"
    else
        REVIEW_DIR="$PROJECT_DIR/review-output"
    fi
    
    if [ -d "$REVIEW_DIR" ]; then
        # 每轮 reviewer 执行后，归档产物文件加入轮次号前缀
        N=$(find "$REVIEW_DIR" -maxdepth 1 -name "r*-pre-check-result.json" 2>/dev/null | wc -l | tr -d ' ')
        for f in pre-check-result.json pre-check-report.md review-result.json; do
            if [ -f "$REVIEW_DIR/$f" ]; then
                mv "$REVIEW_DIR/$f" "$REVIEW_DIR/r${N}-$f"
            fi
        done
    fi
fi
```

- [ ] **Step 2: 修正 synthesize-benchmark.sh 的 REVIEW_DIR**

将第 53 行 `REVIEW_DIR` 从硬编码改为从 config 读取：

```bash
# ── 从 code-check-config.yaml 读取 output_dir ──
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"
CONFIG_YAML="$CHECK_SYSTEM_DIR/code-check-config.yaml"
REVIEW_DIR="$PROJECT_DIR/review-output"  # 默认值

if [ -f "$CONFIG_YAML" ]; then
    OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CONFIG_YAML" 2>/dev/null)
    REVIEW_DIR="$(cd "$CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL" 2>/dev/null && pwd || echo "$PROJECT_DIR/review-output")"
fi
```

- [ ] **Step 3: 修正 schema.py CLI 默认值**

将 `benchmarks/hooks/schema.py` 第 657 行：

```python
    rdir = sys.argv[3] if len(sys.argv) > 3 else "agents/reviewer/check_system/review-output"
```

替换为：

```python
    rdir = sys.argv[3] if len(sys.argv) > 3 else "review-output"
```

- [ ] **Step 4: 修正 review-pre-hook.sh echo 信息**

将 `agents/reviewer/hooks/review-pre-hook.sh` 第 51 行：

```bash
    echo " 详细报告: $PROJECT_DIR/review-output/pre-check-report.md"
```

替换为读取 config 中的 output_dir：

```bash
    OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CHECK_SYSTEM_DIR/code-check-config.yaml" 2>/dev/null || echo "../../../review-output")
    echo " 详细报告: $CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL/pre-check-report.md"
```

- [ ] **Step 5: 提交**

```bash
git add benchmarks/hooks/dump-agent-payload.sh benchmarks/hooks/synthesize-benchmark.sh benchmarks/hooks/schema.py agents/reviewer/hooks/review-pre-hook.sh
git commit -m "fix: benchmarks hooks 和 review-pre-hook 路径适配 review-output/{run_id} 子目录"
```

---

### Task 2: schema.py — Phase 1 三大分析模块

**Files:**
- Modify: `benchmarks/hooks/schema.py` — 新增 `_localize_issues()`、`_assess_fix_quality()`，增强 `_compute_summary()`，更新 `render_md()`

- [ ] **Step 1: 新增 `_localize_issues()` 函数**

在 `_compute_phase_breakdown` 之后（约第 396 行后）添加：

```python
def _localize_issues(review_dir: str, rounds: list[dict]) -> dict:
    """按文件和规则类别统计问题分布。
    
    从每轮 reviewer 的 pre-check-result.json 和 review-result.json 
    中提取问题，按文件和类别聚合。
    
    Returns:
        {
            "per_file": {"UserController.java": {"P0": 2, "P1": 1}},
            "per_category": {"异常处理": {"fail": 2, "codes": ["BE-QL-01"]}},
            "per_round": [{"round": 0, "file": "...", "P0": 2, "P1": 1}]
        }
    """
    import os
    
    per_file = {}
    per_category = {}
    per_round = []
    
    for r in rounds:
        rn = r["round"]
        rv = r.get("reviewer")
        if rv is None:
            continue
        
        issues = rv.get("issues", {})
        if not issues:
            continue
        
        # 读取 pre-check-result.json 获取详细文件/类别信息
        pre_check_path = os.path.join(review_dir, f"r{rn}-pre-check-result.json")
        if os.path.isfile(pre_check_path):
            try:
                with open(pre_check_path, "r") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                data = {}
            
            for report in data.get("file_reports", []):
                fname = report.get("file", "unknown")
                if fname not in per_file:
                    per_file[fname] = {"P0": 0, "P1": 0, "P2": 0}
                
                for finding in report.get("findings", []):
                    level = finding.get("level", "")
                    if level in ("P0", "P1", "P2"):
                        per_file[fname][level] += 1
                        per_round.append({
                            "round": rn,
                            "file": fname,
                            "level": level,
                            "code": finding.get("code", ""),
                            "message": finding.get("message", "")[:80],
                        })
        
        # 读取 review-result.json 获取 AI 检查类别信息
        ai_path = os.path.join(review_dir, f"r{rn}-review-result.json")
        if os.path.isfile(ai_path):
            try:
                with open(ai_path, "r") as fh:
                    ai_data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                ai_data = {}
            
            for item in ai_data.get("items", []):
                if item.get("result") != "FAIL":
                    continue
                cat = item.get("category", "未分类")
                code = item.get("code", "")
                if cat not in per_category:
                    per_category[cat] = {"fail": 0, "codes": []}
                per_category[cat]["fail"] += 1
                if code and code not in per_category[cat]["codes"]:
                    per_category[cat]["codes"].append(code)
    
    return {
        "per_file": per_file,
        "per_category": per_category,
        "per_round": per_round,
    }
```

- [ ] **Step 2: 新增 `_assess_fix_quality()` 函数**

在 `_localize_issues` 之后添加：

```python
def _assess_fix_quality(rounds: list[dict], review_dir: str) -> dict:
    """评估修复质量：反复问题、副作用、有效率。
    
    Returns:
        {
            "recurring_rules": [{"code": "BE-QL-01", "rounds": [0,1,2]}],
            "fix_side_effects": [{"round": 1, "new_codes": ["BE-QL-05"]}],
            "fix_effectiveness": {"round_0_to_1": {"fixed": 3, "total": 5, "rate_pct": 60.0}}
        }
    """
    import os
    
    # 收集每轮的 FAIL code 列表
    round_fail_codes = {}
    for r in rounds:
        rn = r["round"]
        codes = set()
        ai_path = os.path.join(review_dir, f"r{rn}-review-result.json")
        if os.path.isfile(ai_path):
            try:
                with open(ai_path, "r") as fh:
                    ai_data = json.load(fh)
                for item in ai_data.get("items", []):
                    if item.get("result") == "FAIL":
                        codes.add(item.get("code", ""))
            except (json.JSONDecodeError, OSError):
                pass
        round_fail_codes[rn] = codes
    
    # 反复问题：同一 code 在多轮出现
    all_codes = set()
    for codes in round_fail_codes.values():
        all_codes.update(codes)
    
    recurring_rules = []
    for code in all_codes:
        appears_in = sorted([rn for rn, codes in round_fail_codes.items() if code in codes])
        if len(appears_in) >= 2:
            recurring_rules.append({"code": code, "rounds": appears_in})
    
    # 修复副作用：本轮有的 code 上轮没有
    sorted_rounds = sorted(round_fail_codes.keys())
    fix_side_effects = []
    for i in range(1, len(sorted_rounds)):
        prev_codes = round_fail_codes[sorted_rounds[i-1]]
        curr_codes = round_fail_codes[sorted_rounds[i]]
        new_codes = curr_codes - prev_codes
        if new_codes:
            fix_side_effects.append({
                "round": sorted_rounds[i],
                "new_codes": sorted(new_codes),
                "count": len(new_codes),
            })
    
    # 修复有效率：上轮标记 FAIL → 本轮仍 FAIL 的比例
    fix_effectiveness = {}
    for i in range(len(sorted_rounds) - 1):
        prev_rn = sorted_rounds[i]
        next_rn = sorted_rounds[i+1]
        prev_codes = round_fail_codes[prev_rn]
        next_codes = round_fail_codes[next_rn]
        total = len(prev_codes)
        if total > 0:
            still_failing = len(prev_codes & next_codes)
            fixed = total - still_failing
            fix_effectiveness[f"round_{prev_rn}_to_{next_rn}"] = {
                "fixed": fixed,
                "total": total,
                "rate_pct": round(fixed / total * 100, 1),
            }
    
    return {
        "recurring_rules": recurring_rules,
        "fix_side_effects": fix_side_effects,
        "fix_effectiveness": fix_effectiveness,
    }
```

- [ ] **Step 3: 增强 `_compute_summary()` 添加边际成本和审查占比**

在现有 `_compute_summary` 函数返回的 dict 中添加两个新字段。在 `models_used` 之后（约第 264 行表闭合后），添加：

```python
    # 边际修复成本
    marginal_fix_cost = []
    prev_tokens = None
    for r in rounds:
        coder = r.get("coder")
        if coder is not None and coder.get("phase") == "fix":
            tok = coder.get("total_tokens", 0)
            marginal_fix_cost.append({
                "round": r["round"],
                "tokens": tok,
                "delta_from_previous": (tok - prev_tokens) if prev_tokens is not None else 0,
            })
            prev_tokens = tok
    
    # 审查开销占比
    review_overhead_pct = round(reviewer_tokens / total_tokens * 100, 1) if total_tokens > 0 else 0.0
```

并在返回值中添加：

```python
        "marginal_fix_cost": marginal_fix_cost,
        "review_overhead_pct": review_overhead_pct,
```

- [ ] **Step 4: 在 `from_jsonl()` 中调用新函数**

在 `from_jsonl()` 中 `phase_breakdown` 之后（约第 455 行后）添加：

```python
    # 5d. 问题定位
    problem_localization = _localize_issues(review_dir, rounds)

    # 5e. 修复质量
    fix_quality = _assess_fix_quality(rounds, review_dir)
```

并在返回的 dict 中（约第 512 行 `summary` 附近）添加：

```python
        "problem_localization": problem_localization,
        "fix_quality": fix_quality,
```

- [ ] **Step 5: 更新 `render_md()` 添加新章节**

在现有 `render_md` 函数中，在「阶段拆解」章节之后、「缓存命中率」之前（约第 616 行后），添加两个新章节：

```python
    # 问题分布
    pl = data.get("problem_localization", {})
    if pl:
        lines.append("## 问题分布")
        lines.append("")
        
        # 按文件
        per_file = pl.get("per_file", {})
        if per_file:
            lines.append("### 按文件")
            lines.append("")
            lines.append("| 文件 | P0 | P1 | P2 | 合计 |")
            lines.append("|------|----|----|----|------|")
            for fname, counts in sorted(per_file.items(), 
                                          key=lambda x: sum(x[1].values()), reverse=True):
                total = sum(counts.values())
                lines.append(f"| {fname} | {counts['P0']} | {counts['P1']} | {counts['P2']} | {total} |")
            lines.append("")
        
        # 按类别
        per_category = pl.get("per_category", {})
        if per_category:
            lines.append("### 按规则类别")
            lines.append("")
            lines.append("| 类别 | FAIL 数 | 涉及规则码 |")
            lines.append("|------|---------|-----------|")
            for cat, info in sorted(per_category.items(), 
                                      key=lambda x: x[1]["fail"], reverse=True):
                codes_str = ", ".join(info["codes"][:5])
                if len(info["codes"]) > 5:
                    codes_str += f" ... 等{len(info['codes'])}条"
                lines.append(f"| {cat} | {info['fail']} | {codes_str} |")
            lines.append("")
    
    # 修复质量
    fq = data.get("fix_quality", {})
    if fq:
        lines.append("## 修复质量")
        lines.append("")
        
        recurring = fq.get("recurring_rules", [])
        if recurring:
            lines.append("### 反复出现的问题")
            lines.append("")
            lines.append("| 规则码 | 出现轮次 | 状态 |")
            lines.append("|--------|---------|------|")
            for rr in sorted(recurring, key=lambda x: len(x["rounds"]), reverse=True):
                rounds_str = ", ".join(str(rn) for rn in rr["rounds"])
                flag = "🔴 顽固" if len(rr["rounds"]) >= 3 else "⚠️"
                lines.append(f"| {rr['code']} | {rounds_str} | {flag} |")
            lines.append("")
        
        side_effects = fq.get("fix_side_effects", [])
        if side_effects:
            lines.append("### 修复副作用")
            lines.append("")
            lines.append("| 轮次 | 新增 FAIL 数 | 新增规则 |")
            lines.append("|------|-------------|---------|")
            for se in side_effects:
                codes_str = ", ".join(se["new_codes"])
                lines.append(f"| {se['round']} | {se['count']} | {codes_str} |")
            lines.append("")
        
        effectiveness = fq.get("fix_effectiveness", {})
        if effectiveness:
            lines.append("### 修复有效率")
            lines.append("")
            lines.append("| 轮次 → 下一轮 | 已修复 | 总问题 | 有效率 |")
            lines.append("|--------------|--------|--------|--------|")
            for transition, stats in effectiveness.items():
                lines.append(
                    f"| {transition} | {stats['fixed']} | {stats['total']} "
                    f"| {stats['rate_pct']}% |"
                )
            lines.append("")
    
    # 边际修复成本（增强阶段拆解）
    mfc = summary.get("marginal_fix_cost", [])
    if mfc:
        lines.append("### 修复边际成本")
        lines.append("")
        lines.append("| 轮次 | Token | 较上轮增加 |")
        lines.append("|------|-------|-----------|")
        for mc in mfc:
            delta_str = f"+{mc['delta_from_previous']:,}" if mc['delta_from_previous'] > 0 else str(mc['delta_from_previous'])
            lines.append(f"| {mc['round']} | {mc['tokens']:,} | {delta_str} |")
        lines.append("")
    
    lines.append(f"- **审查开销占比**: {summary['review_overhead_pct']}%")
```

- [ ] **Step 6: 运行测试确认**

检查语法和导入：
```bash
cd benchmarks/hooks && python3 -c "import schema; print('OK')"
```

Expected: `OK`，无 ImportError 或 SyntaxError。

- [ ] **Step 7: 提交**

```bash
git add benchmarks/hooks/schema.py
git commit -m "feat: schema.py 新增问题定位、修复质量、成本归因三大分析模块"
```

---

### Task 3: compare.py — Phase 1 基线告警

**Files:**
- Modify: `benchmarks/hooks/compare.py` — 新增 `_compute_baselines()`、`_detect_anomalies()`，增强 `render_comparison_md()`

- [ ] **Step 1: 新增 `_compute_baselines()` 函数**

在 `load_all_benchmarks` 之后添加：

```python
def _compute_baselines(runs: list[dict]) -> dict:
    """从所有历史运行计算基线（均值 + 标准差）。
    
    Returns:
        {
            "avg_p0": 3.2, "p0_std": 1.5,
            "avg_tokens": 45000, "tokens_std": 12000,
            "avg_rounds": 1.8, "rounds_std": 0.8,
            "avg_cache_hit": 0.45, "cache_std": 0.12,
            "sample_count": 10
        }
    """
    import statistics
    
    p0_values = []
    token_values = []
    rounds_values = []
    cache_values = []
    
    for r in runs:
        summary = r.get("summary", {})
        conv = r.get("convergence", {})
        series = conv.get("series", [])
        
        if series:
            p0_values.append(series[0].get("P0", 0))
        
        token_values.append(summary.get("total_tokens", 0))
        rounds_values.append(len(r.get("rounds", [])))
        
        ce = summary.get("cache_efficiency", {})
        cache_values.append(ce.get("cache_hit_ratio", 0))
    
    def safe_stats(values):
        if len(values) < 2:
            return sum(values) / len(values) if values else 0, 0
        return statistics.mean(values), statistics.stdev(values)
    
    avg_p0, p0_std = safe_stats(p0_values)
    avg_tokens, tokens_std = safe_stats(token_values)
    avg_rounds, rounds_std = safe_stats(rounds_values)
    avg_cache, cache_std = safe_stats(cache_values)
    
    return {
        "avg_p0": round(avg_p0, 1), "p0_std": round(p0_std, 1),
        "avg_tokens": int(avg_tokens), "tokens_std": int(tokens_std),
        "avg_rounds": round(avg_rounds, 1), "rounds_std": round(rounds_std, 1),
        "avg_cache_hit": round(avg_cache, 3), "cache_std": round(cache_std, 3),
        "sample_count": len(runs),
    }
```

- [ ] **Step 2: 新增 `_detect_anomalies()` 函数**

在 `_compute_baselines` 之后添加：

```python
def _detect_anomalies(runs: list[dict], baselines: dict) -> list[dict]:
    """检测当前运行是否偏离基线超过 2σ。
    
    Returns:
        [{
            "run_id": "run-...",
            "alerts": [
                {"metric": "tokens", "current": 120000, "baseline": 45000, 
                 "deviation": 6.25, "severity": "critical"},
            ]
        }]
    """
    alerts_per_run = []
    
    for r in runs:
        meta = r.get("meta", {})
        summary = r.get("summary", {})
        conv = r.get("convergence", {})
        ce = summary.get("cache_efficiency", {})
        series = conv.get("series", [])
        
        alerts = []
        
        # Token 检查
        if baselines.get("tokens_std", 0) > 0:
            tokens = summary.get("total_tokens", 0)
            dev = (tokens - baselines["avg_tokens"]) / baselines["tokens_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "tokens", "current": tokens,
                    "baseline": baselines["avg_tokens"],
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })
        
        # P0 检查
        if baselines.get("p0_std", 0) > 0 and series:
            p0 = series[0].get("P0", 0)
            dev = (p0 - baselines["avg_p0"]) / baselines["p0_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "p0", "current": p0,
                    "baseline": round(baselines["avg_p0"], 1),
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })
        
        # 收敛轮次检查
        if baselines.get("rounds_std", 0) > 0:
            rnd = len(r.get("rounds", []))
            dev = (rnd - baselines["avg_rounds"]) / baselines["rounds_std"]
            if abs(dev) > 2:
                alerts.append({
                    "metric": "rounds", "current": rnd,
                    "baseline": baselines["avg_rounds"],
                    "deviation": round(dev, 2),
                    "severity": "critical" if abs(dev) > 3 else "warning",
                })
        
        alerts_per_run.append({
            "run_id": meta.get("run_id", ""),
            "alerts": alerts,
        })
    
    return alerts_per_run
```

- [ ] **Step 3: 增强 `render_comparison_md()` 添加基线概览和异常告警**

在现有报告的「运行概览」表之后（约第 57 行 `lines.append("")` 后），添加基线概览表：

```python
    # ── 基线概览 ──
    baselines = _compute_baselines(runs)
    anomalies = _detect_anomalies(runs, baselines)
    
    if baselines.get("sample_count", 0) >= 2:
        lines.append("## 基线概览")
        lines.append("")
        lines.append(f"**样本数**: {baselines['sample_count']} 次运行")
        lines.append("")
        lines.append("| 指标 | 均值 | 标准差 |")
        lines.append("|------|------|--------|")
        lines.append(f"| 起始 P0 | {baselines['avg_p0']} | ±{baselines['p0_std']} |")
        lines.append(f"| 总 Token | {baselines['avg_tokens']:,} | ±{baselines['tokens_std']:,} |")
        lines.append(f"| 收敛轮次 | {baselines['avg_rounds']} | ±{baselines['rounds_std']} |")
        lines.append(f"| 缓存命中率 | {baselines['avg_cache_hit']*100:.1f}% | ±{baselines['cache_std']*100:.1f}% |")
        lines.append("")
```

在「运行概览」表中，对异常运行行添加标记。将原来的行（约第 50 行）：

```python
        lines.append(
            f"| `{meta['run_id']}` | {meta['timestamp_start'][:10]} "
            f"| {meta.get('requirement_slug', '')[:20]} "
            f"| {rounds_count} | {converged} "
            f"| {summary['total_duration_ms'] / 1000:.0f} "
            f"| {summary['total_tokens']:,} |"
        )
```

替换为：

```python
        # 检查是否有异常
        run_anomaly = next((a for a in anomalies if a["run_id"] == meta["run_id"]), None)
        flag = ""
        if run_anomaly and run_anomaly["alerts"]:
            has_critical = any(a["severity"] == "critical" for a in run_anomaly["alerts"])
            flag = " 🔴" if has_critical else " ⚠️"
        
        lines.append(
            f"| `{meta['run_id']}`{flag} | {meta['timestamp_start'][:10]} "
            f"| {meta.get('requirement_slug', '')[:20]} "
            f"| {rounds_count} | {converged} "
            f"| {summary['total_duration_ms'] / 1000:.0f} "
            f"| {summary['total_tokens']:,} |"
        )
```

在报告末尾（约第 120 行 `return` 之前），添加异常告警章节：

```python
    # ── 异常告警 ──
    any_alerts = any(a["alerts"] for a in anomalies)
    if any_alerts:
        lines.append("## 异常告警")
        lines.append("")
        lines.append("| Run ID | 指标 | 当前值 | 基线均值 | 偏离(σ) | 严重度 |")
        lines.append("|--------|------|--------|---------|---------|--------|")
        for run_anomaly in anomalies:
            for alert in run_anomaly["alerts"]:
                severity_icon = "🔴" if alert["severity"] == "critical" else "⚠️"
                lines.append(
                    f"| `{run_anomaly['run_id']}` | {alert['metric']} "
                    f"| {alert['current']:,} | {alert['baseline']} "
                    f"| {alert['deviation']}σ | {severity_icon} {alert['severity']} |"
                )
        lines.append("")
```

- [ ] **Step 4: 运行测试确认**

```bash
cd benchmarks/hooks && python3 -c "import compare; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add benchmarks/hooks/compare.py
git commit -m "feat: compare.py 新增基线计算和异常检测（Phase 1 基线告警）"
```

---

### Task 4: compare.py — Phase 2 趋势图 + 变更归因

**Files:**
- Modify: `benchmarks/hooks/compare.py` — 新增 `_render_sparkline()`、`_compute_change_attribution()`，增强 `render_comparison_md()`

- [ ] **Step 1: 新增 `_render_sparkline()` 函数**

在文件顶部附近（在 `_detect_anomalies` 之后）添加：

```python
def _render_sparkline(values: list[float], labels: list[str], max_label: str) -> str:
    """将数值列表渲染为 ASCII sparkline。
    
    8 级高度字符: " ▁▂▃▄▅▆▇█"
    """
    if not values or len(values) < 2:
        return ""
    
    chars = " ▁▂▃▄▅▆▇█"
    vmin = min(values)
    vmax = max(values)
    
    if vmax == vmin:
        # 所有值相同 → 全部居中
        indices = [4] * len(values)
    else:
        # 归一化到 [0, 7]
        indices = [round((v - vmin) / (vmax - vmin) * 7) for v in values]
    
    line = "".join(chars[i] for i in indices)
    
    # 组装输出
    max_str = f"{max_label:>10} ┤ "
    bottom = " " * 14 + "└" + "─" * (len(values) * 1) + "─"
    xlabels = " " * 16 + " ".join(labels[:len(values)])
    
    return f"{max_str}{line}\n{bottom}\n{xlabels}\n"
```

- [ ] **Step 2: 新增 `_compute_change_attribution()` 函数**

在 `_render_sparkline` 之后添加：

```python
def _compute_change_attribution(runs: list[dict], project_dir: str = ".") -> list[dict]:
    """对比相邻运行，检测规范文件变更并计算性能影响。
    
    Returns:
        [{
            "run_id": "run-...",
            "commit": "a1b2c3d",
            "changed_agent": "coder" | "reviewer" | None,
            "changed_files": ["path/to/file.md"],
            "fingerprint_change": {"old": "abc12345", "new": "def67890"},
            "perf_delta": {"tokens_pct": 15.6, "p0_delta": 1, ...}
        }]
    """
    import subprocess
    
    attributions = []
    prev = None
    
    for r in runs:
        meta = r.get("meta", {})
        commit = meta.get("git_commit_at_start", "")
        agents = r.get("agents", {})
        summary = r.get("summary", {})
        conv = r.get("convergence", {})
        
        if prev is None:
            prev = {"run": r, "commit": commit}
            attributions.append({
                "run_id": meta.get("run_id", ""),
                "commit": commit,
                "changed_agent": None,
                "changed_files": [],
                "fingerprint_change": None,
                "perf_delta": None,
            })
            continue
        
        # 检查 commit 是否变化
        if commit == prev["commit"] or not commit or not prev["commit"]:
            attributions.append({
                "run_id": meta.get("run_id", ""),
                "commit": commit,
                "changed_agent": None,
                "changed_files": [],
                "fingerprint_change": None,
                "perf_delta": None,
            })
            prev = {"run": r, "commit": commit}
            continue
        
        # 检测指纹变化
        changed_agent = None
        fp_change = None
        prev_agents = prev["run"].get("agents", {})
        
        for agent_key in ("coder", "reviewer"):
            prev_fp = prev_agents.get(agent_key, {}).get("fingerprint", "")
            curr_fp = agents.get(agent_key, {}).get("fingerprint", "")
            if prev_fp and curr_fp and prev_fp != curr_fp:
                changed_agent = agent_key
                fp_change = {"old": prev_fp, "new": curr_fp}
                break
        
        # 获取变更文件
        changed_files = []
        if changed_agent:
            try:
                result = subprocess.run(
                    ["git", "-C", project_dir, "diff", "--stat", 
                     f"{prev['commit']}..{commit}", "--", 
                     "agents/coder/", "agents/reviewer/", "agents/scheduler/"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        if "|" in line:
                            changed_files.append(line.strip())
            except Exception:
                pass
        
        # 计算性能 delta
        prev_summary = prev["run"].get("summary", {})
        tokens_delta = None
        if prev_summary.get("total_tokens", 0) > 0:
            tokens_delta = round(
                (summary.get("total_tokens", 0) - prev_summary["total_tokens"]) 
                / prev_summary["total_tokens"] * 100, 1
            )
        
        prev_series = prev["run"].get("convergence", {}).get("series", [])
        curr_series = conv.get("series", [])
        p0_delta = None
        if prev_series and curr_series:
            p0_delta = curr_series[0].get("P0", 0) - prev_series[0].get("P0", 0)
        
        perf_delta = {
            "tokens_pct": tokens_delta,
            "p0_delta": p0_delta,
        }
        
        attributions.append({
            "run_id": meta.get("run_id", ""),
            "commit": commit,
            "changed_agent": changed_agent,
            "changed_files": changed_files,
            "fingerprint_change": fp_change,
            "perf_delta": perf_delta,
        })
        
        prev = {"run": r, "commit": commit}
    
    return attributions
```

- [ ] **Step 3: 增强 `render_comparison_md()` 添加趋势图和变更归因**

在报告的「Token 消耗趋势」表之后（约第 75 行 `lines.append("")` 后），添加 sparkline 趋势图：

```python
    # ── Sparkline 趋势图 ──
    if len(runs) >= 2:
        lines.append("## 趋势图")
        lines.append("")
        
        # Token 趋势
        token_vals = [r["summary"]["total_tokens"] for r in runs]
        token_labels = [f"R{i+1}" for i in range(len(runs))]
        spark = _render_sparkline(token_vals, token_labels, f"{max(token_vals):,}")
        if spark:
            lines.append("### Token 消耗")
            lines.append("")
            lines.append("```")
            lines.append(spark.rstrip())
            lines.append("```")
            lines.append("")
        
        # P0 趋势
        p0_vals = []
        for r in runs:
            series = r.get("convergence", {}).get("series", [])
            p0_vals.append(series[0].get("P0", 0) if series else 0)
        if any(v > 0 for v in p0_vals):
            spark = _render_sparkline(p0_vals, token_labels, str(max(p0_vals)))
            if spark:
                lines.append("### P0 数量")
                lines.append("")
                lines.append("```")
                lines.append(spark.rstrip())
                lines.append("```")
                lines.append("")
        
        # 收敛轮次趋势
        rounds_vals = [len(r.get("rounds", [])) for r in runs]
        spark = _render_sparkline(rounds_vals, token_labels, str(max(rounds_vals)))
        if spark:
            lines.append("### 收敛轮次")
            lines.append("")
            lines.append("```")
            lines.append(spark.rstrip())
            lines.append("```")
            lines.append("")
        
        # 缓存命中率趋势
        cache_vals = [
            r.get("summary", {}).get("cache_efficiency", {}).get("cache_hit_ratio", 0) * 100 
            for r in runs
        ]
        if any(v > 0 for v in cache_vals):
            spark = _render_sparkline(cache_vals, token_labels, f"{max(cache_vals):.0f}%")
            if spark:
                lines.append("### 缓存命中率")
                lines.append("")
                lines.append("```")
                lines.append(spark.rstrip())
                lines.append("```")
                lines.append("")
```

在报告末尾（异常告警之后，`return` 之前），添加变更归因章节：

```python
    # ── 变更归因 ──
    attributions = _compute_change_attribution(runs, project_dir=".")
    has_changes = any(a.get("changed_agent") for a in attributions)
    if has_changes:
        lines.append("## 变更归因")
        lines.append("")
        lines.append("| 运行 | Commit | 变更 Agent | 文件数 | Token 变化 | P0 变化 |")
        lines.append("|------|--------|-----------|--------|-----------|---------|")
        for attr in attributions:
            if attr.get("changed_agent"):
                delta = attr.get("perf_delta", {}) or {}
                tokens_str = f"{delta.get('tokens_pct', 0):+.1f}%" if delta.get("tokens_pct") is not None else "—"
                p0_str = f"{delta.get('p0_delta', 0):+d}" if delta.get("p0_delta") is not None else "—"
                lines.append(
                    f"| `{attr['run_id']}` | `{attr['commit']}` "
                    f"| {attr['changed_agent']} | {len(attr['changed_files'])} "
                    f"| {tokens_str} | {p0_str} |"
                )
            else:
                lines.append(
                    f"| `{attr['run_id']}` | `{attr['commit']}` "
                    f"| — | 0 | — | — |"
                )
        lines.append("")
        
        # 变更详情
        for attr in attributions:
            if attr.get("changed_files"):
                lines.append(f"### {attr['run_id']} 变更详情 (`{attr['commit']}`)")
                lines.append("")
                lines.append(f"**{attr['changed_agent']} 规范变更 ({len(attr['changed_files'])} 文件):**")
                lines.append("")
                lines.append("```")
                for f in attr["changed_files"]:
                    lines.append(f"  {f}")
                lines.append("```")
                
                delta = attr.get("perf_delta", {}) or {}
                fp = attr.get("fingerprint_change", {}) or {}
                lines.append("")
                lines.append("**性能影响:**")
                lines.append("")
                lines.append(f"- 指纹变更: `{fp.get('old', '?')}` → `{fp.get('new', '?')}`")
                if delta.get("tokens_pct") is not None:
                    lines.append(f"- Token: {delta['tokens_pct']:+.1f}%")
                if delta.get("p0_delta") is not None:
                    lines.append(f"- 起始 P0: {delta['p0_delta']:+d}")
                lines.append("")
```

- [ ] **Step 4: 运行测试确认**

```bash
cd benchmarks/hooks && python3 -c "import compare; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add benchmarks/hooks/compare.py
git commit -m "feat: compare.py 新增 ASCII 趋势图和变更归因（Phase 2）"
```

---

### 执行顺序

```
Task 1 (路径修正: dump-agent-payload.sh + synthesize-benchmark.sh)
  → Task 2 (schema.py: 问题定位 + 修复质量 + 成本归因)
    → Task 3 (compare.py: 基线告警)
      → Task 4 (compare.py: 趋势图 + 变更归因)
```

Task 3 和 Task 4 都修改 `compare.py`，按顺序执行以避免冲突。
