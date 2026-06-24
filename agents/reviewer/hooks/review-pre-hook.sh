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
CONFIG_FILE="$CHECK_SYSTEM_DIR/code-check-config.yaml"

# ─────────────────────────────────────────────────────────────
# 从 YAML 配置读取默认扫描路径；命令行参数优先
CONFIG_PATH=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('default_scan_path', 'src/main/java'))
except Exception:
    print('src/main/java')
" "$CONFIG_FILE" 2>/dev/null)

TARGET_PATH="${1:-${REVIEW_TARGET_PATH:-$CONFIG_PATH}}"

echo "============================================"
echo " Pre-hook: 程序预检"
echo " Target: $TARGET_PATH"
echo "============================================"

cd "$CHECK_SYSTEM_DIR"

# Resolve target path relative to PROJECT_DIR (the script changes to CHECK_SYSTEM_DIR,
# but TARGET_PATH is relative to the project root)
TARGET_ABS="$PROJECT_DIR/$TARGET_PATH"
python3 -m code_check.cli scan "$TARGET_ABS"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "============================================"
    echo " Pre-hook: 阻断"
    echo " 程序预检未通过，请修复后再继续。"
    OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CHECK_SYSTEM_DIR/code-check-config.yaml" 2>/dev/null || echo "../../../review-output")
    echo " 详细报告: $CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL/pre-check-report.md"
    echo "============================================"
    exit 1
fi

echo ""
echo "============================================"
echo " Pre-hook: 通过"
echo "============================================"
exit 0
