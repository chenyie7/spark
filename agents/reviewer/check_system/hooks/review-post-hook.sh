#!/bin/bash
# Post-hook: 报告合并生成 — 在 Review Agent 完成后执行
# 用法: 由 Claude Code /review 命令的 Post-hook 触发
# 行为: 合并 pre-check-result.json + review-result.json → final-review-report.md

set -euo pipefail

PRE_CHECK_JSON="${1:-./review-output/pre-check-result.json}"
AI_CHECK_JSON="${2:-./review-output/review-result.json}"
OUTPUT_MD="${3:-./review-output/final-review-report.md}"
CONFIG_PATH="${4:-code-check-config.yaml}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK_SYSTEM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$CHECK_SYSTEM_DIR"

echo "============================================"
echo " Post-hook: 报告合并生成"
echo " Pre-check: $PRE_CHECK_JSON"
echo " AI check:  $AI_CHECK_JSON"
echo " Output:    $OUTPUT_MD"
echo "============================================"

if [ ! -f "$PRE_CHECK_JSON" ]; then
    echo "Error: Pre-check result not found: $PRE_CHECK_JSON"
    exit 1
fi

CMD="python3 -m code_check.cli report --pre $PRE_CHECK_JSON --output $OUTPUT_MD --config $CONFIG_PATH"

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
