# 基准测试系统

Spark 内置了一套完整的流水线性能基准测试系统，用于追踪每次 `/build` 运行的性能数据、分析修复效率、横向对比规范变更带来的影响。

## 系统架构

```
Claude Code Hooks
    │
    ├── PostToolUse (Agent)  →  dump-agent-payload.sh
    │    每次 Agent 调用完成时采集：时长、Token、模型、判定结果
    │    写入 benchmarks/dumps/session-{id}.jsonl
    │
    └── Stop (会话结束)       →  synthesize-benchmark.sh
         调用 schema.py 合成完整报告，产出：
         · benchmarks/run-{timestamp}-{slug}.json   (结构化数据)
         · benchmarks/run-{timestamp}-{slug}.md     (可读报告)
```

## 单次运行报告

每次 `/build` 完成后自动生成，包含以下分析维度：

### Agent 版本指纹

记录 coder（规范文件）和 reviewer（检查规则 + Python 代码）的 SHA256 指纹，追踪规范变更对每次运行的影响：

```
| Agent    | Fingerprint | 源文件数 |
|----------|-------------|---------|
| coder    | a1b2c3d4    | 22      |
| reviewer | e5f6g7h8    | 8       |
```

### 收敛曲线

追踪每轮审查中 P0/P1/P2 数量的变化，直到收敛或达到最大重试：

```
| Round | P0 | P1 | P2 | AI_FAIL |
|-------|----|----|----|---------|
| 0     | 5  | 3  | 2  | 2       |
| 1     | 2  | 1  | 1  | 0       |
| 2     | 0  | 0  | 1  | 0       |
```

### 各轮次详情

记录每个 Agent 调用阶段的耗时、Token 消耗、工具调用次数、缓存命中率、审查结果。

### 阶段拆解

按 generate（初始生成）、fix（修复轮次）、review（审查）三个阶段分别统计 Token 和时间开销，量化修复成本。

### 问题分布

- 按文件聚合 P0/P1/P2 数量，定位问题集中的热点文件
- 按规则类别聚合 FAIL 数量，发现高频违规类型

### 修复质量分析

| 指标 | 说明 |
|------|------|
| 反复问题 | 同一规则码在多轮审查中持续出现，标记为顽固问题 |
| 修复副作用 | 修复过程中引入的新问题（上一轮没有，本轮新增） |
| 修复有效率 | 每轮修复后，上一轮的 FAIL 项在本轮被修复的比例 |
| 边际修复成本 | 每一轮修复消耗的 Token，及相比上一轮的增长/下降趋势 |

### 汇总指标

| 指标 | 说明 |
|------|------|
| 总耗时 / 总 Token / 总 Tool Uses | 端到端统计 |
| Coder vs Reviewer 占比 | 生成与审查的 Token 和耗时对比 |
| 缓存命中率 | cache_read / (cache_read + input) 比例 |
| 审查开销占比 | Reviewer Token / 总 Token |
| 每修复一个 P0 消耗 Token | 修复效率的量化指标 |
| P0 减少率 | 首次审查到最终审查的 P0 降低比例 |
| 模型使用统计 | 各模型调用次数分布 |

## 跨运行对比

`compare.py` 脚本加载 `benchmarks/` 目录下所有 `run-*.json` 文件，生成横向对比报告。

```bash
python3 benchmarks/hooks/compare.py benchmarks -o benchmarks/comparison-report.md
```

### 基线计算与异常检测

从所有历史运行计算均值与标准差，对当前运行进行 >2σ 偏离告警：

```
| 指标   | 均值      | 标准差    |
|--------|-----------|----------|
| 起始 P0 | 3.5       | ±1.2     |
| 总 Token | 185,000  | ±32,000  |
| 收敛轮次 | 2.1      | ±0.8     |
| 缓存命中率 | 34.2%   | ±8.5%    |
```

### ASCII 趋势图

Token 消耗、P0 数量、收敛轮次、缓存命中率四个维度的可视化趋势，使用 8 级高度字符：

```
   185,000 ┤ ▁▃▅▇█
           └────────
            R1 R2 R3
```

### 变更归因

对比相邻运行的 git commit，检测 coder/reviewer 规范文件的变更，自动计算性能影响：

```
| 运行      | Commit   | 变更 Agent | 文件数 | Token 变化 | P0 变化 |
|-----------|----------|-----------|--------|-----------|---------|
| run-...1  | a1b2c3d  | reviewer  | 3      | +12.3%    | -2      |
```

## 实际案例：三版本横向对比

项目内置了 `admin-test-01`、`admin-test-02`、`admin-test-03` 三个版本的基准测试对比报告，从以下维度进行量化对比：

| 维度 | admin-test-01 | admin-test-02 | admin-test-03 |
|------|:---:|:---:|:---:|
| 架构纯度 | 较差 | 较差 | 优秀 |
| RBAC 权限安全 | 缺失 | 缺失 | 完整 |
| SQL 规范 | 未使用 LambdaQuery | 合规 | 合规 |
| 参数校验覆盖 | 41 | 33 | 44 |
| 审查通过 | 无记录 | 90/99 | 0 P0/P1 |
| 综合评分 | 61/100 | 80/100 | 80/100 |

参见 [BENCHMARK-REPORT.md](../review-output/BENCHMARK-REPORT.md) 查看完整报告。

## Hook 配置

基准测试通过 Claude Code hooks 自动采集，配置在项目 `.claude/settings.json` 中：

- **PostToolUse hook**（matcher: `Agent`）：每次 Agent 工具调用后触发，采集性能数据
- **Stop hook**：会话结束时触发，合成完整 JSON + Markdown 报告

无需手动操作，流水线性能数据自动记录。
