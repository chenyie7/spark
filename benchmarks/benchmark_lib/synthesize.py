"""合成引擎。

合并 dumps/{run_id}.jsonl（性能数据）和 {run_id}/pipeline-log.jsonl（结构数据），
生成符合 schema 2.0 的 benchmark.json。
"""

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from benchmark_lib.config import load_config, resolve_path
from benchmark_lib.models import get_timestamp_cst

CST = timezone(timedelta(hours=8))


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
            phase = "generate" if round_num == 0 else "fix"

            # 检查是否已有该 round 的条目（reviewer 可能先被处理）
            existing = None
            for rnd in rounds:
                if rnd["round"] == round_num:
                    existing = rnd
                    break

            if existing is not None:
                existing["coder"] = {
                    "phase": phase,
                    "duration_ms": dump.get("duration_ms", 0),
                    "total_tokens": dump.get("total_tokens", 0),
                    "total_tool_uses": dump.get("total_tool_uses", 0),
                    "usage": dump.get("usage", {}),
                }
            else:
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

            # 找到当前 round 的条目并附加 reviewer
            existing = None
            for rnd in rounds:
                if rnd["round"] == round_num:
                    existing = rnd
                    break

            if existing is not None:
                existing["reviewer"] = {
                    "phase": "review",
                    "duration_ms": dump.get("duration_ms", 0),
                    "total_tokens": dump.get("total_tokens", 0),
                    "total_tool_uses": dump.get("total_tool_uses", 0),
                    "usage": dump.get("usage", {}),
                    "result": verdict,
                    "issues": {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1},
                }
            else:
                rounds.append({
                    "round": round_num,
                    "coder": None,
                    "reviewer": {
                        "phase": "review",
                        "duration_ms": dump.get("duration_ms", 0),
                        "total_tokens": dump.get("total_tokens", 0),
                        "total_tool_uses": dump.get("total_tool_uses", 0),
                        "usage": dump.get("usage", {}),
                        "result": verdict,
                        "issues": {"P0": 0, "P1": 0, "P2": 0, "AI_FAIL": -1},
                    },
                })

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
