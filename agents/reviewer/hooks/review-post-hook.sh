#!/bin/bash
# Post-hook: 报告合并 — 在 AI 检查完成后执行
# 用法: bash agents/reviewer/hooks/review-post-hook.sh [pre-json] [ai-json] [output-md]
# 行为: 合并 pre-check-result.json + review-result.json → final-review-report.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# hooks/ → reviewer/ → agents/ → project root
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"

# 从 code-check-config.yaml 读取 output_dir（相对于 check_system 目录）
OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CHECK_SYSTEM_DIR/code-check-config.yaml")

# 解析为绝对路径
OUTPUT_DIR_ABS="$(cd "$CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL" 2>/dev/null && pwd || echo "$PROJECT_DIR/review-output")"

PRE_CHECK_JSON="${1:-$OUTPUT_DIR_ABS/pre-check-result.json}"
AI_CHECK_JSON="${2:-$OUTPUT_DIR_ABS/review-result.json}"
OUTPUT_MD="${3:-$OUTPUT_DIR_ABS/final-review-report.md}"

cd "$CHECK_SYSTEM_DIR"

echo "============================================"
echo " Post-hook: 报告合并"
echo " Pre-check: $PRE_CHECK_JSON"
echo " AI check:  $AI_CHECK_JSON"
echo " Output:    $OUTPUT_MD"
echo "============================================"

if [ ! -f "$PRE_CHECK_JSON" ]; then
    echo "Error: Pre-check result not found: $PRE_CHECK_JSON"
    exit 1
fi

CMD="python3 -m code_check.cli report --pre $PRE_CHECK_JSON --output $OUTPUT_MD"

if [ -f "$AI_CHECK_JSON" ]; then
    CMD="$CMD --ai $AI_CHECK_JSON"
    echo "AI check result found, including in report."
else
    echo "AI check result not found, generating report without AI section."
fi

$CMD

echo ""
echo "============================================"
echo " Post-hook: 完成"
echo " 最终报告: $OUTPUT_MD"
echo "============================================"
