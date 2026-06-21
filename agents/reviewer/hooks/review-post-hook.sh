#!/bin/bash
# Post-hook: 报告合并 — 在 AI 检查完成后执行
# 用法: bash agents/reviewer/hooks/review-post-hook.sh [pre-json] [ai-json] [output-md]
# 行为: 合并 pre-check-result.json + review-result.json → final-review-report.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# hooks/ → reviewer/ → agents/ → project root
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

PRE_CHECK_JSON="${1:-$PROJECT_DIR/review-output/pre-check-result.json}"
AI_CHECK_JSON="${2:-$PROJECT_DIR/review-output/review-result.json}"
OUTPUT_MD="${3:-$PROJECT_DIR/review-output/final-review-report.md}"

CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"

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
