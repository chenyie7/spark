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
        # 跳过开发子 Agent（subagent-driven-development 的任务 Agent）
        if rec.get("is_dev_agent"):
            continue

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

def _compute_summary(rounds: list[dict], convergence: dict, records: list[dict] | None = None) -> dict:
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

    # 模型使用统计
    models_used = {}
    if records:
        for rec in records:
            if rec.get("is_dev_agent"):
                continue  # 只统计 pipeline agent 的模型
            model = rec.get("model", "")
            if model:
                models_used[model] = models_used.get(model, 0) + 1

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
        "marginal_fix_cost": marginal_fix_cost,
        "review_overhead_pct": review_overhead_pct,
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

            # 判定收敛：P0 = 0 且 result = REVIEW_PASSED
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


# ── 修复效率 ──

def _compute_fix_efficiency(rounds: list[dict]) -> dict:
    """计算修复效率指标。

    Returns:
        {
            "tokens_per_p0_fixed": float | None,
            "p0_reduction_rate_pct": float | None,
            "new_issues_per_fix_round": list[int],
        }
    """
    fix_rounds = []
    p0_series = []

    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            issues = rv.get("issues", {})
            p0 = issues.get("P0", 0)
            p0_series.append(p0)

        coder = r.get("coder")
        if coder is not None and coder.get("phase") == "fix":
            fix_rounds.append(r)

    # tokens per P0 fixed
    tokens_per_p0 = None
    if len(p0_series) >= 2:
        total_fix_tokens = sum(
            r["coder"]["total_tokens"] for r in fix_rounds
            if r.get("coder") is not None
        )
        p0_fixed = p0_series[0] - p0_series[-1]
        if p0_fixed > 0:
            tokens_per_p0 = round(total_fix_tokens / p0_fixed)

    # P0 reduction rate per round
    reduction_rate = None
    if len(p0_series) >= 2 and p0_series[0] > 0:
        reduction_rate = round((p0_series[0] - p0_series[-1]) / p0_series[0] * 100, 1)

    # New issues introduced (P1/P2 increase during fix rounds)
    new_issues_per_fix = []
    prev_total = None
    for r in rounds:
        rv = r.get("reviewer")
        if rv is not None:
            issues = rv.get("issues", {})
            current_total = issues.get("P1", 0) + issues.get("P2", 0)
            if prev_total is not None and current_total > prev_total:
                new_issues_per_fix.append(current_total - prev_total)
            else:
                new_issues_per_fix.append(0)
            prev_total = current_total

    return {
        "tokens_per_p0_fixed": tokens_per_p0,
        "p0_reduction_rate_pct": reduction_rate,
        "new_issues_per_fix_round": new_issues_per_fix,
    }


# ── 阶段拆解 ──

def _compute_phase_breakdown(rounds: list[dict]) -> dict:
    """按阶段拆解 tokens 和时间。

    Returns:
        { "generate": {...}, "fix": {...}, "review": {...} }
    """
    breakdown = {}
    for phase_name in ("generate", "fix", "review"):
        breakdown[phase_name] = {
            "calls": 0,
            "total_tokens": 0,
            "total_duration_ms": 0,
        }

    for r in rounds:
        for role_key in ("coder", "reviewer"):
            entry = r.get(role_key)
            if entry is None:
                continue
            phase = entry.get("phase", "")
            if phase in breakdown:
                breakdown[phase]["calls"] += 1
                breakdown[phase]["total_tokens"] += entry.get("total_tokens", 0)
                breakdown[phase]["total_duration_ms"] += entry.get("duration_ms", 0)

    # 去掉 0 调用的阶段
    return {k: v for k, v in breakdown.items() if v["calls"] > 0}


def _localize_issues(review_dir: str, rounds: list[dict]) -> dict:
    """按文件和规则类别统计问题分布。

    从每轮 reviewer 的 pre-check-result.json 和 review-result.json
    中提取问题，按文件和类别聚合。
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


def _assess_fix_quality(rounds: list[dict], review_dir: str) -> dict:
    """评估修复质量：反复问题、副作用、有效率。"""
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


# ── 需求 slug ──

def _slugify(text: str, max_len: int = 30) -> str:
    """将中文需求文本转为短 slug。"""
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

    # 5b. 修复效率
    fix_efficiency = _compute_fix_efficiency(rounds)

    # 5c. 阶段拆解
    phase_breakdown = _compute_phase_breakdown(rounds)

    # 5d. 问题定位
    problem_localization = _localize_issues(review_dir, rounds)

    # 5e. 修复质量
    fix_quality = _assess_fix_quality(rounds, review_dir)

    # 6. 汇总
    summary = _compute_summary(rounds, convergence, records)

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
        "fix_efficiency": fix_efficiency,
        "phase_breakdown": phase_breakdown,
        "problem_localization": problem_localization,
        "fix_quality": fix_quality,
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

    # 阶段拆解
    if data.get("phase_breakdown"):
        lines.append("## 阶段拆解")
        lines.append("")
        lines.append("| 阶段 | 调用次数 | Tokens | 耗时(s) |")
        lines.append("|------|---------|--------|---------|")
        pb = data["phase_breakdown"]
        for phase_name in ("generate", "fix", "review"):
            if phase_name in pb:
                p = pb[phase_name]
                lines.append(
                    f"| {phase_name} | {p['calls']} | {p['total_tokens']:,} "
                    f"| {p['total_duration_ms'] / 1000:.0f} |"
                )
        lines.append("")

    # 问题分布
    pl = data.get("problem_localization", {})
    if pl:
        lines.append("## 问题分布")
        lines.append("")

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

    # 边际修复成本
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

    ce = summary["cache_efficiency"]
    lines.append(f"- **缓存命中率**: {ce['cache_hit_ratio'] * 100:.1f}%  "
                 f"(cache_read={ce['total_cache_read_tokens']:,}, input={ce['total_input_tokens']:,})")
    lines.append(f"- **审查开销占比**: {summary['review_overhead_pct']}%")

    # 修复效率
    fe = data.get("fix_efficiency", {})
    if fe.get("tokens_per_p0_fixed") is not None:
        lines.append(f"- **每修复一个 P0 消耗 Token**: {fe['tokens_per_p0_fixed']:,}")
    if fe.get("p0_reduction_rate_pct") is not None:
        lines.append(f"- **P0 减少率**: {fe['p0_reduction_rate_pct']}%")

    lines.append(f"- **是否收敛**: {'✅' if summary['converged'] else '❌'}")

    # 模型信息
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


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 schema.py <session_id> <jsonl_path> [review_dir] [project_dir] [requirement] [max_retries]", file=sys.stderr)
        sys.exit(1)

    sid = sys.argv[1]
    jpath = sys.argv[2]
    rdir = sys.argv[3] if len(sys.argv) > 3 else "review-output"
    pdir = sys.argv[4] if len(sys.argv) > 4 else os.getcwd()
    req = sys.argv[5] if len(sys.argv) > 5 else ""
    mr = int(sys.argv[6]) if len(sys.argv) > 6 else 3
    bs = sys.argv[7] if len(sys.argv) > 7 else "strict"

    data = from_jsonl(sid, jpath, rdir, pdir, req, mr, bs)
    if data is None:
        print("No data to synthesize (empty JSONL).", file=sys.stderr)
        sys.exit(0)

    # 输出目录: benchmarks/runs/{run_id}/
    benchmarks_dir = os.path.join(pdir, "benchmarks", "runs", run_id)
    os.makedirs(benchmarks_dir, exist_ok=True)

    json_path = os.path.join(benchmarks_dir, "benchmark.json")
    md_path = os.path.join(benchmarks_dir, "report.md")

    with open(json_path, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    with open(md_path, "w") as fh:
        fh.write(render_md(data))

    print(f"Benchmark saved: {json_path}", file=sys.stderr)
    print(f"Report saved:   {md_path}", file=sys.stderr)
