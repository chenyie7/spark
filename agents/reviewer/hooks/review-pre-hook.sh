#!/bin/bash
# Pre-hook: 程序预检 — 在 Review Step 2 之前执行
# 用法: bash agents/reviewer/hooks/review-pre-hook.sh <target-path>
# 行为: 扫描代码 → 有阻断级问题则 exit 1，通过则 exit 0
#
# 路径配置: 第一个参数指定要扫描的 Java 代码目录，相对于项目根目录
#           默认值见下方 DEFAULT_TARGET

set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# 可配置项
# ═══════════════════════════════════════════════════════════════

DEFAULT_TARGET="${REVIEW_TARGET_PATH:-src/main/java}"
TARGET_PATH="${1:-$DEFAULT_TARGET}"

# ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# hooks/ → reviewer/ → agents/ → project root
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"

echo "============================================"
echo " Pre-hook: 程序预检"
echo " Target: $TARGET_PATH"
echo "============================================"

cd "$CHECK_SYSTEM_DIR"

python3 -m code_check.cli scan "$TARGET_PATH"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "============================================"
    echo " Pre-hook: 阻断"
    echo " 程序预检未通过，请修复后再继续。"
    echo " 详细报告: $CHECK_SYSTEM_DIR/review-output/pre-check-report.md"
    echo "============================================"
    exit 1
fi

echo ""
echo "============================================"
echo " Pre-hook: 通过"
echo "============================================"
exit 0
