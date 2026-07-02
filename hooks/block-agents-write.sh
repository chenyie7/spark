#!/bin/bash
# block-agents-write.sh
# PreToolUse hook — 拦截对 agents/ 目录的 Write/Edit 工具调用
# 被拦截时返回非零退出码，Claude Code 会拒绝该操作

set -euo pipefail

# 仅在流水线运行时生效，非流水线场景静默跳过
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi

# 从 CLAUDE_TOOL_INPUT 环境变量获取 file_path，并解析为规范绝对路径
RESOLVED=$(printf '%s' "${CLAUDE_TOOL_INPUT:-}" | python3 -c "
import os, sys, json
try:
    d = json.load(sys.stdin)
    fp = d.get('file_path', '') or d.get('path', '')
    if fp:
        root = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
        abs_path = os.path.join(root, fp)
        canonical = os.path.realpath(abs_path)
        print(canonical)
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$RESOLVED" ]; then
    # 无法解析 file_path，放行（不做误杀）
    exit 0
fi

# 白名单: 允许写入特定 agent 目录（新增 agent 的安装和维护）
PM_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/agents/pm/"
case "$RESOLVED" in
    "$PM_DIR"*)
        exit 0
        ;;
esac

# 检查是否落在 agents/ 目录内（与规范绝对路径比较，防止 ../ 绕过）
AGENTS_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/agents/"
case "$RESOLVED" in
    "$AGENTS_DIR"*)
        cat >&2 <<EOF
╔══════════════════════════════════════════════════════════╗
║  🚫 写入被拒绝：禁止修改 agents/ 目录                      ║
║                                                          ║
║  路径: $RESOLVED
║                                                          ║
║  coder Agent 只能修改:                                    ║
║    - src/main/java/ 下的 Java 代码                       ║
║    - 项目根目录的 pom.xml（如需添加依赖）                   ║
║                                                          ║
║  agents/ 目录包含审查系统的规则和配置，                      ║
║  修改它们会导致流水线结果不可信。                            ║
║                                                          ║
║  如果审查规则确实有问题，请告知用户手动修复。                  ║
╚══════════════════════════════════════════════════════════╝
EOF
        exit 1
        ;;
    *)
        exit 0
        ;;
esac
