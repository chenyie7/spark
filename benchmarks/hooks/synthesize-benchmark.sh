#!/bin/bash
# synthesize-benchmark.sh
# Stop hook —— 流水线结束时合成性能日志
#
# 从 session dump JSONL + review-output/r*- 产物合成完整 benchmark JSON + MD
# 如果 session dump 为空（没跑流水线），静默退出不做任何事。
#
# Stop hook 在每次 Claude 响应结束时触发。
# 通过 stop_hook_active 标志防止无限循环。

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
DUMP_DIR="$PROJECT_DIR/benchmarks/dumps"

# ── 从 stdin 读 Stop hook payload ──
RAW=$(cat 2>/dev/null || echo "{}")

# 防止无限循环：如果已经是 stop hook 触发的对话，直接退出
STOP_ACTIVE=$(echo "$RAW" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('stop_hook_active', 'false'))
" 2>/dev/null || echo "false")

if [ "$STOP_ACTIVE" = "true" ]; then
    exit 0
fi

# 获取 session_id
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
BLOCK_STRATEGY="strict"

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

# ── 尝试从 code-check-config.yaml 读取 strategy ──
CONFIG_YAML="$PROJECT_DIR/agents/reviewer/check_system/code-check-config.yaml"
if [ -f "$CONFIG_YAML" ]; then
    BLOCK_STRATEGY=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('strategy', 'strict'))
except Exception:
    print('strict')
" "$CONFIG_YAML" 2>/dev/null || echo "strict")
fi

# ── 调用合成引擎 ──
SCHEMA_SCRIPT="$PROJECT_DIR/benchmarks/hooks/schema.py"

if [ ! -f "$SCHEMA_SCRIPT" ]; then
    exit 0
fi

python3 "$SCHEMA_SCRIPT" \
    "$SESSION_ID" \
    "$JSONL_PATH" \
    "$REVIEW_DIR" \
    "$PROJECT_DIR" \
    "" \
    "$MAX_RETRIES" \
    "$BLOCK_STRATEGY"

exit 0
