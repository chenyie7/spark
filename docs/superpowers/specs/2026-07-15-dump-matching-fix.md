# Dump 匹配修复：关键词 → 时序匹配

> **状态:** 待确认 | **日期:** 2026-07-15

## 问题

合成引擎的 `_filter_dumps` 函数用关键词匹配来区分 dump 中的 coder/reviewer 条目，实际运行时匹配失败，导致 benchmark 中 token 全为 0。

## 根因

两个原因叠加：

1. **关键词不匹配**：`config.yaml` 中配置的 coder 关键词是 `"生成"`，但 Agent 工具的 description 参数是 `"Coder: Hello World demo"`，不包含中文
2. **大小写敏感**：reviewer 关键词 `"review"` 与 description 中的 `"Reviewer:"` 不匹配（Python `in` 大小写敏感）

## 方案

**扔掉关键词匹配，改用时序匹配。**

pipeline-log 和 dump 都是按执行顺序追加的，且在 `.pipeline-active` 保护下只会采集 pipeline Agent（coder/reviewer）的数据。因此：

> 第 N 条 pipeline-log 条目 → 第 N 条 dump 条目

零歧义，零关键词依赖。

## 改动

### 1. `benchmarks/benchmark_lib/synthesize.py`

删除 `_filter_dumps` 函数，简化 `_build_rounds`：

```python
def _build_rounds(log_records, dump_records):
    """按时序合并 pipeline-log 和 dump 数据。"""
    # dump 按时序排序
    sorted_dumps = sorted(dump_records, key=lambda r: r.get("ts", 0))
    
    rounds = []
    dump_idx = 0
    
    for log in log_records:
        node = log.get("node", "")
        round_num = log.get("round", 1)
        verdict = log.get("verdict", "")
        
        dump = sorted_dumps[dump_idx] if dump_idx < len(sorted_dumps) else {}
        dump_idx += 1
        
        if node == "coder":
            phase = "generate" if round_num == 0 else "fix"
            # 挂载 coder 数据...
        elif node == "reviewer":
            # 挂载 reviewer 数据...
```

### 2. `benchmarks/config.yaml`

删除 `node_keywords` 配置段（不再需要）。

## 非目标

- 不改变 dump hook 的数据采集逻辑
- 不改变 pipeline-log 的写入逻辑
- 不改变 benchmark.json 的数据结构

## 验证

用 hello-test 的 dump + pipeline-log 重新合成，确认 token 数据正确。
