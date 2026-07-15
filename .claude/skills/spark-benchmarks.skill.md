---
name: spark-benchmarks
description: 基准测试性能分析 — 读取 benchmark.json 数据，对单次或多次运行进行性能分析
---

# /spark:benchmarks — 基准测试性能分析

用法：`/spark:benchmarks <run_id>` 或 `/spark:benchmarks <run_id_1> <run_id_2>`

## 单次运行分析

当只给一个 run_id 时，读取 `benchmarks/{run_id}/benchmark.json`：
1. 读取 JSON 数据
2. 输出核心指标摘要：
   - 总 Token、总耗时、收敛轮次、是否收敛
   - Coder/Reviewer Token 占比
   - 缓存命中率
   - 各轮次的 P0/P1/P2 趋势
   - 模型使用分布
3. 指出性能瓶颈：哪一轮消耗最大？修复轮次是否比首轮更贵？

## 两次运行对比

当给两个 run_id 时，读取两份 `benchmark.json`：
1. 加载两份数据
2. 输出对比表格，维度包括：
   - 总 Token / 耗时 / 收敛轮次 / 缓存命中率
   - 起始 P0 数量 / 每轮 P0 下降趋势
   - Coder vs Reviewer Token 占比
   - 模型使用
3. 给出综合判断：哪次运行表现更好，好在哪些方面
4. 分析差异原因（基于 git commit、轮次结构差异等）

## 约束

- 只读取 `benchmarks/` 目录下的文件，不修改任何文件
- 不做统计检验、异常检测、趋势图渲染
- 分析以自然语言呈现，辅以表格
