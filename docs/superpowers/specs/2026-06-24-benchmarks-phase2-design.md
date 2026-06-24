# 基准测试系统 Phase 2 升级

> **状态:** 已确认 | **日期:** 2026-06-24

## 目标

在 Phase 1（单次深度分析 + 基线告警）基础上，新增：
1. **ASCII 趋势图** — Markdown 报告中嵌入 sparkline 趋势线，直观展示关键指标变化
2. **变更归因** — 自动关联两次运行之间的规范文件变更，分析性能影响

## 背景

Phase 1 解决了"单次运行分析 + 异常检测"的问题。但用户的核心场景是"改了规范后想知道效果如何"，这需要两个额外能力：直观的趋势可视化（不只是表格数字）和自动的变更关联（改了什么规范 → 性能如何变）。

## 设计

### 模块 1: ASCII Sparkline 趋势图

在 `compare.py` 的 Markdown 报告中新增趋势图章节，用 Unicode block 字符渲染紧凑的折线图。

**格式:**

```
## 趋势图

### Token 消耗
  52,000 ┤     █
  45,000 ┤  ▁▃█▂▄▅▆
         └─────────────────
          R1 R2 R3 R4 R5 R6

### P0 数量
      8 ┤  █▅▂▁▁▁▁
         └─────────────────
```

**渲染规则:**
- 收集所有运行的目标指标值，归一化到 [0, 1]
- 映射到 8 级高度字符：`" ▁▂▃▄▅▆▇█"`（索引 0 = 空格，索引 8 = █）
- Y 轴标注最大值，X 轴标注运行编号（R1, R2…）
- 同一次运行内的收敛轮次数据，每轮一个点连接展示

**默认生成 4 张图:**
1. Token 消耗趋势（总 token / 运行）
2. P0 数量趋势（起始 P0 / 运行）
3. 收敛轮次趋势
4. 缓存命中率趋势

**函数签名:**

```python
def _render_sparkline(values: list[float], labels: list[str], max_label: str) -> str:
    """将数值列表渲染为 ASCII sparkline 字符串。

    Args:
        values: 每个点的数值
        labels: X 轴标签（如 ['R1', 'R2', ...]）
        max_label: Y 轴最大值标签（如 '52,000'）

    Returns:
        多行 sparkline 字符串
    """
```

### 模块 2: 变更归因

对比报告中新增「变更归因」章节，自动检测规范文件变更并关联性能变化。

**自动检测逻辑:**

1. 按时间排序所有运行记录
2. 相邻两次运行之间，检查 `git_commit_at_start` 是否不同
3. 如果不同，用 `git diff --stat <old>..<new> -- agents/coder/ agents/reviewer/ agents/scheduler/` 列出变更文件
4. 同时对比 benchmark JSON 中的 `agents.coder.fingerprint` 和 `agents.reviewer.fingerprint`——指纹变化 = 规范文件确实被修改了
5. 提取性能 delta：token 变化率、P0 变化率、收敛轮次变化

**展示格式:**

```
## 变更归因

| 运行 | Commit | 版本指纹变更 | 文件数 | Token 变化 | P0 变化 |
|------|--------|-------------|--------|-----------|---------|
| R5 | `a1b2c3d` | coder v1→v2 | 3 | +15.6% | +25% |
| R4 | `e5f6g7h` | — | 0 | — | — |
| R3 | `d4e5f6g` | reviewer v1→v2 | 1 | -8.2% | 不变 |

### R5 变更详情 (a1b2c3d)

**变更文件 (coder):**
  agents/coder/quality/code-style-guide.md     | 12 +++++---
  agents/coder/layered/controller-guide.md      | 5 +++--
  agents/coder/infrastructure/result-guide.md   | 2 +-

**性能影响 vs R4:**
| 指标 | R4 | R5 | 变化 |
|------|----|----|------|
| 总 Token | 45,000 | 52,000 | +15.6% |
| 起始 P0 | 3 | 4 | +1 |
| 收敛轮次 | 2 | 2 | 不变 |
| 缓存命中率 | 42% | 38% | -4pp |
```

**函数签名:**

```python
def _compute_change_attribution(runs: list[dict], project_dir: str) -> list[dict]:
    """对比相邻运行，检测规范文件变更并计算性能影响。

    Returns:
        [{
            "run_id": "run-...",
            "commit": "a1b2c3d",
            "changed_agent": "coder" | "reviewer" | None,
            "changed_files": ["path/to/file.md", ...],
            "fingerprint_change": {"old": "abc12345", "new": "def67890"},
            "perf_delta": {
                "tokens_pct": 15.6,
                "p0_delta": 1,
                "rounds_delta": 0,
                "cache_pct": -4
            }
        }, ...]
    """
```

### 变更清单

| 文件 | 变更 |
|------|------|
| `benchmarks/hooks/compare.py` | 新增 `_render_sparkline`；新增 `_compute_change_attribution`；增强 `render_comparison_md` |

Phase 2 只修改 `compare.py` 一个文件——所有逻辑都在跨运行对比报告中。

## 与 Phase 1 的关系

```
Phase 1                          Phase 2
───────                          ───────
schema.py:                       compare.py:
  深度分析 + 基线告警               ASCII 趋势图 + 变更归因

合在一起 → 完整的跨运行对比报告（含趋势 + 归因 + 异常 + 深度指标）
```

两个 Phase 可以独立实现。Phase 1 不依赖 Phase 2 的函数，Phase 2 读取 Phase 1 生成的 `run-*.json` 文件做分析。

## 测试计划

### `_render_sparkline` 单元测试
- 3 个值的 sparkline 正确映射到 block 字符
- 全零值 → 全部空格
- 最大值 → 全部 █
- 输出中包含正确的 Y 轴标注和 X 轴标签

### `_compute_change_attribution` 单元测试
- 两次运行 commit 相同 → 无变更归因
- 两次运行 commit 不同且指纹变化 → 正确识别变更 agent 和文件
- token delta 百分比计算正确（正值 = 增长，负值 = 减少）

### 集成测试
- 多份 `run-*.json` 输入 → 对比报告包含完整趋势图和变更归因章节

## 非目标

- 不生成 HTML/JS 交互式图表（仅 ASCII）
- 不自动化 git bisect 定位性能退化的精确 commit
- 不需要手动备注标签（Phase 2 只做自动关联）
