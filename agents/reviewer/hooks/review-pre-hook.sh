#!/bin/bash
# Pre-hook: 程序预检 — 在 Review Step 2 之前执行
# 用法: bash agents/reviewer/hooks/review-pre-hook.sh <target-path>
# 行为: 扫描代码 → 有阻断级问题则 exit 1，通过则 exit 0
#
# 路径配置: 第一个参数指定要扫描的 Java 代码目录，相对于项目根目录
#           默认值见下方 DEFAULT_TARGET

set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 路径解析
# hooks/ → reviewer/ → agents/ → project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"

# ─────────────────────────────────────────────────────────────
TARGET_PATH="${1:-${REVIEW_TARGET_PATH:-src/main/java}}"

echo "============================================"
echo " Pre-hook: 程序预检"
echo " Target: $TARGET_PATH"
echo "============================================"

TARGET_ABS="$PROJECT_DIR/$TARGET_PATH"

if [ ! -d "$TARGET_ABS" ]; then
    echo ""
    echo "============================================"
    echo " Pre-hook: 阻断"
    echo " 目标路径不存在: $TARGET_ABS"
    echo "============================================"
    exit 1
fi

JAVA_COUNT=$(find "$TARGET_ABS" -name "*.java" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$JAVA_COUNT" -eq 0 ]; then
    echo ""
    echo "============================================"
    echo " Pre-hook: 阻断"
    echo " 未找到 Java 文件: $TARGET_ABS"
    echo "============================================"
    exit 1
fi

echo "Java 文件数: $JAVA_COUNT"
echo ""
echo "静态代码扫描已由 reviewer Agent 中的 fuck-u-code MCP 工具处理，"
echo "此预检仅验证目标路径和 Java 文件存在性。"
echo ""
echo "============================================"
echo " Pre-hook: 通过"
echo "============================================"
exit 0
