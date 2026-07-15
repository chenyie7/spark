"""数据模型与 JSON Schema 定义。

定义 benchmark.json 的完整 JSON Schema (draft-07)，
以及辅助的数据结构 dataclass。
"""

import json
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
