# 性能日志系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `/build` 流水线增加基于 Claude Code Hooks 的自动性能数据采集系统，每次运行后产出 benchmarks/run-*.json 和 .md

**Architecture:** PostToolUse(Agent) hook 按 Agent 调用粒度采集指标并追加到 session JSONL；Stop hook 在会话结束时从 JSONL + review-output/r*- 产物中合成完整性能日志

**Tech Stack:** Bash (Claude Code hooks), jq (JSON 处理), Python3 (JSON 合成和 Markdown 渲染)

---

## 目录结构

```
benchmarks/
├── hooks/                              ← 源码（commit）
│   ├── dump-agent-payload.sh          ← PostToolUse hook — 采集 JSONL + reviewer 产物重命名
│   ├── synthesize-benchmark.sh        ← Stop hook — 合成编排
│   └── schema.py                      ← Python 引擎 — 推断 + 指纹 + 合成 + 渲染
├── dumps/                              ← 运行时中间产物（gitignore）
│   └── session-{id}.jsonl             ← PostToolUse 逐条追加
├── run-YYYYMMDD-HHmmss-{slug}.json    ← 最终产出（gitignore）
└── run-YYYYMMDD-HHmmss-{slug}.md      ← 最终产出（gitignore）
```

## 文件规划

| 文件 | 动作 | 职责 |
|------|------|------|
| `benchmarks/hooks/dump-agent-payload.sh` | 新建 | PostToolUse hook — 采集 JSONL + reviewer 产物重命名 |
| `benchmarks/hooks/synthesize-benchmark.sh` | 新建 | Stop hook — 合成编排 |
| `benchmarks/hooks/schema.py` | 新建 | Python 模块 — 数据结构 + round 推断 + 指纹计算 + MD 渲染 |
| `.claude/settings.json` | 修改 | PostToolUse 路径更新 + 添加 Stop hook 配置 |
| `.gitignore` | 修改 | 排除 `benchmarks/dumps/` 和 `benchmarks/run-*` |

`dump-agent-payload.sh` 保持轻量（<60 行），只做采集不参与计算。`synthesize-benchmark.sh` 做编排：调用 Python 模块完成推断、合成、渲染三步。

---

### Task 1: Python 核心模块 — 数据结构和合成逻辑

**Files:**
- Create: `benchmarks/hooks/schema.py`

- [ ] **Step 1: 创建 `schema.py` — 写入完整模块**

这个文件是合成引擎，暴露一个入口函数 `from_jsonl(session_id, jsonl_path, review_dir, project_dir) -> dict`。

```python
#!/usr/bin/env python3
"""性能日志合成引擎。

入口: from_jsonl(session_id, jsonl_path, review_dir, project_dir) -> dict
返回符合 schema v1.0 的完整 JSON 对象，调用方负责写入文件。
"""

import json
import os
import hashlib
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

# ── 文件列表：指纹计算 ──

CODER_GLOB_DIRS = ["agents/coder/"]
CODER_GLOB_EXTS = [".md"]
CODER_EXTRA_FILES = ["agents/scheduler/pipeline.yaml"]

REVIEWER_GLOB_DIRS = [
    "agents/reviewer/check_system/code_check/",
    "agents/reviewer/check_system/rules/",
]
REVIEWER_GLOB_EXTS = [".py", ".yaml"]
REVIEWER_EXTRA_FILES = [
    "agents/reviewer/check_system/code-check-config.yaml",
    "agents/reviewer/hooks/review-pre-hook.sh",
    "agents/reviewer/hooks/review-post-hook.sh",
]


# ── 指纹 ──

def _compute_fingerprint(project_dir: str, glob_dirs: list[str],
                         extensions: list[str], extra_files: list[str]) -> tuple[str, str, int]:
    """返回 (short_fingerprint, full_fingerprint, file_count)。"""
    import hashlib

    files = []
    for d in glob_dirs:
        full_dir = os.path.join(project_dir, d)
        if not os.path.isdir(full_dir):
            continue
        for root, _, filenames in os.walk(full_dir):
            for fn in filenames:
                if any(fn.endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, fn))
    for ef in extra_files:
        fp = os.path.join(project_dir, ef)
        if os.path.isfile(fp):
            files.append(fp)

    files = sorted(set(files))
    hasher = hashlib.sha256()
    for fp in files:
        try:
            with open(fp, "rb") as fh:
                hasher.update(fh.read())
        except OSError:
            pass

    full_hash = hasher.hexdigest()
    return full_hash[:8], "sha256:" + full_hash, len(files)


# ── Round 推断 ──

def _infer_rounds(records: list[dict]) -> list[dict]:
    """从原始 JSONL 记录推断结构化为 rounds[] 的数据。

    每条 record 预期包含:
      description, duration_ms, total_tokens, total_tool_uses, usage, last_message_snippet

    返回 rounds 列表，每条:
      { "round": int, "coder": {...} | null, "reviewer": {...} | null }
    """
    REVIEW_PATTERNS = re.compile(r"review|审查|reviewer", re.IGNORECASE)

    rounds = []
    current_round = 0
    prev_role = None
    current_entry = {"round": current_round, "coder": None, "reviewer": None}

    for rec in records:
        desc = rec.get("description", "")
        is_reviewer = bool(REVIEW_PATTERNS.search(desc))
        role = "reviewer" if is_reviewer else "coder"

        if role == "coder" and prev_role == "reviewer":
            # 开始新一轮
            rounds.append(current_entry)
            current_round += 1
            current_entry = {"round": current_round, "coder": None, "reviewer": None}

        phase = _determine_phase(role, prev_role)
        agent_data = _build_agent_entry(role, phase, rec)

        if role == "coder":
            current_entry["coder"] = agent_data
        else:
            current_entry["reviewer"] = agent_data

        prev_role = role

    # 推最后一轮
    if current_entry["coder"] is not None or current_entry["reviewer"] is not None:
        rounds.append(current_entry)

    return rounds


def _determine_phase(role: str, prev_role: str | None) -> str:
    if role == "coder":
        return "generate" if prev_role is None else "fix"
    return "review"


def _build_agent_entry(role: str, phase: str, rec: dict) -> dict:
    entry = {
        "phase": phase,
        "duration_ms": rec.get("duration_ms", 0),
        "total_tokens": rec.get("total_tokens", 0),
        "total_tool_uses": rec.get("total_tool_uses", 0),
        "usage": rec.get("usage", {}),
    }
    if role == "reviewer":
        entry["result"] = _extract_review_result(rec.get("last_message_snippet", ""))
    return entry


def _extract_review_result(last_message: str) -> str:
    if "REVIEW_PASSED" in last_message:
        return "REVIEW_PASSED"
    if "REVIEW_ERROR" in last_message:
        return "REVIEW_ERROR"
    if "REVIEW_FAILED" in last_message:
        return "REVIEW_FAILED"
    return "UNKNOWN"


# ── Issue 提取 ──

def _extract_issues(review_dir: str, round_num: int) -> dict:
    """从 r{round_num}-pre-check-result.json 提取 P0/P1/P2 数量。"""
    pre_check_path = os.path.join(
        review_dir, f"r{round_num}-pre-check-result.json"
    )
    issues = {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1}

    if not os.path.isfile(pre_check_path):
        return issues

    try:
        with open(pre_check_path, "r") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return issues

    for issue in data.get("issues", []):
        level = issue.get("level", "")
        if level in ("P0", "P1", "P2"):
            issues[level] += 1

    # 检查 AI 检查结果
    ai_path = os.path.join(review_dir, f"r{round_num}-review-result.json")
    if os.path.isfile(ai_path):
        try:
            with open(ai_path, "r") as fh:
                ai_data = json.load(fh)
            ai_issues = ai_data.get("issues", [])
            ai_fail_count = sum(
                1 for i in ai_issues if i.get("result") == "FAIL"
            )
            issues["AI_FAIL"] = ai_fail_count
        except (json.JSONDecodeError, OSError):
            pass

    return issues


# ── 汇总 ──

def _compute_summary(rounds: list[dict], convergence: dict) -> dict:
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

    cache_ratio = (total_cache_read / total_input) if total_input > 0 else 0.0

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
    }


# ── 收敛 ──

def _compute_convergence(rounds: list[dict], max_retries: int) -> dict:
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

            # 判定收敛：P0 = 0 且 AI_FAIL = 0 且 result = REVIEW_PASSED
            if point["P0"] == 0 and (point["AI_FAIL"] == 0 or point["AI_FAIL"] == -1):
                if rv.get("result") == "REVIEW_PASSED":
                    if rounds_to_converge is None:
                        rounds_to_converge = r["round"]

    if rounds_to_converge is not None:
        termination_reason = "converged"

    return {
        "rounds_to_converge": rounds_to_converge,
        "termination_reason": termination_reason,
        "series": series,
    }


# ── 需求 slug ──

def _slugify(text: str, max_len: int = 30) -> str:
    """将中文需求文本转为短 slug。"""
    # 取前 max_len 个非空白字符，移除特殊字符
    slug = "".join(ch for ch in text.strip()[:max_len] if ch.isalnum() or ch in "_-")
    slug = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "", slug)
    return slug[:max_len] if slug else "unnamed"


# ── 入口 ──

def from_jsonl(session_id: str, jsonl_path: str,
               review_dir: str, project_dir: str,
               requirement: str = "", max_retries: int = 3,
               block_strategy: str = "strict") -> dict:
    """从 session dump 和 review 产物合成完整性能日志。"""

    # 1. 读 JSONL
    records = []
    if os.path.isfile(jsonl_path):
        with open(jsonl_path, "r") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    if not records:
        return None

    # 2. 计算指纹
    coder_short, coder_full, coder_count = _compute_fingerprint(
        project_dir, CODER_GLOB_DIRS, CODER_GLOB_EXTS, CODER_EXTRA_FILES
    )
    reviewer_short, reviewer_full, reviewer_count = _compute_fingerprint(
        project_dir, REVIEWER_GLOB_DIRS, REVIEWER_GLOB_EXTS, REVIEWER_EXTRA_FILES
    )

    # 3. 推断 rounds
    rounds = _infer_rounds(records)

    # 4. 挂载 issue 数据
    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            rv["issues"] = _extract_issues(review_dir, r["round"])

    # 5. 收敛分析
    convergence = _compute_convergence(rounds, max_retries)

    # 6. 汇总
    summary = _compute_summary(rounds, convergence)

    # 7. 元信息
    first_ts = records[0].get("ts", 0)
    last_ts = records[-1].get("ts", 0)
    tz = CST
    start_dt = datetime.fromtimestamp(first_ts, tz=tz).isoformat() if first_ts else ""
    end_dt = datetime.fromtimestamp(last_ts, tz=tz).isoformat() if last_ts else ""
    slug = _slugify(requirement) if requirement else "unnamed"
    run_id_ts = datetime.fromtimestamp(first_ts, tz=tz).strftime("%Y%m%d-%H%M%S") if first_ts else "unknown"
    run_id = f"run-{run_id_ts}"

    # 8. 获取 git commit
    git_commit = ""
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        pass

    return {
        "schema_version": "1.0",
        "meta": {
            "run_id": run_id,
            "timestamp_start": start_dt,
            "timestamp_end": end_dt,
            "requirement_slug": slug,
            "requirement_full": requirement,
            "config": {
                "max_retries": max_retries,
                "block_strategy": block_strategy,
                "block_on": ["P0"],
            },
            "git_commit_at_start": git_commit,
        },
        "agents": {
            "coder": {
                "fingerprint": coder_short,
                "fingerprint_full": coder_full,
                "source_file_count": coder_count,
            },
            "reviewer": {
                "fingerprint": reviewer_short,
                "fingerprint_full": reviewer_full,
                "source_file_count": reviewer_count,
            },
        },
        "rounds": rounds,
        "convergence": convergence,
        "summary": summary,
    }


# ── Markdown 渲染 ──

def render_md(data: dict) -> str:
    """从 JSON data 渲染人类可读的 Markdown 报告。"""
    meta = data["meta"]
    agents = data["agents"]
    rounds = data["rounds"]
    conv = data["convergence"]
    summary = data["summary"]

    lines = []
    lines.append("# 流水线性能报告")
    lines.append("")
    lines.append(f"**Run ID**: `{meta['run_id']}`")
    lines.append(f"**时间**: {meta['timestamp_start']} ~ {meta['timestamp_end']}")
    lines.append(f"**需求**: {meta['requirement_full'][:100]}")
    lines.append(f"**Git Commit**: `{meta['git_commit_at_start']}`")
    lines.append(f"**配置**: max_retries={meta['config']['max_retries']}, strategy={meta['config']['block_strategy']}")
    lines.append("")

    # Agents 指纹
    lines.append("## Agent 版本指纹")
    lines.append("")
    lines.append("| Agent | Fingerprint | 源文件数 |")
    lines.append("|-------|-------------|---------|")
    lines.append(f"| coder | `{agents['coder']['fingerprint']}` | {agents['coder']['source_file_count']} |")
    lines.append(f"| reviewer | `{agents['reviewer']['fingerprint']}` | {agents['reviewer']['source_file_count']} |")
    lines.append("")

    # 收敛
    lines.append("## 收敛曲线")
    lines.append("")
    lines.append(f"**终止原因**: {conv['termination_reason']}")
    if conv['rounds_to_converge'] is not None:
        lines.append(f"**收敛于第 {conv['rounds_to_converge']} 轮**")
    lines.append("")

    if conv["series"]:
        lines.append("| Round | P0 | P1 | P2 | AI_FAIL |")
        lines.append("|-------|----|----|----|---------|")
        for s in conv["series"]:
            lines.append(f"| {s['round']} | {s['P0']} | {s['P1']} | {s['P2']} | {s['AI_FAIL']} |")
        lines.append("")

    # 每轮
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

    # 汇总
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
    ce = summary["cache_efficiency"]
    lines.append(f"- **缓存命中率**: {ce['cache_hit_ratio'] * 100:.1f}%  "
                 f"(cache_read={ce['total_cache_read_tokens']:,}, input={ce['total_input_tokens']:,})")
    lines.append(f"- **是否收敛**: {'✅' if summary['converged'] else '❌'}")

    return "\n".join(lines) + "\n"


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 schema.py <session_id> <jsonl_path> [review_dir] [project_dir] [requirement] [max_retries]", file=sys.stderr)
        sys.exit(1)

    sid = sys.argv[1]
    jpath = sys.argv[2]
    rdir = sys.argv[3] if len(sys.argv) > 3 else "agents/reviewer/check_system/review-output"
    pdir = sys.argv[4] if len(sys.argv) > 4 else os.getcwd()
    req = sys.argv[5] if len(sys.argv) > 5 else ""
    mr = int(sys.argv[6]) if len(sys.argv) > 6 else 3

    data = from_jsonl(sid, jpath, rdir, pdir, req, mr)
    if data is None:
        print("No data to synthesize (empty JSONL).", file=sys.stderr)
        sys.exit(0)

    # 输出目录
    benchmarks_dir = os.path.join(pdir, "benchmarks")
    os.makedirs(benchmarks_dir, exist_ok=True)

    run_id = data["meta"]["run_id"]
    slug = data["meta"]["requirement_slug"]
    json_path = os.path.join(benchmarks_dir, f"{run_id}-{slug}.json")
    md_path = os.path.join(benchmarks_dir, f"{run_id}-{slug}.md")

    with open(json_path, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    with open(md_path, "w") as fh:
        fh.write(render_md(data))

    print(f"Benchmark saved: {json_path}", file=sys.stderr)
    print(f"Report saved:   {md_path}", file=sys.stderr)
```

- [ ] **Step 2: 验证 Python 语法和导入**

```bash
cd /Users/chenyi/ai-project/workflow-agent-demo
python3 -c "import ast; ast.parse(open('benchmarks/hooks/schema.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3: 用现有 dump 数据做一次 dry-run 测试**

先确认上次测试的 JSONL 文件存在：
```bash
ls benchmarks/dumps/session-*.jsonl
```

用 CLI 跑一次合成：
```bash
SESSION_ID=$(basename $(ls benchmarks/dumps/session-*.jsonl | head -1) .jsonl | sed 's/session-//')
python3 benchmarks/hooks/schema.py \
  "$SESSION_ID" \
  "benchmarks/dumps/session-${SESSION_ID}.jsonl" \
  "agents/reviewer/check_system/review-output" \
  "." \
  "测试" \
  3
```

Expected: 输出两个文件路径到 stderr，生成 `benchmarks/run-*.json` 和 `benchmarks/run-*.md`

- [ ] **Step 4: 验证 JSON 输出结构**

```bash
python3 -c "
import json
with open('benchmarks/$(ls -t benchmarks/ | head -1)') as f:
    d = json.load(f)
print('schema_version:', d['schema_version'])
print('meta keys:', list(d['meta'].keys()))
print('agents keys:', list(d['agents'].keys()))
print('rounds count:', len(d['rounds']))
print('convergence series:', len(d['convergence']['series']))
print('summary keys:', list(d['summary'].keys()))
"
```

Expected: schema_version=1.0, 各 key 存在

- [ ] **Step 5: 查看生成的 Markdown**

```bash
cat "benchmarks/$(ls -t benchmarks/*.md | head -1)"
```

确认格式完整：标题、Agent 指纹表、收敛曲线表、各轮详情表、汇总

- [ ] **Step 6: Commit**

```bash
git add benchmarks/hooks/schema.py
git commit -m "feat: add benchmark synthesis engine (schema.py)"
```

---

### Task 2: 修改 PostToolUse hook — 添加 reviewer 检测 + 产物重命名

**Files:**
- Modify: `benchmarks/hooks/dump-agent-payload.sh`

- [ ] **Step 1: 读取当前版本**

```bash
cat benchmarks/hooks/dump-agent-payload.sh
```

当前脚本只做了 JSONL 追加。需要新增 reviewer 检测和产物重命名。

- [ ] **Step 2: 替换为完整版本**

```bash
cat > benchmarks/hooks/dump-agent-payload.sh << 'HOOK_EOF'
#!/bin/bash
# dump-agent-payload.sh
# PostToolUse hook for Agent tool — 采集性能数据 + 归档 review 产物
#
# 职责：
#   1. 每次 Agent 工具调用完成后，从 stdin 提取关键字段，追加到 session JSONL
#   2. 检测到 reviewer Agent 时，重命名 review-output 产物文件加入轮次号
#
# 配置：PostToolUse matcher: "Agent"

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DUMP_DIR="$PROJECT_DIR/benchmarks/dumps"
mkdir -p "$DUMP_DIR"

RAW=$(cat)
NOW=$(date +%s)

# ── 提取 session_id ──
SESSION_ID=$(echo "$RAW" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('session_id', 'unknown'))
" 2>/dev/null)

# ── 构建精简 JSONL 行 ──
RECORD=$(echo "$RAW" | python3 -c "
import sys, json, os

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
last_msg = last_msg[:200] if last_msg else ''

usage = tr.get('usage', {})

rec = {
    'ts': int(__import__('time').time()),
    'session_id': d.get('session_id', ''),
    'tool_use_id': d.get('tool_use_id', ''),
    'description': ti.get('description', ''),
    'subagent_type': ti.get('subagent_type', ''),
    'duration_ms': tr.get('totalDurationMs', 0),
    'total_tokens': tr.get('totalTokens', 0),
    'total_tool_uses': tr.get('totalToolUseCount', 0),
    'usage': usage,
    'last_message_snippet': last_msg,
}

print(json.dumps(rec, ensure_ascii=False))
" 2>/dev/null)

# ── 追加 JSONL ──
DUMP_FILE="$DUMP_DIR/session-${SESSION_ID}.jsonl"
echo "$RECORD" >> "$DUMP_FILE"

# ── reviewer 检测 & 产物重命名 ──
DESC=$(echo "$RECORD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null)

if echo "$DESC" | grep -qiE 'review|审查'; then
    REVIEW_DIR="$PROJECT_DIR/agents/reviewer/check_system/review-output"
    if [ -d "$REVIEW_DIR" ]; then
        # 已有 rN- 文件数量 = 本轮轮次号
        N=$(find "$REVIEW_DIR" -maxdepth 1 -name "r*-pre-check-result.json" 2>/dev/null | wc -l | tr -d ' ')
        for f in pre-check-result.json pre-check-report.md review-result.json; do
            if [ -f "$REVIEW_DIR/$f" ]; then
                mv "$REVIEW_DIR/$f" "$REVIEW_DIR/r${N}-$f"
            fi
        done
    fi
fi

exit 0
HOOK_EOF
```

- [ ] **Step 3: 验证脚本语法**

```bash
bash -n benchmarks/hooks/dump-agent-payload.sh
echo "Syntax OK"
```

Expected: `Syntax OK`

- [ ] **Step 4: 模拟测试 reviewer 重命名逻辑**

```bash
# 创建临时测试目录
TEST_DIR=$(mktemp -d)
mkdir -p "$TEST_DIR/review-output"
touch "$TEST_DIR/review-output/pre-check-result.json"
touch "$TEST_DIR/review-output/pre-check-report.md"
touch "$TEST_DIR/review-output/review-result.json"

# 模拟已有 r0 文件
touch "$TEST_DIR/review-output/r0-pre-check-result.json"

# 验证：N 应该 = 1（已有 1 个 rN 文件）
N=$(find "$TEST_DIR/review-output" -maxdepth 1 -name "r*-pre-check-result.json" | wc -l | tr -d ' ')
echo "N=$N (expected: 1)"

# 模拟重命名
for f in pre-check-result.json pre-check-report.md review-result.json; do
    if [ -f "$TEST_DIR/review-output/$f" ]; then
        mv "$TEST_DIR/review-output/$f" "$TEST_DIR/review-output/r${N}-$f"
    fi
done

# 验证产物已重命名
ls -la "$TEST_DIR/review-output/"
# Expected: r0-pre-check-result.json, r1-pre-check-result.json, r1-pre-check-report.md, r1-review-result.json

rm -rf "$TEST_DIR"
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/hooks/dump-agent-payload.sh
git commit -m "feat: add reviewer detection and artifact renaming to PostToolUse hook"
```

---

### Task 3: 创建 Stop hook — 合成脚本

**Files:**
- Create: `benchmarks/hooks/synthesize-benchmark.sh`

- [ ] **Step 1: 写入 Stop hook 脚本**

```bash
cat > benchmarks/hooks/synthesize-benchmark.sh << 'STOP_EOF'
#!/bin/bash
# synthesize-benchmark.sh
# Stop hook —— 流水线结束时合成性能日志
#
# 从 session dump JSONL + review-output/r*- 产物合成完整 benchmark JSON + MD
# 如果 session dump 为空（没跑流水线），静默退出不做任何事。

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DUMP_DIR="$PROJECT_DIR/benchmarks/dumps"

# ── 从 stdin 读 Stop hook payload，获取 session_id ──
RAW=$(cat 2>/dev/null || echo "{}")
SESSION_ID=$(echo "$RAW" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('session_id', ''))
" 2>/dev/null || echo "")

# 如果 stdin 没给 session_id，从最新的 dump 文件推断
if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(ls -t "$DUMP_DIR"/session-*.jsonl 2>/dev/null | head -1 | sed 's/.*session-//' | sed 's/\.jsonl//' || echo "")
fi

if [ -z "$SESSION_ID" ]; then
    exit 0
fi

JSONL_PATH="$DUMP_DIR/session-${SESSION_ID}.jsonl"

if [ ! -f "$JSONL_PATH" ]; then
    exit 0
fi

# ── 配置 ──
REVIEW_DIR="$PROJECT_DIR/agents/reviewer/check_system/review-output"
MAX_RETRIES=3

# ── 尝试从 pipeline.yaml 读取配置 ──
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

# ── 调用合成引擎 ──
REQUIREMENT=""
SCHEMA_SCRIPT="$PROJECT_DIR/benchmarks/hooks/schema.py"

if [ ! -f "$SCHEMA_SCRIPT" ]; then
    echo "[benchmark] schema.py not found, skipping" >&2
    exit 0
fi

python3 "$SCHEMA_SCRIPT" \
    "$SESSION_ID" \
    "$JSONL_PATH" \
    "$REVIEW_DIR" \
    "$PROJECT_DIR" \
    "$REQUIREMENT" \
    "$MAX_RETRIES"

exit 0
STOP_EOF
```

- [ ] **Step 2: 验证脚本语法**

```bash
bash -n benchmarks/hooks/synthesize-benchmark.sh
echo "Syntax OK"
```

Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add benchmarks/hooks/synthesize-benchmark.sh
git commit -m "feat: add Stop hook to synthesize benchmark reports"
```

---

### Task 4: 更新配置文件

**Files:**
- Modify: `.claude/settings.json`
- Modify: `.gitignore`

- [ ] **Step 1: 更新 `.claude/settings.json` — 更新路径 + 添加 Stop hook**

当前配置（已有 PreToolUse 做 agents/ 写入隔离）：
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
            "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/dump-agent-payload.sh"
          }
        ]
      }
    ]
  }
}
```

替换为路径更新 + Stop hook 后的版本：

```bash
cat > .claude/settings.json << 'SETTINGS_EOF'
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
            "command": "bash ${CLAUDE_PROJECT_DIR}/benchmarks/hooks/synthesize-benchmark.sh"
          }
        ]
      }
    ]
  }
}
SETTINGS_EOF
```

- [ ] **Step 2: 验证 JSON 格式**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3: 更新或创建 `.gitignore`**

```bash
# 检查 .gitignore 是否存在
if [ ! -f .gitignore ]; then
    touch .gitignore
fi

# 添加排除规则（如果不存在）
for pattern in "benchmarks/dumps/" "benchmarks/run-*"; do
    if ! grep -q "^${pattern}$" .gitignore 2>/dev/null; then
        echo "$pattern" >> .gitignore
        echo "Added to .gitignore: $pattern"
    else
        echo "Already in .gitignore: $pattern"
    fi
done
```

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json .gitignore
git commit -m "feat: add Stop hook config and gitignore benchmark artifacts"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 用一个小 Agent 调用来验证 PostToolUse hook 仍然正常**

```bash
# 通过启动一个小型 Agent 调用来触发 PostToolUse hook
# （在对话中通过 Agent 工具完成）
```

验证 hook 仍写 JSONL：
```bash
ls -la benchmarks/dumps/
cat benchmarks/dumps/session-*.jsonl | tail -1 | python3 -m json.tool
```

Expected: JSONL 包含 `description`, `duration_ms`, `total_tokens`, `usage` 等字段

- [ ] **Step 2: 触发一个 reviewer 类 Agent（description 含 "review"）来测试重命名**

验证产物文件被重命名：
```bash
ls agents/reviewer/check_system/review-output/r*-pre-check-result.json
```

Expected: 看到 `r0-pre-check-result.json`, `r1-pre-check-result.json` 等文件

- [ ] **Step 3: 手动触发 Stop hook 合成**

```bash
SESSION_ID=$(basename $(ls -t benchmarks/dumps/session-*.jsonl | head -1) .jsonl | sed 's/session-//')
python3 benchmarks/hooks/schema.py \
  "$SESSION_ID" \
  "benchmarks/dumps/session-${SESSION_ID}.jsonl" \
  "agents/reviewer/check_system/review-output" \
  "." \
  "实现一个登录注册功能" \
  3
```

Expected: 生成 `benchmarks/run-*-login-register.json` 和 `benchmarks/run-*-login-register.md`

- [ ] **Step 4: 验证 JSON 完整性**

```bash
python3 << 'PYEOF'
import json, sys

with open(f"benchmarks/{sorted(__import__('os').listdir('benchmarks'))[-1]}") as f:
    d = json.load(f)

errors = []

# meta
m = d["meta"]
for key in ["run_id", "timestamp_start", "timestamp_end", "requirement_slug", "config"]:
    if key not in m:
        errors.append(f"meta missing: {key}")

# agents
for role in ["coder", "reviewer"]:
    a = d["agents"][role]
    for key in ["fingerprint", "fingerprint_full", "source_file_count"]:
        if key not in a:
            errors.append(f"agents.{role} missing: {key}")

# rounds
for r in d["rounds"]:
    if r["coder"] is None and r["reviewer"] is None:
        errors.append(f"round {r['round']} has no data")

# convergence
c = d["convergence"]
for key in ["rounds_to_converge", "termination_reason", "series"]:
    if key not in c:
        errors.append(f"convergence missing: {key}")

# summary
s = d["summary"]
for key in ["total_duration_ms", "total_tokens", "coder", "reviewer", "cache_efficiency", "converged"]:
    if key not in s:
        errors.append(f"summary missing: {key}")

if errors:
    for e in errors:
        print(f"FAIL: {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
PYEOF
```

Expected: `ALL CHECKS PASSED`

- [ ] **Step 5: Commit**

```bash
git add benchmarks/
git commit -m "test: add first benchmark output from dry-run"
```
