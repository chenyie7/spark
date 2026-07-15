# Dump 匹配修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 修复合成引擎中 dump 条目无法匹配的问题，从关键词匹配改为时序匹配。

**Architecture:** 删除 `_filter_dumps` + 删除 `config.yaml` 的 `node_keywords`。`_build_rounds` 直接按时序 zip pipeline-log 和 dump。

---

### Task 1: 重写 `_build_rounds` 函数

**Files:**
- Modify: `benchmarks/benchmark_lib/synthesize.py`

- [ ] **Step 1: 删除 `_filter_dumps` 函数**

删除整个 `_filter_dumps` 函数定义。

- [ ] **Step 2: 重写 `_build_rounds`**

将 `_build_rounds` 的签名从三个参数改为两个，内部改为时序匹配：

```python
def _build_rounds(
    log_records: list[dict],
    dump_records: list[dict],
) -> list[dict]:
    """按时序合并 pipeline-log 和 dump 数据，构建 rounds 列表。

    pipeline-log 和 dump 都是按执行顺序追加的。
    第 N 条 pipeline-log 条目匹配第 N 条 dump 条目。
    """
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
            existing = _find_or_none(rounds, round_num)
            coder_data = {
                "phase": phase,
                "duration_ms": dump.get("duration_ms", 0),
                "total_tokens": dump.get("total_tokens", 0),
                "total_tool_uses": dump.get("total_tool_uses", 0),
                "usage": dump.get("usage", {}),
            }
            if existing is not None:
                existing["coder"] = coder_data
            else:
                rounds.append({"round": round_num, "coder": coder_data, "reviewer": None})

        elif node == "reviewer":
            existing = _find_or_none(rounds, round_num)
            reviewer_data = {
                "phase": "review",
                "duration_ms": dump.get("duration_ms", 0),
                "total_tokens": dump.get("total_tokens", 0),
                "total_tool_uses": dump.get("total_tool_uses", 0),
                "usage": dump.get("usage", {}),
                "result": verdict,
                "issues": {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1},
            }
            if existing is not None:
                existing["reviewer"] = reviewer_data
            else:
                rounds.append({"round": round_num, "coder": None, "reviewer": reviewer_data})

    return rounds


def _find_or_none(rounds: list[dict], round_num: int) -> dict | None:
    """在 rounds 列表中查找指定轮次的条目。"""
    for r in rounds:
        if r["round"] == round_num:
            return r
    return None
```

- [ ] **Step 3: 更新 `synthesize` 函数中的调用**

将：
```python
coder_dumps = _filter_dumps(dump_records, config.node_keywords.coder)
reviewer_dumps = _filter_dumps(dump_records, config.node_keywords.reviewer)
rounds = _build_rounds(log_records, coder_dumps, reviewer_dumps)
```

改为：
```python
rounds = _build_rounds(log_records, dump_records)
```

- [ ] **Step 4: 提交**

```bash
git add benchmarks/benchmark_lib/synthesize.py
git commit -m "fix(benchmarks): switch dump matching from keywords to temporal order

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 删除 `config.yaml` 中的 `node_keywords`

**Files:**
- Modify: `benchmarks/config.yaml`
- Modify: `benchmarks/benchmark_lib/config.py`

- [ ] **Step 1: 删除 config.yaml 中的 `node_keywords` 段**

`benchmarks/config.yaml` 删除整个 `node_keywords` 配置块。

- [ ] **Step 2: 删除 config.py 中的 `NodeKeywordsConfig`**

删除 `NodeKeywordsConfig` dataclass 和 `BenchmarkConfig` 中的 `node_keywords` 字段，以及 `load_config` 中的相关加载逻辑。

简化后的 `config.py`：

```python
"""配置加载模块。"""
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class RetentionConfig:
    max_days: int = 7


@dataclass
class PathsConfig:
    dumps_dir: str = "benchmarks/dumps"
    output_dir: str = "benchmarks"


@dataclass
class BenchmarkConfig:
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    pipeline_log_template: str = "{run_id}/pipeline-log.jsonl"


def load_config(project_dir: str = ".") -> BenchmarkConfig:
    config_path = Path(project_dir) / "benchmarks" / "config.yaml"
    if not config_path.exists():
        return BenchmarkConfig()
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}
    return BenchmarkConfig(
        retention=RetentionConfig(
            max_days=raw.get("retention", {}).get("max_days", 7),
        ),
        paths=PathsConfig(
            dumps_dir=raw.get("paths", {}).get("dumps_dir", "benchmarks/dumps"),
            output_dir=raw.get("paths", {}).get("output_dir", "benchmarks"),
        ),
        pipeline_log_template=raw.get(
            "pipeline_log_template", "{run_id}/pipeline-log.jsonl"
        ),
    )


def resolve_path(project_dir: str, relative_path: str) -> Path:
    return (Path(project_dir) / relative_path).resolve()
```

注意：`from dataclasses import dataclass, field` 改为 `from dataclasses import dataclass`（field 不再需要）。

- [ ] **Step 3: 提交**

```bash
git add benchmarks/config.yaml benchmarks/benchmark_lib/config.py
git commit -m "refactor(benchmarks): remove node_keywords config, no longer needed

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 验证

- [ ] **Step 1: 用 hello-test 数据重新合成**

```bash
RUN_ID="20260715080204-hello-test"
PYTHONPATH="${PWD}/benchmarks:${PWD}" python3 -m benchmark_lib.cli synthesize "${RUN_ID}" --project-dir .
```

- [ ] **Step 2: 检查 token 数据**

```bash
PYTHONPATH="${PWD}/benchmarks:${PWD}" python3 -c "
from benchmark_lib.models import validate_benchmark
import json
with open('benchmarks/${RUN_ID}/benchmark.json') as f:
    d = json.load(f)
validate_benchmark(d)
print(f'tokens: {d[\"summary\"][\"total_tokens\"]:,}')
print(f'coder_tokens: {d[\"summary\"][\"coder\"][\"total_tokens\"]:,}')
print(f'reviewer_tokens: {d[\"summary\"][\"reviewer\"][\"total_tokens\"]:,}')
for r in d['rounds']:
    c = r.get('coder', {})
    rv = r.get('reviewer', {})
    print(f'Round {r[\"round\"]}: coder={c.get(\"total_tokens\",0):,}t | reviewer={rv.get(\"total_tokens\",0):,}t')
"
```

Expected: `tokens > 0`（之前为 0）

- [ ] **Step 3: 用 benchmark-test 数据重新合成确认**

```bash
RUN_ID="20260715072545-benchmark-test"
PYTHONPATH="${PWD}/benchmarks:${PWD}" python3 -m benchmark_lib.cli synthesize "${RUN_ID}" --project-dir .
```

确认 token 数据同样正确。
