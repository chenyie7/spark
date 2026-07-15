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
