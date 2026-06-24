# 基准测试系统 Phase 1 升级

> **状态:** 已确认 | **日期:** 2026-06-24

## 目标

在现有 benchmarks 系统基础上，新增四项分析能力：
1. **问题定位** — 按文件、按规则类别的问题分布
2. **修复质量** — 反复问题追踪、修复副作用检测
3. **成本归因** — 阶段成本拆解、修复边际成本
4. **基线告警** — 历史基线自动计算、异常标记

## 背景

当前 benchmarks 系统（`dump-agent-payload.sh` + `schema.py` + `compare.py`）提供基础采集、轮次分析和跨运行对比。但在"改完规范后想知道效果如何"的场景下，缺乏细粒度的问题定位、修复质量评估和异常检测能力。

另外，之前 `--target-dir` 和 `run_id` 子目录的改动导致 benchmarks 的数据采集路径断裂——`dump-agent-payload.sh` 和 `schema.py` 中仍引用旧的 `agents/reviewer/check_system/review-output` 路径，需要统一修正。

## 设计

### 系统架构

```
Agent 工具调用
  │
  ├─ dump-agent-payload.sh (PostToolUse Hook)
  │   → benchmarks/dumps/session-{id}.jsonl
  │   → 归档 review-output/{run_id}/ 产物文件
  │
  └─ synthesize-benchmark.sh (Stop Hook)
      │
      ├─ schema.py (合成引擎)
      │   ├─ from_jsonl() → 结构化 JSON
      │   ├─ 新增: _localize_issues() → 问题定位
      │   ├─ 新增: _assess_fix_quality() → 修复质量
      │   ├─ 增强: _compute_summary() → 成本归因
      │   └─ render_md() → Markdown 报告
      │
      └─ compare.py (跨运行对比)
          ├─ 新增: _compute_baselines() → 基线计算
          └─ 新增: _detect_anomalies() → 异常检测
```

### 路径修正（前置条件）

**`dump-agent-payload.sh`** — reviewer 产物归档路径：

```
旧: agents/reviewer/check_system/review-output
新: review-output/{run_id}/

归档模式从 r{N}-pre-check-result.json 改为按 run_id 子目录组织
```

**`schema.py`** — `_extract_issues` 需要接收 `review-output/{run_id}/` 路径，去掉 `r{round_num}-` 前缀逻辑，直接读 `pre-check-result.json`（同一 run 内每轮 reviewer 执行时已有独立文件由 hook 归档）。

**`synthesize-benchmark.sh`** — 需要从 `code-check-config.yaml` 读取当前 `output_dir` 以定位产物。

### 模块 1: 问题定位 (`_localize_issues`)

**数据来源:** `pre-check-result.json` 中的 `file_reports` 和 AI `review-result.json` 中的 `items`

**输出结构:**

```python
{
    "per_file": {
        "UserController.java": {"P0": 2, "P1": 1, "P2": 0},
        "UserServiceImpl.java": {"P0": 1, "P1": 0, "P2": 1}
    },
    "per_category": {
        "异常处理": {"fail": 2, "codes": ["BE-QL-01", "BE-QL-02"]},
        "日志质量": {"fail": 1, "codes": ["BE-QL-11"]}
    },
    "per_round": [
        {"round": 0, "file": "UserController.java", "P0": 2, "P1": 1},
        {"round": 1, "file": "UserController.java", "P0": 0, "P1": 1}
    ]
}
```

**Markdown 展示:** 新增「问题分布」章节，包含两张表：
- 按文件的问题分布表
- 按规则类别的问题分布表

### 模块 2: 修复质量 (`_assess_fix_quality`)

**数据来源:** 跨轮次的 issue 对比

**三个指标:**

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| `recurring_rules` | 同一规则在多轮反复触发 | 对比轮 N 和轮 N+1 的 fail code 列表，取交集 |
| `fix_side_effects` | 修复引入的新问题 | 轮 N 不存在的 code 在轮 N+1 出现，计数 |
| `fix_effectiveness` | 修复有效率 | 轮 N 标记 FAIL → 轮 N+1 仍 FAIL 的数量 / 轮 N 总 FAIL |

**输出结构:**

```python
{
    "recurring_rules": [
        {"code": "BE-QL-01", "rounds": [0, 1, 2], "file": "UserService.java"}
    ],
    "fix_side_effects": [
        {"round": 1, "new_codes": ["BE-QL-05"], "count": 1}
    ],
    "fix_effectiveness": {
        "round_0_to_1": {"fixed": 3, "total": 5, "rate_pct": 60.0}
    }
}
```

**Markdown 展示:** 新增「修复质量」章节：
- 反复出现的问题列表（红色标记出现 ≥3 轮的顽固问题）
- 修复副作用统计
- 修复有效率趋势

### 模块 3: 成本归因（增强 `_compute_summary`）

在现有 `phase_breakdown` 基础上增加：

**新增指标:**

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| `marginal_fix_cost` | 每轮修复比上一轮多花的 token | 轮 N token - 轮 N-1 token |
| `cost_per_file` | 每个生成/修改文件的平均 token | 总 token / 涉及文件数 |
| `review_overhead_pct` | 审查占全流程 token 比例 | reviewer_tokens / total_tokens × 100 |

**Markdown 展示:** 增强「阶段拆解」章节：
- 新增边际成本列
- 审查开销占比

### 模块 4: 基线告警 (`_compute_baselines` + `_detect_anomalies`)

**在 compare.py 中新增**（跨运行分析时计算）：

**基线计算:**
从所有历史 `run-*.json` 中提取：
- 平均 P0 数、P0 标准差
- 平均总 token、token 标准差
- 平均收敛轮次
- 平均缓存命中率

**异常检测:**
当前运行与基线对比，超过 2σ 标记为异常：

```python
{
    "baselines": {
        "avg_p0": 3.2, "p0_std": 1.5,
        "avg_tokens": 45000, "tokens_std": 12000,
        "avg_rounds": 1.8,
        "avg_cache_hit": 0.45
    },
    "alerts": [
        {
            "metric": "tokens",
            "current": 120000,
            "baseline": 45000,
            "deviation": 6.25,
            "severity": "critical"
        }
    ]
}
```

**Markdown 展示:**
- 对比报告中异常运行行高亮（⚠️ 或 🔴）
- 新增「基线概览」表
- 新增「异常告警」章节

## 变更清单

| 文件 | 变更 |
|------|------|
| `benchmarks/hooks/schema.py` | 新增 `_localize_issues`、`_assess_fix_quality`；增强 `_compute_summary`；更新 `render_md`；修正产物路径 |
| `benchmarks/hooks/compare.py` | 新增 `_compute_baselines`、`_detect_anomalies`；增强 `render_comparison_md` |
| `benchmarks/hooks/dump-agent-payload.sh` | 修正 reviewer 产物归档路径为 `review-output/{run_id}/` |
| `benchmarks/hooks/synthesize-benchmark.sh` | 从 `code-check-config.yaml` 读取 `output_dir` 定位产物 |

## 测试计划

### schema.py 单元测试
- `_localize_issues` 正确解析 pre-check-result.json 的 file_reports
- `_localize_issues` 正确解析 review-result.json 的 items 并归类
- `_assess_fix_quality` 正确检测跨轮反复问题
- `_assess_fix_quality` 正确计算修复副作用
- `_compute_summary` 包含 `marginal_fix_cost` 和 `review_overhead_pct`

### compare.py 单元测试
- `_compute_baselines` 从多份 JSON 正确计算均值/标准差
- `_detect_anomalies` 正确识别超出 2σ 的异常

### 集成测试
- 一次完整 `/build` 后，benchmark JSON 包含所有 4 个新模块的数据
- Markdown 报告包含所有新章节
- 对比报告正确标记异常运行

## 非目标

- 不实现 Phase 2 的趋势可视化图表（时间序列图等）
- 不实现变更归因（规范 diff ↔ 性能变化关联）
- 不修改 `.claude/settings.json` 的 hook 配置（已有配置不变）
