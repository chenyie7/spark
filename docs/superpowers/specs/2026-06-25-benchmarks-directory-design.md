# 基准测试目录结构优化

> **状态:** 已确认 | **日期:** 2026-06-25

## 目标

基准测试文件按每次运行分组到独立文件夹，消除 `benchmarks/` 根目录下 `run-*.json`/`run-*.md` 平铺的混乱局面。

## 背景

当前 `schema.py` 将 benchmark JSON 和 Markdown 报告直接写入 `benchmarks/` 根目录：

```
benchmarks/
├── run-20260624-004822-unnamed.json
├── run-20260624-004822-unnamed.md
├── run-20260624-092532-unnamed.json
├── ...
```

随着运行次数增加，文件越来越多，难以管理和查找。

## 设计

### 新目录结构

```
benchmarks/
├── hooks/                              # 采集/分析脚本（不变）
├── dumps/                              # 原始 session JSONL（不变）
├── runs/                               # 新：按运行分组
│   ├── 20260624153000/
│   │   ├── benchmark.json
│   │   └── report.md
│   ├── 20260624160000-admin-test/
│   │   ├── benchmark.json
│   │   └── report.md
│   └── ...
└── run-*.json / run-*.md               # 旧格式（compare.py 仍兼容读取）
```

### 文件夹命名

直接使用 pipeline 的 `run_id` 作为文件夹名：
- `run_id = "20260624153000"` → `runs/20260624153000/`
- `run_id = "20260624160000-admin-test"` → `runs/20260624160000-admin-test/`

### 文件命名

文件夹内固定两个文件：
- `benchmark.json` — 完整结构化数据（原 `{run_id}-{slug}.json`）
- `report.md` — 人类可读报告（原 `{run_id}-{slug}.md`）

文件名固定后，`requirement_slug` 不再参与文件名，仅保留在 JSON 的 `meta.requirement_slug` 字段中。

## 变更清单

### 1. `schema.py` — 输出路径

**文件:** `benchmarks/hooks/schema.py`

CLI 输出部分（约第 924-939 行）改为：

```python
    # 输出目录: benchmarks/runs/{run_id}/
    benchmarks_dir = os.path.join(pdir, "benchmarks", "runs", run_id)
    os.makedirs(benchmarks_dir, exist_ok=True)

    json_path = os.path.join(benchmarks_dir, "benchmark.json")
    md_path = os.path.join(benchmarks_dir, "report.md")

    with open(json_path, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    with open(md_path, "w") as fh:
        fh.write(render_md(data))
```

### 2. `compare.py` — 读取逻辑向后兼容

**文件:** `benchmarks/hooks/compare.py`

`load_all_benchmarks()` 改为：

```python
def load_all_benchmarks(bench_dir: str) -> list[dict]:
    """加载所有 benchmark JSON，兼容新旧两种目录结构。"""
    results = []
    
    # 新格式: runs/{run_id}/benchmark.json
    runs_dir = os.path.join(bench_dir, "runs")
    if os.path.isdir(runs_dir):
        for run_dir in sorted(os.listdir(runs_dir)):
            jpath = os.path.join(runs_dir, run_dir, "benchmark.json")
            if os.path.isfile(jpath):
                try:
                    with open(jpath, "r") as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
    
    # 旧格式兼容: run-*.json（benchmarks/ 根目录平铺）
    for fname in sorted(os.listdir(bench_dir)):
        if fname.endswith(".json") and fname.startswith("run-"):
            fpath = os.path.join(bench_dir, fname)
            # 避免重复：如果新格式已加载同 run_id 的数据则跳过
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                run_id = data.get("meta", {}).get("run_id", "")
                if not any(r.get("meta", {}).get("run_id") == run_id for r in results):
                    results.append(data)
            except (json.JSONDecodeError, OSError):
                pass
    
    return results
```

## 非目标

- 不自动迁移旧 `run-*.json` 文件到新目录（保留旧文件，手动清理）
- 不改变 `dumps/` 和 `hooks/` 目录结构
