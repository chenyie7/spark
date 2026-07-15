# 基准测试系统重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完整重构 `benchmarks/` 基准测试系统：Shell 退化到极薄数据搬运层，所有业务逻辑迁移到纯 Python `benchmark_lib` 包，配置集中到 `config.yaml`，按 run_id 组织数据，7 天自动清理，新增 `spark:benchmarks` skill。

**Architecture:** 3 层结构：Hook 层（极薄 Shell 采集）→ Pipeline Engine 层（结构化轮次日志）→ Python 合成引擎（合并两路数据 + 渲染报告 + 清理）。Hook 通过 `.pipeline-active` 开关保证非 `/build` 场景零开销。

**Tech Stack:** Python 3.14, Bash, YAML, JSON Schema (draft-07)

---

### Task 1: 创建配置文件 `benchmarks/config.yaml`

**Files:**
- Create: `benchmarks/config.yaml`

- [ ] **Step 1: 创建配置文件**

```yaml
# 基准测试系统配置
# 所有可配置项集中于此文件，代码中零硬编码。

# 数据保留
retention:
  max_days: 7

# 数据目录（相对于项目根目录）
paths:
  dumps_dir: benchmarks/dumps
  output_dir: benchmarks

# pipeline-log 文件路径模板
# {run_id} 会被替换为实际的 run_id
pipeline_log_template: "{run_id}/pipeline-log.jsonl"

# pipeline 节点识别关键词（用于区分 dumps 中的 coder/reviewer/dev-agent 条目）
node_keywords:
  coder:
    - "生成"
  reviewer:
    - "审查"
    - "review"
```

- [ ] **Step 2: 提交**

```bash
git add benchmarks/config.yaml
git commit -m "feat(benchmarks): add config.yaml for centralized configuration"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 2: 创建包初始化文件 `benchmarks/benchmark_lib/__init__.py`

**Files:**
- Create: `benchmarks/benchmark_lib/__init__.py`

- [ ] **Step 1: 创建包入口**

```python
"""benchmark_lib — 基准测试数据合成、报告、清理的纯 Python 包。

用法：
    from benchmark_lib.config import load_config
    from benchmark_lib.synthesize import synthesize
    from benchmark_lib.report import render_report
    from benchmark_lib.cleanup import cleanup
"""

__version__ = "2.0.0"
```

- [ ] **Step 2: 提交**

```bash
git add benchmarks/benchmark_lib/__init__.py
git commit -m "feat(benchmarks): add benchmark_lib package init"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 3: 配置加载模块 `benchmarks/benchmark_lib/config.py`

**Files:**
- Create: `benchmarks/benchmark_lib/config.py`

- [ ] **Step 1: 编写配置加载模块**

```python
"""配置加载模块。

从 benchmarks/config.yaml 加载配置，以 dataclass 形式暴露。
全项目零硬编码路径和阈值。
"""

from dataclasses import dataclass, field
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
class NodeKeywordsConfig:
    coder: list[str] = field(default_factory=lambda: ["生成"])
    reviewer: list[str] = field(default_factory=lambda: ["审查", "review"])


@dataclass
class BenchmarkConfig:
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    pipeline_log_template: str = "{run_id}/pipeline-log.jsonl"
    node_keywords: NodeKeywordsConfig = field(default_factory=NodeKeywordsConfig)


def load_config(project_dir: str = ".") -> BenchmarkConfig:
    """从 benchmarks/config.yaml 加载配置。

    Args:
        project_dir: 项目根目录路径

    Returns:
        BenchmarkConfig 实例，缺失字段使用默认值
    """
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
        node_keywords=NodeKeywordsConfig(
            coder=raw.get("node_keywords", {}).get("coder", ["生成"]),
            reviewer=raw.get("node_keywords", {}).get("reviewer", ["审查", "review"]),
        ),
    )


def resolve_path(project_dir: str, relative_path: str) -> Path:
    """将配置中的相对路径解析为绝对 Path。"""
    return (Path(project_dir) / relative_path).resolve()
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "from benchmark_lib.config import load_config; c = load_config(); print(f'retention_days={c.retention.max_days}')"
```

Expected: `retention_days=7`

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/config.py
git commit -m "feat(benchmarks): add config loading module with zero hardcoding"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 4: 数据模型与 JSON Schema `benchmarks/benchmark_lib/models.py`

**Files:**
- Create: `benchmarks/benchmark_lib/models.py`

- [ ] **Step 1: 编写数据模型和 JSON Schema**

```python
"""数据模型与 JSON Schema 定义。

定义 benchmark.json 的完整 JSON Schema (draft-07)，
以及辅助的数据结构 dataclass。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import jsonschema

CST = timezone(timedelta(hours=8))

# ── JSON Schema (draft-07) ────────────────────────────────────────────

BENCHMARK_SCHEMA_V2 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["schema_version", "meta", "rounds", "convergence", "summary"],
    "properties": {
        "schema_version": {"type": "string", "const": "2.0"},
        "meta": {
            "type": "object",
            "required": ["run_id", "timestamp_start", "timestamp_end", "git_commit"],
            "properties": {
                "run_id": {"type": "string"},
                "timestamp_start": {"type": "string"},
                "timestamp_end": {"type": "string"},
                "git_commit": {"type": "string"},
                "max_retries": {"type": "integer"},
                "block_strategy": {"type": "string"},
            },
        },
        "rounds": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["round"],
                "properties": {
                    "round": {"type": "integer"},
                    "coder": {
                        "type": "object",
                        "properties": {
                            "phase": {"type": "string"},
                            "duration_ms": {"type": "integer"},
                            "total_tokens": {"type": "integer"},
                            "total_tool_uses": {"type": "integer"},
                            "usage": {"type": "object"},
                        },
                    },
                    "reviewer": {
                        "type": "object",
                        "properties": {
                            "phase": {"type": "string"},
                            "duration_ms": {"type": "integer"},
                            "total_tokens": {"type": "integer"},
                            "total_tool_uses": {"type": "integer"},
                            "usage": {"type": "object"},
                            "result": {"type": "string"},
                            "issues": {
                                "type": "object",
                                "properties": {
                                    "P0": {"type": "integer"},
                                    "P1": {"type": "integer"},
                                    "P2": {"type": "integer"},
                                    "AI_FAIL": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
            },
        },
        "convergence": {
            "type": "object",
            "required": ["rounds_to_converge", "termination_reason", "series"],
            "properties": {
                "rounds_to_converge": {"type": ["integer", "null"]},
                "termination_reason": {"type": "string"},
                "series": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "round": {"type": "integer"},
                            "P0": {"type": "integer"},
                            "P1": {"type": "integer"},
                            "P2": {"type": "integer"},
                            "AI_FAIL": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "summary": {
            "type": "object",
            "required": ["total_duration_ms", "total_tokens", "total_tool_uses", "converged"],
            "properties": {
                "total_duration_ms": {"type": "integer"},
                "total_tokens": {"type": "integer"},
                "total_tool_uses": {"type": "integer"},
                "coder": {
                    "type": "object",
                    "properties": {
                        "total_tokens": {"type": "integer"},
                        "total_duration_ms": {"type": "integer"},
                        "avg_tokens_per_call": {"type": "integer"},
                    },
                },
                "reviewer": {
                    "type": "object",
                    "properties": {
                        "total_tokens": {"type": "integer"},
                        "total_duration_ms": {"type": "integer"},
                        "avg_tokens_per_call": {"type": "integer"},
                    },
                },
                "cache_efficiency": {
                    "type": "object",
                    "properties": {
                        "total_cache_read_tokens": {"type": "integer"},
                        "total_input_tokens": {"type": "integer"},
                        "cache_hit_ratio": {"type": "number"},
                    },
                },
                "converged": {"type": "boolean"},
                "models_used": {"type": "object"},
            },
        },
    },
}


# ── 校验函数 ──

def validate_benchmark(data: dict) -> None:
    """校验 benchmark 数据是否符合 schema 2.0。

    Args:
        data: 待校验的 benchmark JSON 对象

    Raises:
        jsonschema.ValidationError: 校验失败
    """
    jsonschema.validate(data, BENCHMARK_SCHEMA_V2)


def get_timestamp_cst() -> str:
    """返回当前时间的 CST ISO 格式字符串。"""
    return datetime.now(CST).isoformat()
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "from benchmark_lib.models import BENCHMARK_SCHEMA_V2; print(f'schema version={BENCHMARK_SCHEMA_V2[\"properties\"][\"schema_version\"][\"const\"]}')"
```

Expected: `schema version=2.0`

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/models.py
git commit -m "feat(benchmarks): add data models and JSON Schema v2.0"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 5: 重写数据采集 Hook `benchmarks/hooks/dump-agent-payload.sh`

**Files:**
- Modify: `benchmarks/hooks/dump-agent-payload.sh` (重写)

- [ ] **Step 1: 重写 hook（极薄 Shell，不下发业务判断）**

```bash
#!/bin/bash
# dump-agent-payload.sh
# PostToolUse hook for Agent tool — 采集性能数据追加到 JSONL
#
# 职责：极薄数据搬运。不下发任何业务判断（不提取 verdict、不检测
# is_dev_agent、不重命名产物文件）。只负责把 Agent payload 追加到 dump 文件。
#
# 配置：PostToolUse matcher: "Agent"

set -euo pipefail

# 开关：非流水线场景静默退出
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# 从 .current-run 读取 run_id
CURRENT_RUN="${PROJECT_DIR}/review-output/.current-run"
if [ ! -f "$CURRENT_RUN" ]; then
    exit 0
fi

RUN_ID=$(python3 -c "
import json
with open('${CURRENT_RUN}') as f:
    print(json.load(f)['run_id'])
" 2>/dev/null || echo "")

if [ -z "$RUN_ID" ]; then
    exit 0
fi

DUMP_FILE="${PROJECT_DIR}/benchmarks/dumps/${RUN_ID}.jsonl"
mkdir -p "$(dirname "$DUMP_FILE")"

# 读取 stdin，提取性能字段，追加一行 JSONL
python3 -c "
import sys, json, time

raw = json.load(sys.stdin)
ti = raw.get('tool_input', {})
tr = raw.get('tool_response', {})
content = tr.get('content', [])

# 完整 last_message（不截取）
last_msg = ''
if content and isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            last_msg = block.get('text', '')
            break

rec = {
    'ts': int(time.time()),
    'tool_use_id': raw.get('tool_use_id', ''),
    'description': ti.get('description', ''),
    'subagent_type': ti.get('subagent_type', ''),
    'duration_ms': tr.get('totalDurationMs', 0),
    'total_tokens': tr.get('totalTokens', 0),
    'total_tool_uses': tr.get('totalToolUseCount', 0),
    'usage': tr.get('usage', {}),
    'last_message': last_msg,
    'model': tr.get('usage', {}).get('model', ''),
}
print(json.dumps(rec, ensure_ascii=False))
" >> "$DUMP_FILE"

exit 0
```

- [ ] **Step 2: 提交**

```bash
git add benchmarks/hooks/dump-agent-payload.sh
git commit -m "refactor(benchmarks): rewrite dump hook to thin shell, use run_id naming"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 6: Pipeline Engine 写入 pipeline-log.jsonl

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py`

- [ ] **Step 1: 在 `cmd_report` 函数末尾增加 pipeline-log 写入逻辑**

在 `cmd_report` 函数中，`engine.report()` 成功返回后，在 `print(json.dumps({...}))` 之前插入 pipeline-log 写入逻辑。

定位到 `cmd_report` 函数（约第 121-138 行）。在 `state = engine.report(...)` 调用成功后（第 128 行之后），加入：

```python
    # ── 写入 pipeline-log.jsonl（基准测试数据采集）─────────────
    import time as _time
    from pathlib import Path as _Path

    run_id = state_path.parent.name
    log_dir = _Path("benchmarks") / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline-log.jsonl"

    log_entry = {
        "ts": int(_time.time()),
        "round": state.round,
        "node": args.node,
        "status": args.status,
        "verdict": args.verdict or "",
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    # ── pipeline-log 写入完毕 ─────────────────────────────
```

完整修改后的 `cmd_report` 函数：

```python
def cmd_report(args):
    """记录节点执行结果。"""
    state_path = Path(args.state_file)
    pipeline_path = Path(args.pipeline)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({"accepted": False, "error": str(e)}))
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        status = NodeStatus(args.status)
        state = engine.report(
            node_id=args.node,
            status=status,
            summary=args.summary or "",
            agent_verdict=args.verdict or "",
        )
    except (ValueError, RuntimeError) as e:
        print(json.dumps({"accepted": False, "error": str(e)}))
        sys.exit(0)

    # ── 写入 pipeline-log.jsonl（基准测试数据采集）─────────────
    import time as _time

    run_id = state_path.parent.name
    log_dir = Path("benchmarks") / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline-log.jsonl"

    log_entry = {
        "ts": int(_time.time()),
        "round": state.round,
        "node": args.node,
        "status": args.status,
        "verdict": args.verdict or "",
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    # ── pipeline-log 写入完毕 ─────────────────────────────

    print(json.dumps({
        "accepted": True,
        "state": state.status.value,
        "round": state.round,
        "current_nodes": state.current_nodes,
    }))
```

- [ ] **Step 2: 验证 pipeline_engine 模块仍可导入**

```bash
cd /Users/chenyi/ai-project/spark && PYTHONPATH="agents/scheduler:agents/reviewer/check_system" python3 -c "from pipeline_engine.cli import cmd_report; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: 运行 pipeline_engine 现有测试确保不破坏**

```bash
cd /Users/chenyi/ai-project/spark && PYTHONPATH="agents/scheduler:agents/reviewer/check_system" python3 -m pytest agents/scheduler/tests/ -v
```

Expected: All tests pass

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/pipeline_engine/cli.py
git commit -m "feat(pipeline-engine): write pipeline-log.jsonl on report for benchmark data"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 7: 数据清理模块 `benchmarks/benchmark_lib/cleanup.py`

**Files:**
- Create: `benchmarks/benchmark_lib/cleanup.py`

- [ ] **Step 1: 编写清理模块**

```python
"""数据清理模块。

清理 benchmarks/dumps/ 和 benchmarks/{run_id}/ 中超过保留天数的数据。
硬保护当前 run_id 不删除。
"""

import os
import shutil
import time
from pathlib import Path

from benchmark_lib.config import load_config, resolve_path


def cleanup(project_dir: str = ".", current_run_id: str | None = None) -> int:
    """清理过期数据。

    Args:
        project_dir: 项目根目录
        current_run_id: 当前运行 ID，其数据不会被删除（硬保护）

    Returns:
        清理的文件/目录数量
    """
    config = load_config(project_dir)
    max_age_seconds = config.retention.max_days * 24 * 3600
    now = time.time()
    cutoff = now - max_age_seconds
    cleaned = 0

    # ── 清理 dumps/ ──
    dumps_dir = resolve_path(project_dir, config.paths.dumps_dir)
    if dumps_dir.is_dir():
        for f in sorted(dumps_dir.iterdir()):
            if not f.is_file():
                continue
            if not f.name.endswith(".jsonl"):
                continue
            run_id = f.name.replace(".jsonl", "")
            if run_id == current_run_id:
                continue
            if _mtime(f) < cutoff:
                f.unlink()
                cleaned += 1

    # ── 清理 {run_id}/ 目录 ──
    output_dir = resolve_path(project_dir, config.paths.output_dir)
    if output_dir.is_dir():
        for d in sorted(output_dir.iterdir()):
            if not d.is_dir():
                continue
            # 跳过非 run_id 目录（如 hooks/、dumps/、benchmark_lib/）
            run_id = d.name
            if run_id in ("hooks", "dumps", "benchmark_lib"):
                continue
            if run_id == current_run_id:
                continue
            benchmark_file = d / "benchmark.json"
            if benchmark_file.is_file() and _mtime(benchmark_file) < cutoff:
                shutil.rmtree(d)
                cleaned += 1

    return cleaned


def _mtime(path: Path) -> float:
    """获取文件/目录的最后修改时间。"""
    try:
        return os.path.getmtime(str(path))
    except OSError:
        return 0.0
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "from benchmark_lib.cleanup import cleanup; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/cleanup.py
git commit -m "feat(benchmarks): add cleanup module with 7-day retention and hard protection"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 8: 报告渲染模块 `benchmarks/benchmark_lib/report.py`

**Files:**
- Create: `benchmarks/benchmark_lib/report.py`

- [ ] **Step 1: 编写 Markdown 报告渲染**

```python
"""Markdown 报告渲染模块。

从 benchmark.json 数据渲染人类可读的 Markdown 报告。
纯数据驱动，不访问文件系统。
"""


def render_report(data: dict) -> str:
    """将 benchmark JSON 渲染为 Markdown 报告。

    Args:
        data: 符合 schema 2.0 的 benchmark JSON 对象

    Returns:
        Markdown 格式的报告字符串
    """
    meta = data["meta"]
    rounds = data["rounds"]
    conv = data["convergence"]
    summary = data["summary"]

    lines = []
    lines.append("# 流水线性能报告")
    lines.append("")
    lines.append(f"**Run ID**: `{meta['run_id']}`")
    lines.append(f"**时间**: {meta['timestamp_start']} ~ {meta['timestamp_end']}")
    lines.append(f"**Git Commit**: `{meta['git_commit']}`")
    lines.append(f"**配置**: max_retries={meta.get('max_retries', '-')}, strategy={meta.get('block_strategy', '-')}")
    lines.append("")

    # ── 收敛曲线 ──
    lines.append("## 收敛曲线")
    lines.append("")
    lines.append(f"**终止原因**: {conv['termination_reason']}")
    if conv["rounds_to_converge"] is not None:
        lines.append(f"**收敛于第 {conv['rounds_to_converge']} 轮**")
    lines.append("")

    if conv["series"]:
        lines.append("| Round | P0 | P1 | P2 | AI_FAIL |")
        lines.append("|-------|----|----|----|---------|")
        for s in conv["series"]:
            ai = s.get("AI_FAIL", -1)
            ai_str = str(ai) if ai >= 0 else "-"
            lines.append(f"| {s['round']} | {s['P0']} | {s['P1']} | {s['P2']} | {ai_str} |")
        lines.append("")

    # ── 各轮次详情 ──
    lines.append("## 各轮次详情")
    lines.append("")
    lines.append("| Round | Agent | Phase | Duration(s) | Tokens | Tools | Cache Hit | Result |")
    lines.append("|-------|-------|-------|-------------|--------|-------|-----------|--------|")
    for r in rounds:
        rn = r["round"]
        for role_key in ("coder", "reviewer"):
            entry = r.get(role_key)
            if entry is None:
                continue
            dur_s = round(entry["duration_ms"] / 1000, 0)
            tok = entry["total_tokens"]
            tools = entry["total_tool_uses"]
            usage = entry.get("usage", {})
            cache_hit = ""
            inp = usage.get("input_tokens", 0)
            cr = usage.get("cache_read_input_tokens", 0)
            if inp > 0:
                cache_hit = f"{round(cr / inp * 100, 0)}%"
            result = entry.get("result", "-") if role_key == "reviewer" else "-"
            lines.append(
                f"| {rn} | {role_key} | {entry['phase']} | {dur_s} | {tok} | {tools} | {cache_hit} | {result} |"
            )
    lines.append("")

    # ── 汇总 ──
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- **总耗时**: {summary['total_duration_ms'] / 1000:.0f}s")
    lines.append(f"- **总 Token**: {summary['total_tokens']:,}")
    lines.append(f"- **总 Tool Uses**: {summary['total_tool_uses']}")
    lines.append("")
    lines.append("| 维度 | Coder | Reviewer |")
    lines.append("|------|-------|----------|")
    s_coder = summary["coder"]
    s_reviewer = summary["reviewer"]
    lines.append(f"| Tokens | {s_coder['total_tokens']:,} | {s_reviewer['total_tokens']:,} |")
    lines.append(f"| Duration(s) | {s_coder['total_duration_ms'] / 1000:.0f} | {s_reviewer['total_duration_ms'] / 1000:.0f} |")
    lines.append(f"| Avg Tokens/Call | {s_coder['avg_tokens_per_call']:,} | {s_reviewer['avg_tokens_per_call']:,} |")
    lines.append("")

    # ── 缓存与收敛 ──
    ce = summary["cache_efficiency"]
    lines.append(f"- **缓存命中率**: {ce['cache_hit_ratio'] * 100:.1f}%  "
                 f"(cache_read={ce['total_cache_read_tokens']:,}, input={ce['total_input_tokens']:,})")
    lines.append(f"- **是否收敛**: {'✅' if summary['converged'] else '❌'}")

    # ── 模型使用 ──
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

    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "from benchmark_lib.report import render_report; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/report.py
git commit -m "feat(benchmarks): add Markdown report rendering module"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 9: 合成引擎 `benchmarks/benchmark_lib/synthesize.py`

**Files:**
- Create: `benchmarks/benchmark_lib/synthesize.py`

- [ ] **Step 1: 编写合成引擎**

```python
"""合成引擎。

合并 dumps/{run_id}.jsonl（性能数据）和 {run_id}/pipeline-log.jsonl（结构数据），
生成符合 schema 2.0 的 benchmark.json。
"""

import json
import os
import subprocess
from pathlib import Path

from benchmark_lib.config import load_config, resolve_path
from benchmark_lib.models import get_timestamp_cst


def synthesize(run_id: str, project_dir: str = ".") -> dict:
    """合成 benchmark.json 数据。

    Args:
        run_id: 流水线运行 ID
        project_dir: 项目根目录

    Returns:
        符合 schema 2.0 的完整 JSON 对象

    Raises:
        FileNotFoundError: dumps/{run_id}.jsonl 不存在
    """
    config = load_config(project_dir)
    output_dir = resolve_path(project_dir, config.paths.output_dir)
    dumps_dir = resolve_path(project_dir, config.paths.dumps_dir)

    # 1. 读取 dump 数据
    dump_path = dumps_dir / f"{run_id}.jsonl"
    if not dump_path.is_file():
        raise FileNotFoundError(f"dump file not found: {dump_path}")

    dump_records = _read_jsonl(dump_path)

    # 2. 读取 pipeline-log
    log_path = output_dir / config.pipeline_log_template.format(run_id=run_id)
    log_records = _read_jsonl(log_path) if log_path.is_file() else []

    # 3. 按 node 关键词分类 dump 条目，按时序匹配
    coder_dumps = _filter_dumps(dump_records, config.node_keywords.coder)
    reviewer_dumps = _filter_dumps(dump_records, config.node_keywords.reviewer)

    # 4. 按 pipeline-log 分组构建 rounds
    rounds = _build_rounds(log_records, coder_dumps, reviewer_dumps)

    # 5. 提取 issues
    _attach_issues(rounds, run_id, project_dir)

    # 6. 计算收敛
    convergence = _compute_convergence(rounds)

    # 7. 计算汇总
    summary = _compute_summary(rounds, convergence, dump_records)

    # 8. 获取 git commit
    git_commit = _get_git_commit(project_dir)

    # 9. 获取时间戳
    ts_start = get_timestamp_cst()
    ts_end = ts_start

    if dump_records:
        first_ts = dump_records[0].get("ts")
        last_ts = dump_records[-1].get("ts")
        from datetime import datetime, timezone, timedelta
        CST = timezone(timedelta(hours=8))
        if first_ts:
            ts_start = datetime.fromtimestamp(first_ts, tz=CST).isoformat()
        if last_ts:
            ts_end = datetime.fromtimestamp(last_ts, tz=CST).isoformat()

    return {
        "schema_version": "2.0",
        "meta": {
            "run_id": run_id,
            "timestamp_start": ts_start,
            "timestamp_end": ts_end,
            "git_commit": git_commit,
            "max_retries": 3,
            "block_strategy": "strict",
        },
        "rounds": rounds,
        "convergence": convergence,
        "summary": summary,
    }


def _read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件，跳过空行和解析失败的行。"""
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _filter_dumps(dump_records: list[dict], keywords: list[str]) -> list[dict]:
    """筛选包含指定关键词的 dump 条目，按 ts 排序。"""
    result = []
    for rec in dump_records:
        desc = rec.get("description", "")
        if any(kw in desc for kw in keywords):
            result.append(rec)
    result.sort(key=lambda r: r.get("ts", 0))
    return result


def _classify_dump(rec: dict, config) -> str | None:
    """将 dump 条目分类为 'coder' / 'reviewer' / None（dev agent，跳过）。"""
    desc = rec.get("description", "")
    for kw in config.node_keywords.coder:
        if kw in desc:
            return "coder"
    for kw in config.node_keywords.reviewer:
        if kw in desc:
            return "reviewer"
    return None


def _build_rounds(
    log_records: list[dict],
    coder_dumps: list[dict],
    reviewer_dumps: list[dict],
) -> list[dict]:
    """合并 pipeline-log 和 dump 数据，构建 rounds 列表。

    pipeline-log 条目按时序提供轮次结构和 verdict。
    dump 条目按时序提供性能数据（duration、tokens、usage）。
    两者按时序 zip 合并。
    """
    rounds = []
    c_idx = 0
    r_idx = 0

    for log in log_records:
        node = log.get("node", "")
        round_num = log.get("round", 1)
        verdict = log.get("verdict", "")

        if node == "coder":
            dump = coder_dumps[c_idx] if c_idx < len(coder_dumps) else {}
            c_idx += 1
            phase = "generate" if round_num == 1 else "fix"
            rounds.append({
                "round": round_num,
                "coder": {
                    "phase": phase,
                    "duration_ms": dump.get("duration_ms", 0),
                    "total_tokens": dump.get("total_tokens", 0),
                    "total_tool_uses": dump.get("total_tool_uses", 0),
                    "usage": dump.get("usage", {}),
                },
                "reviewer": None,
            })
        elif node == "reviewer":
            dump = reviewer_dumps[r_idx] if r_idx < len(reviewer_dumps) else {}
            r_idx += 1

            # 找到当前 round 的 coder 条目并附加 reviewer
            for rnd in rounds:
                if rnd["round"] == round_num and rnd["reviewer"] is None:
                    rnd["reviewer"] = {
                        "phase": "review",
                        "duration_ms": dump.get("duration_ms", 0),
                        "total_tokens": dump.get("total_tokens", 0),
                        "total_tool_uses": dump.get("total_tool_uses", 0),
                        "usage": dump.get("usage", {}),
                        "result": verdict,
                        "issues": {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1},
                    }
                    break

    return rounds


def _attach_issues(rounds: list[dict], run_id: str, project_dir: str) -> None:
    """从 review-output 产物读取 issues 并挂载到 reviewer 记录。"""
    for r in rounds:
        rv = r.get("reviewer")
        if rv is None:
            continue
        rn = r["round"]

        pre_check_path = Path(project_dir) / "review-output" / run_id / f"r{rn}-pre-check-result.json"
        ai_path = Path(project_dir) / "review-output" / run_id / f"r{rn}-review-result.json"

        issues = {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1}

        if pre_check_path.is_file():
            try:
                with open(pre_check_path, "r") as f:
                    data = json.load(f)
                for issue in data.get("issues", []):
                    level = issue.get("level", "")
                    if level in ("P0", "P1", "P2"):
                        issues[level] += 1
            except (json.JSONDecodeError, OSError):
                pass

        if ai_path.is_file():
            try:
                with open(ai_path, "r") as f:
                    ai_data = json.load(f)
                ai_issues = ai_data.get("issues", [])
                issues["AI_FAIL"] = sum(
                    1 for i in ai_issues if i.get("result") == "FAIL"
                )
            except (json.JSONDecodeError, OSError):
                pass

        rv["issues"] = issues


def _compute_convergence(rounds: list[dict]) -> dict:
    """计算收敛曲线。"""
    series = []
    rounds_to_converge = None
    termination_reason = "max_retries_exceeded"

    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            issues = rv.get("issues", {})
            point = {
                "round": r["round"],
                "P0": issues.get("P0", 0),
                "P1": issues.get("P1", 0),
                "P2": issues.get("P2", 0),
                "AI_FAIL": issues.get("AI_FAIL", -1),
            }
            series.append(point)

            if point["P0"] == 0 and rv.get("result") == "REVIEW_PASSED":
                if rounds_to_converge is None:
                    rounds_to_converge = r["round"]

    if rounds_to_converge is not None:
        termination_reason = "converged"

    return {
        "rounds_to_converge": rounds_to_converge,
        "termination_reason": termination_reason,
        "series": series,
    }


def _compute_summary(rounds: list[dict], convergence: dict, dump_records: list[dict]) -> dict:
    """计算汇总指标。"""
    total_duration = 0
    total_tokens = 0
    total_tools = 0
    coder_tokens = 0
    coder_duration = 0
    coder_calls = 0
    reviewer_tokens = 0
    reviewer_duration = 0
    reviewer_calls = 0
    total_cache_read = 0
    total_input = 0

    for r in rounds:
        for role_key in ("coder", "reviewer"):
            entry = r.get(role_key)
            if entry is None:
                continue
            dur = entry.get("duration_ms", 0)
            tok = entry.get("total_tokens", 0)
            tools = entry.get("total_tool_uses", 0)
            usage = entry.get("usage", {})

            total_duration += dur
            total_tokens += tok
            total_tools += tools

            cr = usage.get("cache_read_input_tokens", 0)
            inp = usage.get("input_tokens", 0)
            total_cache_read += cr
            total_input += inp

            if role_key == "coder":
                coder_tokens += tok
                coder_duration += dur
                coder_calls += 1
            else:
                reviewer_tokens += tok
                reviewer_duration += dur
                reviewer_calls += 1

    total_cache_base = total_cache_read + total_input
    cache_ratio = (total_cache_read / total_cache_base) if total_cache_base > 0 else 0.0

    models_used = {}
    for rec in dump_records:
        model = rec.get("model", "")
        if model:
            models_used[model] = models_used.get(model, 0) + 1

    return {
        "total_duration_ms": total_duration,
        "total_tokens": total_tokens,
        "total_tool_uses": total_tools,
        "coder": {
            "total_tokens": coder_tokens,
            "total_duration_ms": coder_duration,
            "avg_tokens_per_call": (coder_tokens // coder_calls) if coder_calls else 0,
        },
        "reviewer": {
            "total_tokens": reviewer_tokens,
            "total_duration_ms": reviewer_duration,
            "avg_tokens_per_call": (reviewer_tokens // reviewer_calls) if reviewer_calls else 0,
        },
        "cache_efficiency": {
            "total_cache_read_tokens": total_cache_read,
            "total_input_tokens": total_input,
            "cache_hit_ratio": round(cache_ratio, 4),
        },
        "converged": convergence["rounds_to_converge"] is not None,
        "models_used": models_used,
    }


def _get_git_commit(project_dir: str) -> str:
    """获取当前 git commit hash。"""
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "from benchmark_lib.synthesize import synthesize; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/synthesize.py
git commit -m "feat(benchmarks): add synthesize engine merging pipeline-log and dumps"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 10: CLI 入口 `benchmarks/benchmark_lib/cli.py`

**Files:**
- Create: `benchmarks/benchmark_lib/cli.py`

- [ ] **Step 1: 编写 CLI 入口**

```python
"""CLI 入口 — 基准测试命令行工具。

命令：
  synthesize  合成 benchmark.json 和 report.md
  cleanup     清理过期数据
"""

import argparse
import json
import sys
from pathlib import Path

from benchmark_lib.config import load_config
from benchmark_lib.models import validate_benchmark
from benchmark_lib.synthesize import synthesize
from benchmark_lib.report import render_report
from benchmark_lib.cleanup import cleanup


def _detect_run_id(project_dir: str) -> str | None:
    """从 review-output/.current-run 自动检测 run_id。"""
    current_run_path = Path(project_dir) / "review-output" / ".current-run"
    if not current_run_path.is_file():
        return None
    try:
        with open(current_run_path, "r") as f:
            return json.load(f).get("run_id", "")
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def cmd_synthesize(args):
    """合成 benchmark.json 和 report.md。"""
    project_dir = args.project_dir

    # 自动检测 run_id
    run_id = args.run_id
    if not run_id:
        run_id = _detect_run_id(project_dir)
        if not run_id:
            print("Error: 无法自动检测 run_id。请显式指定 run_id 或确保 .current-run 文件存在。", file=sys.stderr)
            sys.exit(1)

    config = load_config(project_dir)
    output_dir = Path(project_dir) / config.paths.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 合成
    try:
        data = synthesize(run_id, project_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 校验
    try:
        validate_benchmark(data)
    except Exception as e:
        print(f"Error: JSON Schema 校验失败 — {e}", file=sys.stderr)
        sys.exit(1)

    # 写入 benchmark.json
    json_path = output_dir / "benchmark.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Benchmark saved: {json_path}", file=sys.stderr)

    # 渲染并写入 report.md
    md_path = output_dir / "report.md"
    with open(md_path, "w") as f:
        f.write(render_report(data))
    print(f"Report saved:   {md_path}", file=sys.stderr)

    # 清理过期数据
    cleaned = cleanup(project_dir, current_run_id=run_id)
    if cleaned > 0:
        print(f"Cleaned {cleaned} expired benchmark(s).", file=sys.stderr)


def cmd_cleanup(args):
    """清理过期数据。"""
    project_dir = args.project_dir
    run_id = _detect_run_id(project_dir)

    cleaned = cleanup(project_dir, current_run_id=run_id)
    if args.dry_run:
        print(f"Would clean {cleaned} expired benchmark(s). (dry-run)")
    else:
        print(f"Cleaned {cleaned} expired benchmark(s).")


def main():
    parser = argparse.ArgumentParser(
        prog="benchmark-lib",
        description="基准测试数据合成、报告、清理工具",
    )
    sub = parser.add_subparsers(dest="command")

    # synthesize
    p_syn = sub.add_parser("synthesize", help="合成 benchmark.json 和 report.md")
    p_syn.add_argument("run_id", nargs="?", default="",
                       help="流水线 run_id（留空则从 .current-run 自动检测）")
    p_syn.add_argument("--project-dir", default=".", help="项目根目录")

    # cleanup
    p_cln = sub.add_parser("cleanup", help="清理过期基准测试数据")
    p_cln.add_argument("--project-dir", default=".", help="项目根目录")
    p_cln.add_argument("--dry-run", action="store_true", help="仅预览，不实际删除")

    args = parser.parse_args()
    if args.command == "synthesize":
        cmd_synthesize(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 CLI 模块**

```bash
cd /Users/chenyi/ai-project/spark && python3 -m benchmark_lib.cli --help
```

Expected: 显示帮助信息和子命令列表

- [ ] **Step 3: 提交**

```bash
git add benchmarks/benchmark_lib/cli.py
git commit -m "feat(benchmarks): add CLI entry with synthesize and cleanup commands"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 11: 性能分析 Skill `.claude/skills/spark-benchmarks.skill.md`

**Files:**
- Create: `.claude/skills/spark-benchmarks.skill.md`

- [ ] **Step 1: 创建 Skill 文件**

```markdown
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
```

- [ ] **Step 2: 提交**

```bash
git add .claude/skills/spark-benchmarks.skill.md
git commit -m "feat(benchmarks): add spark:benchmarks skill for performance analysis"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 12: 更新 `.claude/settings.json`

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: 更新 Hook 和 Skill 配置**

当前 settings.json 中的 Stop hook：
```json
"Stop": [
    {
        "hooks": [
            {
                "type": "command",
                "command": "bash ${CLAUDE_PROJECT_DIR}/benchmarks/hooks/synthesize-benchmark.sh"
            }
        ]
    }
]
```

改为：
```json
"Stop": [
    {
        "hooks": [
            {
                "type": "command",
                "command": "python3 -m benchmark_lib.cli synthesize --project-dir ${CLAUDE_PROJECT_DIR:-.}"
            }
        ]
    }
]
```

完整修改后的 settings.json：

```json
{
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": "bash ${CLAUDE_PROJECT_DIR}/hooks/block-agents-write.sh"
                    }
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Agent",
                "hooks": [
                    {
                        "type": "command",
                        "command": "bash ${CLAUDE_PROJECT_DIR}/benchmarks/hooks/dump-agent-payload.sh"
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -m benchmark_lib.cli synthesize --project-dir ${CLAUDE_PROJECT_DIR:-.}"
                    }
                ]
            }
        ]
    },
    "permissions": {
        "allow": [
            "Bash(python3 -m pipeline_engine.cli *)",
            "Bash(python3 -m code_check.cli *)",
            "Bash(python3 -m benchmark_lib.cli *)"
        ]
    }
}
```

关键变化：
1. Stop hook 从 `bash synthesize-benchmark.sh` 改为 `python3 -m benchmark_lib.cli synthesize --project-dir`
2. permissions.allow 新增 `Bash(python3 -m benchmark_lib.cli *)`

- [ ] **Step 2: 验证 JSON 格式**

```bash
cd /Users/chenyi/ai-project/spark && python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3: 提交**

```bash
git add .claude/settings.json
git commit -m "feat(benchmarks): switch Stop hook to Python CLI, add benchmark permission"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 13: 删除旧文件

**Files:**
- Delete: `benchmarks/hooks/schema.py`
- Delete: `benchmarks/hooks/compare.py`
- Delete: `benchmarks/hooks/synthesize-benchmark.sh`
- Delete: `benchmarks/hooks/__pycache__/` (目录)

- [ ] **Step 1: 删除旧文件**

```bash
cd /Users/chenyi/ai-project/spark
rm benchmarks/hooks/schema.py
rm benchmarks/hooks/compare.py
rm benchmarks/hooks/synthesize-benchmark.sh
rm -rf benchmarks/hooks/__pycache__
```

- [ ] **Step 2: 确认旧文件全部删除**

```bash
ls benchmarks/hooks/
```

Expected: 只剩 `dump-agent-payload.sh`

- [ ] **Step 3: 提交**

```bash
git add -A benchmarks/hooks/
git commit -m "refactor(benchmarks): remove old schema.py, compare.py, synthesize-benchmark.sh"

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 14: 端到端集成验证

**Files:**
- 使用现有 `benchmarks/dumps/` 中的数据

- [ ] **Step 1: 用现有 dump 数据验证合成链路**

先找到一份现有的 dump 文件作为测试数据：

```bash
cd /Users/chenyi/ai-project/spark
ls benchmarks/dumps/
```

选择一个 run_id（从文件名提取，如 `session-08dee738-1c09-4b20-8a52-57c58ef5053c`），手动创建对应的 pipeline-log.jsonl 模拟数据：

```bash
# 创建一个测试用的 run_id
TEST_RUN="test-20260715"

# 复制一份 dump 数据
cp benchmarks/dumps/session-08dee738-1c09-4b20-8a52-57c58ef5053c.jsonl "benchmarks/dumps/${TEST_RUN}.jsonl"

# 创建模拟的 pipeline-log.jsonl
mkdir -p "benchmarks/${TEST_RUN}"
cat > "benchmarks/${TEST_RUN}/pipeline-log.jsonl" << 'EOF'
{"ts": 1782313159, "round": 1, "node": "coder", "status": "success", "verdict": ""}
{"ts": 1782313247, "round": 1, "node": "reviewer", "status": "success", "verdict": "REVIEW_FAILED"}
{"ts": 1782313584, "round": 2, "node": "coder", "status": "success", "verdict": ""}
{"ts": 1782313849, "round": 2, "node": "reviewer", "status": "success", "verdict": "REVIEW_PASSED"}
EOF
```

- [ ] **Step 2: 运行合成命令**

```bash
cd /Users/chenyi/ai-project/spark && python3 -m benchmark_lib.cli synthesize "${TEST_RUN}"
```

Expected: 输出 `Benchmark saved: ...` 和 `Report saved: ...`，无报错。

- [ ] **Step 3: 验证产物**

```bash
# 检查 benchmark.json 格式正确
python3 -c "
import json
with open('benchmarks/${TEST_RUN}/benchmark.json') as f:
    d = json.load(f)
print(f'schema_version={d[\"schema_version\"]}')
print(f'run_id={d[\"meta\"][\"run_id\"]}')
print(f'rounds={len(d[\"rounds\"])}')
print(f'converged={d[\"summary\"][\"converged\"]}')
print(f'total_tokens={d[\"summary\"][\"total_tokens\"]}')
"
```

Expected: 输出有意义的数据（rounds >= 1, 有 token 数据等）

- [ ] **Step 4: 验证报告**

```bash
head -20 "benchmarks/${TEST_RUN}/report.md"
```

Expected: Markdown 报告以 `# 流水线性能报告` 开头

- [ ] **Step 5: 验证 Schema 校验**

```bash
python3 -c "
from benchmark_lib.models import validate_benchmark
import json
with open('benchmarks/${TEST_RUN}/benchmark.json') as f:
    d = json.load(f)
validate_benchmark(d)
print('Schema validation passed')
"
```

Expected: `Schema validation passed`

- [ ] **Step 6: 验证清理 dry-run**

```bash
cd /Users/chenyi/ai-project/spark && python3 -m benchmark_lib.cli cleanup --dry-run
```

Expected: 输出 `Would clean 0 expired benchmark(s). (dry-run)`（当前数据都不超过 7 天）

- [ ] **Step 7: 清理测试数据**

```bash
rm -rf "benchmarks/${TEST_RUN}" "benchmarks/dumps/${TEST_RUN}.jsonl"
```

- [ ] **Step 8: 提交**

```bash
# 如果有任何集成测试修改，在此提交
# 集成测试本身不产生代码变更，可跳过此提交
echo "Integration test passed"
```

---

## 任务依赖图

```
Task 1  (config.yaml)
Task 2  (__init__.py)       ← 无依赖
Task 3  (config.py)         ← 依赖 Task 1
Task 4  (models.py)         ← 无依赖
Task 5  (dump hook)         ← 无依赖
Task 6  (pipeline_engine)   ← 无依赖
Task 7  (cleanup.py)        ← 依赖 Task 3
Task 8  (report.py)         ← 无依赖
Task 9  (synthesize.py)     ← 依赖 Task 3, 4
Task 10 (cli.py)            ← 依赖 Task 3, 7, 8, 9
Task 11 (skill)             ← 依赖 Task 10
Task 12 (settings.json)     ← 依赖 Task 10
Task 13 (delete old)        ← 依赖 Task 10, 12
Task 14 (integration test)  ← 依赖 Task 13
```

## 并行执行建议

以下任务组之间无依赖，可并行执行：
- **组 A:** Task 1, 2, 4, 5, 6, 8
- **组 B:** Task 3（依赖 Task 1）
- **组 C:** Task 7（依赖 Task 3）
- **组 D:** Task 9（依赖 Task 3, 4）
- **组 E:** Task 10（依赖 Task 3, 7, 8, 9）
- **组 F:** Task 11, 12, 13, 14（依赖 Task 10）

推荐开发顺序：组 A → 组 B + 组 C + 组 D（并行）→ 组 E → 组 F
