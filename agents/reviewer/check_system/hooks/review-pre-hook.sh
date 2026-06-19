#!/bin/bash
# Pre-hook: 程序预检 — 在 Review Agent 启动前执行
# 用法: 由 Claude Code /review 命令的 Pre-hook 触发
# 行为: 扫描代码 → 有阻断级问题则 exit 1（阻止 Review Agent），通过则 exit 0

set -euo pipefail

TARGET_PATH="${1:-../../../src/main/java}"
CONFIG_PATH="${2:-code-check-config.yaml}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK_SYSTEM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$CHECK_SYSTEM_DIR"

echo "============================================"
echo " Pre-hook: 程序预检"
echo " Target: $TARGET_PATH"
echo " Config: $CONFIG_PATH"
echo "============================================"

python3 -m code_check.cli scan "$TARGET_PATH" --config "$CONFIG_PATH"

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "============================================"
    echo " Pre-hook: 阻断"
    echo " 程序预检未通过，Review Agent 将不会启动。"
    echo " 请查看 review-output/pre-check-report.md 了解详情。"
    echo "============================================"
    exit 1
fi

echo ""
echo "============================================"
echo " Pre-hook: 通过"
echo " 程序预检通过，继续执行 Review Agent..."
echo "============================================"
exit 0
