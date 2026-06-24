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

# ── 提取 session_id ──
SESSION_ID=$(echo "$RAW" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('session_id', 'unknown'))
" 2>/dev/null)

# ── 构建精简 JSONL 行 ──
RECORD=$(echo "$RAW" | python3 -c "
import sys, json, time

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

usage = tr.get('usage', {})

# extract model info
model = usage.get('model', '') or ''

# detect verdict from last_msg
verdict = ''
if 'REVIEW_PASSED' in last_msg:
    verdict = 'REVIEW_PASSED'
elif 'REVIEW_FAILED' in last_msg:
    verdict = 'REVIEW_FAILED'
elif 'REVIEW_ERROR' in last_msg:
    verdict = 'REVIEW_ERROR'

# detect error/failure signals
has_error = 'error' in last_msg[:200].lower() or 'failed' in last_msg[:200].lower() or 'Traceback' in last_msg

# distinguish pipeline Agent vs dev sub-agent
desc = ti.get('description', '')
is_dev_agent = (
    'Task' in desc and (
        'Implement' in desc or
        'review Task' in desc.lower() or
        'Spec review' in desc or
        'Code quality review' in desc or
        'Fix Task' in desc
    )
)

last_msg_snippet = last_msg[:500] if last_msg else ''

rec = {
    'ts': int(time.time()),
    'session_id': d.get('session_id', ''),
    'tool_use_id': d.get('tool_use_id', ''),
    'description': ti.get('description', ''),
    'subagent_type': ti.get('subagent_type', ''),
    'duration_ms': tr.get('totalDurationMs', 0),
    'total_tokens': tr.get('totalTokens', 0),
    'total_tool_uses': tr.get('totalToolUseCount', 0),
    'usage': usage,
    'last_message_snippet': last_msg_snippet,
    # new fields
    'model': model,
    'verdict': verdict,
    'has_error': has_error,
    'is_dev_agent': is_dev_agent,
}

print(json.dumps(rec, ensure_ascii=False))
" 2>/dev/null)

# ── 追加 JSONL ──
DUMP_FILE="$DUMP_DIR/session-${SESSION_ID}.jsonl"
echo "$RECORD" >> "$DUMP_FILE"

# ── reviewer 检测 & 产物重命名 ──
DESC=$(echo "$RECORD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null)

if echo "$DESC" | grep -qiE 'review|审查'; then
    # 从 code-check-config.yaml 读取 output_dir，定位 reviewer 产物
    CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"
    CONFIG_YAML="$CHECK_SYSTEM_DIR/code-check-config.yaml"

    if [ -f "$CONFIG_YAML" ]; then
        OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CONFIG_YAML" 2>/dev/null)
        REVIEW_DIR="$(cd "$CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL" 2>/dev/null && pwd || echo "$PROJECT_DIR/review-output")"
    else
        REVIEW_DIR="$PROJECT_DIR/review-output"
    fi

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
