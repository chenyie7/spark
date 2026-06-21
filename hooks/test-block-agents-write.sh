#!/bin/bash
# Test suite for block-agents-write.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_SCRIPT="$SCRIPT_DIR/block-agents-write.sh"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0

run_test() {
    local desc="$1"
    local path="$2"
    local expected_exit="$3"

    # Temporarily disable set -e so a rejection (exit 1) doesn't kill the test
    set +e
    CLAUDE_PROJECT_DIR="$PROJECT_ROOT" \
    CLAUDE_TOOL_INPUT="{\"file_path\":\"$path\"}" \
        bash "$HOOK_SCRIPT" 2>/dev/null
    local actual=$?
    set -e
    if [ "$actual" = "$expected_exit" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (expected exit=$expected_exit, got exit=$actual)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Testing block-agents-write.sh ==="
echo ""

echo "Rejection tests:"
run_test "agents/coder/README.md" "agents/coder/README.md" 1
run_test "agents/reviewer/scanner.py" "agents/reviewer/check_system/code_check/scanner.py" 1
run_test "agents/scheduler/pipeline.yaml" "agents/scheduler/pipeline.yaml" 1
run_test "./agents/foo/bar.java" "./agents/foo/bar.java" 1
run_test "../project-name/agents/foo" "../workflow-agent-demo/agents/foo" 1
run_test "dot-dot-slash bypass" "src/main/java/../../../agents/coder/SKILL.md" 1
run_test "symlink bypass inside project" "hooks/../agents/reviewer/README.md" 1

echo ""
echo "Allow tests:"
run_test "src/main/java" "src/main/java/com/example/Controller.java" 0
run_test "review-output at root" "review-output/pre-check-result.json" 0
run_test "pom.xml" "pom.xml" 0
run_test "empty file_path" "" 0
run_test "malformed JSON" "not-json" 0
# With realpath resolution, ../agents/ resolves OUTSIDE the project root
# (to <parent>/agents/), so it points to a different agents/ directory
# and is correctly not blocked. Only paths inside THIS project's agents/ are blocked.
run_test "../agents/ resolves outside project" "../agents/bypass" 0
run_test "absolute path inside src" "$PROJECT_ROOT/src/main/java/Foo.java" 0

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
