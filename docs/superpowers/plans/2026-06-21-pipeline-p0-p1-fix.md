# 流水线 P0/P1 缺陷修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复首次流水线运行暴露的 3 个缺陷：coder 越权修改 review 文件、review-output 路径混在 agents/ 下、修复轮只修 P0 导致收敛慢。

**Architecture:** Hook（硬约束，拦截 agents/ 写入）+ Prompt（软约束，声明边界）；review-output 迁至项目根目录和 agents/ 平级；修复轮 prompt 改为一次性修复全部阻断级问题。

**Tech Stack:** Bash (hook 脚本), Python CLI (已有不改), YAML (配置)

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `hooks/block-agents-write.sh` | PreToolUse hook 脚本，拦截对 agents/ 的 Write/Edit | **新建** |
| `.claude/settings.json` | 注册 PreToolUse hook | 修改 |
| `agents/reviewer/check_system/code-check-config.yaml` | output_dir 迁到根目录 + strategy 改为 normal | 修改 |
| `agents/reviewer/hooks/review-pre-hook.sh` | 预检 hook，产物路径迁到根目录 | 修改 |
| `agents/reviewer/hooks/review-post-hook.sh` | 合并报告 hook，产物路径迁到根目录 | 修改 |
| `agents/scheduler/pipeline.yaml` | reviewer outputs 路径缩短 + coder prompt 加边界约束 | 修改 |
| `agents/scheduler/build.skill.md` | Phase 3/4 路径缩短 + 修复 prompt 全量修复 + 边界约束 | 修改 |
| `agents/reviewer/review.skill.md` | Step 1/2/3 产物路径更新 | 修改 |
| `.gitignore` | 新增 review-output/ 排除 | 修改 |

---

### Task 1: 创建 Hook 守卫脚本

**Files:**
- Create: `hooks/block-agents-write.sh`

**目标：** 创建 PreToolUse hook 脚本，当 Write/Edit 的目标路径在 `agents/` 下时拒绝操作。

- [ ] **Step 1: 创建脚本文件**

```bash
mkdir -p hooks
```

- [ ] **Step 2: 写入 `hooks/block-agents-write.sh`**

```bash
#!/bin/bash
# block-agents-write.sh
# PreToolUse hook — 拦截对 agents/ 目录的 Write/Edit 工具调用
# 被拦截时返回非零退出码，Claude Code 会拒绝该操作
#
# 通过 CLAUDE_TOOL_INPUT 环境变量获取 tool input JSON，解析 file_path 字段。
# 如果 file_path 以 agents/ 开头则拒绝。

set -euo pipefail

TOOL_NAME="${CLAUDE_TOOL_NAME:-unknown}"

# 从 CLAUDE_TOOL_INPUT 环境变量获取 file_path
FILE_PATH=$(echo "${CLAUDE_TOOL_INPUT:-}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    # file_path 可能在顶层，也可能在嵌套位置
    fp = d.get('file_path', '') or d.get('path', '')
    print(fp)
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
    # 无法解析 file_path，放行（不做误杀）
    exit 0
fi

# 规范化路径（去掉开头的 ./ 或 .. 等）
NORMALIZED=$(echo "$FILE_PATH" | sed 's|^\./||')

# 检查是否以 agents/ 开头
case "$NORMALIZED" in
    agents/*)
        cat >&2 <<EOF
╔══════════════════════════════════════════════════════════╗
║  🚫 写入被拒绝：禁止修改 agents/ 目录                      ║
║                                                          ║
║  路径: $NORMALIZED
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
```

- [ ] **Step 3: 赋予执行权限**

```bash
chmod +x hooks/block-agents-write.sh
```

- [ ] **Step 4: 验证 Bash 语法**

```bash
bash -n hooks/block-agents-write.sh && echo "Bash syntax OK"
```
Expected: `Bash syntax OK`

- [ ] **Step 5: 测试拒绝逻辑**

```bash
# 模拟对 agents/ 路径的 Write 调用
CLAUDE_TOOL_INPUT='{"file_path":"agents/reviewer/check_system/code_check/scanner.py"}' bash hooks/block-agents-write.sh; echo "exit=$?"
```
Expected: 输出包含 "写入被拒绝"，exit=1

- [ ] **Step 6: 测试放行逻辑**

```bash
# 模拟对 src/main/java 路径的 Write 调用
CLAUDE_TOOL_INPUT='{"file_path":"src/main/java/com/example/UserController.java"}' bash hooks/block-agents-write.sh; echo "exit=$?"
```
Expected: exit=0

- [ ] **Step 7: 测试放行 review-output（根目录）**

```bash
CLAUDE_TOOL_INPUT='{"file_path":"review-output/pre-check-result.json"}' bash hooks/block-agents-write.sh; echo "exit=$?"
```
Expected: exit=0（不在 agents/ 下）

- [ ] **Step 8: 测试 pom.xml 放行**

```bash
CLAUDE_TOOL_INPUT='{"file_path":"pom.xml"}' bash hooks/block-agents-write.sh; echo "exit=$?"
```
Expected: exit=0

- [ ] **Step 9: Commit**

```bash
git add hooks/block-agents-write.sh
git commit -m "feat: add PreToolUse hook to block coder writes to agents/ directory

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 注册 PreToolUse hook 到 settings.json

**Files:**
- Modify: `.claude/settings.json`（在已有 PostToolUse 配置前插入 PreToolUse）

- [ ] **Step 1: 更新 `.claude/settings.json`**

将文件内容替换为（在已有 PostToolUse 配置前插入 PreToolUse 段）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PROJECT_DIR}/hooks/block-agents-write.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/dump-agent-payload.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: 验证 JSON 语法**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('JSON OK')"
```
Expected: `JSON OK`

- [ ] **Step 3: 验证 PreToolUse 和 PostToolUse 两个 hook 段都存在**

```bash
python3 -c "
import json
d = json.load(open('.claude/settings.json'))
hooks = d['hooks']
assert 'PreToolUse' in hooks, 'PreToolUse missing!'
assert 'PostToolUse' in hooks, 'PostToolUse missing!'
assert len(hooks['PreToolUse']) > 0, 'PreToolUse empty!'
assert len(hooks['PostToolUse']) > 0, 'PostToolUse empty!'
print('Both hooks present OK')
"
```
Expected: `Both hooks present OK`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: register PreToolUse hook to block agents/ directory writes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 更新 code-check-config.yaml — output_dir + strategy

**Files:**
- Modify: `agents/reviewer/check_system/code-check-config.yaml`（2 处修改：output_dir 路径 + strategy 值）

- [ ] **Step 1: 修改 output_dir 路径**

定位到第 10 行 `output_dir: ./review-output/`，替换为：

```yaml
output_dir: ../../../review-output/
```

原理：`code-check-config.yaml` 在 `check_system/` 目录下，`../../../` 向上三级到项目根目录，`review-output/` 在根目录下。

- [ ] **Step 2: 修改阻断策略**

定位到第 5 行 `strategy: strict`，替换为：

```yaml
strategy: normal
```

- [ ] **Step 3: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('agents/reviewer/check_system/code-check-config.yaml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 4: 验证 output_dir 解析正确**

```bash
cd agents/reviewer/check_system && python3 -c "
import yaml, os
with open('code-check-config.yaml') as f:
    c = yaml.safe_load(f)
output_dir = c['output_dir']
resolved = os.path.normpath(os.path.join(os.path.dirname('code-check-config.yaml'), output_dir))
print(f'Resolved output_dir: {resolved}')
# 应该在项目根目录的 review-output/ 下
assert resolved.startswith('../../'), f'Expected relative path going up, got: {resolved}'
print('Path OK')
"
```
Expected: `Path OK`

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/check_system/code-check-config.yaml
git commit -m "fix: migrate review-output to project root, change block strategy to normal

- output_dir: ./review-output/ → ../../../review-output/
- strategy: strict → normal (P1 no longer blocks, only P0)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 更新 review hook 脚本路径

**Files:**
- Modify: `agents/reviewer/hooks/review-pre-hook.sh:48`（产物输出路径引用）
- Modify: `agents/reviewer/hooks/review-post-hook.sh:8-10,28,45`（默认参数 + 产物检查路径 + 最终报告路径）

- [ ] **Step 1: 修改 `review-pre-hook.sh` 的报告路径引用**

将第 48 行：
```bash
    echo " 详细报告: $CHECK_SYSTEM_DIR/review-output/pre-check-report.md"
```
替换为：
```bash
    echo " 详细报告: $PROJECT_DIR/review-output/pre-check-report.md"
```

- [ ] **Step 2: 修改 `review-post-hook.sh` 的默认参数**

将第 8-10 行：
```bash
PRE_CHECK_JSON="${1:-./review-output/pre-check-result.json}"
AI_CHECK_JSON="${2:-./review-output/review-result.json}"
OUTPUT_MD="${3:-./review-output/final-review-report.md}"
```
替换为：
```bash
PRE_CHECK_JSON="${1:-$PROJECT_DIR/review-output/pre-check-result.json}"
AI_CHECK_JSON="${2:-$PROJECT_DIR/review-output/review-result.json}"
OUTPUT_MD="${3:-$PROJECT_DIR/review-output/final-review-report.md}"
```

注意：`PRE_CHECK_JSON` 不能再在 `$PROJECT_DIR` 定义之前引用它，需要先定义 `$PROJECT_DIR`。当前脚本 `PROJECT_DIR` 定义在第 14 行，在第 8 行之后。需要调整顺序：将 `PROJECT_DIR` 的计算移到默认参数定义之前。

完整修改：
- 将 `SCRIPT_DIR=...` 和 `PROJECT_DIR=...` 定义（第 12-15 行）移到默认参数（第 8-10 行）之前
- 然后更新默认参数中的路径

- [ ] **Step 3: 修改 `review-post-hook.sh` 的文件检查路径**

将第 28 行：
```bash
    echo "Error: Pre-check result not found: $PRE_CHECK_JSON"
```
保持不变（已经通过变量引用）。

将第 45 行：
```bash
    echo " 最终报告: $CHECK_SYSTEM_DIR/$OUTPUT_MD"
```
替换为：
```bash
    echo " 最终报告: $OUTPUT_MD"
```
（因为 `OUTPUT_MD` 现在已经是绝对路径）

并将 `cd "$CHECK_SYSTEM_DIR"`（第 17 行）保持不动——CLI 仍需要在 check_system 目录下执行以找到 code_check 包和配置。

- [ ] **Step 4: 验证 Bash 语法**

```bash
bash -n agents/reviewer/hooks/review-pre-hook.sh && echo "pre-hook Bash OK"
bash -n agents/reviewer/hooks/review-post-hook.sh && echo "post-hook Bash OK"
```
Expected: `pre-hook Bash OK` + `post-hook Bash OK`

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/hooks/review-pre-hook.sh agents/reviewer/hooks/review-post-hook.sh
git commit -m "fix: update review hook scripts to use project-root review-output paths

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 更新 pipeline.yaml — reviewer outputs 路径 + coder 边界约束

**Files:**
- Modify: `agents/scheduler/pipeline.yaml:23-42`（coder prompt_template 加边界声明）
- Modify: `agents/scheduler/pipeline.yaml:68-70`（reviewer outputs 路径缩短）

- [ ] **Step 1: 在 coder prompt_template 末尾加边界约束**

在 `pipeline.yaml` coder 节点的 `prompt_template` 中，在 `{review_context}` 行之后、`将生成的 Java 代码写入 src/main/java 对应包路径下。` 行之前，插入边界声明。

定位到第 39 行 `{review_context}` 和第 41 行 `将生成的 Java 代码写入 src/main/java 对应包路径下。` 之间，插入：

```
      ⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml（如需添加依赖）。禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。

```

注意 YAML 缩进：prompt_template 内容每行有 6 个空格前缀。

- [ ] **Step 2: 缩短 reviewer.outputs 路径**

将 reviewer 节点的 3 个 outputs 路径从 `agents/reviewer/check_system/review-output/` 缩短为 `review-output/`：

```yaml
      - pre_check: "review-output/pre-check-result.json"
      - ai_review: "review-output/review-result.json"
      - final_report: "review-output/final-review-report.md"
```

- [ ] **Step 3: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('agents/scheduler/pipeline.yaml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 4: 验证 coder prompt 中包含边界约束**

```bash
grep "agents/" agents/scheduler/pipeline.yaml | head -3
```
Expected: 输出包含 "禁止修改 agents/" 或类似内容

- [ ] **Step 5: 验证 reviewer outputs 路径不含 agents/ 前缀**

```bash
grep "review-output/" agents/scheduler/pipeline.yaml
```
Expected: 输出路径为 `review-output/...` 而不是 `agents/reviewer/check_system/review-output/...`

- [ ] **Step 6: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "fix: add coder boundary constraint in prompt, shorten reviewer output paths

- coder prompt: add '禁止修改 agents/ 或 hooks/' constraint
- reviewer outputs: migrate to project-root review-output/

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 更新 build.skill.md — 路径 + 修复 prompt + 边界约束

**Files:**
- Modify: `agents/scheduler/build.skill.md:63,71,88-90`（Phase 3/4 路径）+ 修复 prompt 语义 + 边界声明

- [ ] **Step 1: 更新 Phase 3 REVIEW_PASSED 路径（第 63 行）**

将：
```
- ✅ 流水线成功！读取 `agents/reviewer/check_system/review-output/final-review-report.md` 并展示内容给用户。
```
替换为：
```
- ✅ 流水线成功！读取 `review-output/final-review-report.md` 并展示内容给用户。
```

- [ ] **Step 2: 更新 Phase 3 REVIEW_FAILED 超限路径（第 71 行）**

将：
```
- ❌ 超出最大轮次。读取 `agents/reviewer/check_system/review-output/final-review-report.md` 并展示内容。
```
替换为：
```
- ❌ 超出最大轮次。读取 `review-output/final-review-report.md` 并展示内容。
```

- [ ] **Step 3: 更新 Phase 4 修复轮 prompt 中的文件路径**

将 Phase 4 的 3 个文件路径从：
```
1. agents/reviewer/check_system/review-output/pre-check-result.json — 程序预检结果
2. agents/reviewer/check_system/review-output/review-result.json — AI 语义检查结果
3. agents/reviewer/check_system/review-output/pre-check-report.md — 预检报告
```
替换为：
```
1. review-output/pre-check-result.json — 程序预检结果
2. review-output/review-result.json — AI 语义检查结果
3. review-output/pre-check-report.md — 预检报告
```

- [ ] **Step 4: 更新修复目标语义**

将：
```
然后逐个修复所有 P0 问题。修复原则：
```
替换为：
```
然后逐个修复所有阻断级问题（P0 必须修，P1 和 AI-FAIL 也尽量修），一次性全部解决。

修复原则（重要！）：
- 同一轮中修复所有级别的问题，不要分批。P0/P1/AI-FAIL 能修的一起修，避免多轮修复
```

- [ ] **Step 5: 在修复原则中添加边界约束**

在修复原则列表后、`- 不确定的改动，加注释说明原因` 之后，新增：

```
⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml（如需添加依赖）。禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。
```

- [ ] **Step 6: 验证路径不包含 agents/ 前缀**

```bash
grep "review-output/" agents/scheduler/build.skill.md
```
Expected: 输出路径为 `review-output/...` 而不是 `agents/reviewer/check_system/review-output/...`

- [ ] **Step 7: 验证修复 prompt 包含"一次性全部"语义**

```bash
grep "一次性全部\|所有阻断级\|所有级别" agents/scheduler/build.skill.md
```
Expected: 有输出，包含新的修复策略措辞

- [ ] **Step 8: 验证边界约束存在**

```bash
grep "agents/" agents/scheduler/build.skill.md
```
Expected: 输出包含 "禁止修改 agents/" 边界声明

- [ ] **Step 9: Commit**

```bash
git add agents/scheduler/build.skill.md
git commit -m "fix: shorten review-output paths, fix-all-blocking-issues prompt, add boundary constraint

- Phase 3/4 paths: agents/reviewer/check_system/review-output/ → review-output/
- Fix prompt: '修复所有 P0' → '一次性修复所有阻断级 P0/P1/AI-FAIL'
- Add boundary constraint: coder must not modify agents/ or hooks/

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 更新 review.skill.md — 产物路径

**Files:**
- Modify: `agents/reviewer/review.skill.md:22-23,33,36,41`（Step 1/2/3 中的产物路径）

- [ ] **Step 1: 更新 Step 1 产物路径描述**

将两处 `review-output/pre-check-result.json` 和 `review-output/pre-check-report.md` 更新为从 check_system 工作目录出发的相对路径 `../../../review-output/pre-check-result.json` 和 `../../../review-output/pre-check-report.md`。

定位到 review.skill.md 第 22-23 行：
```
- `exit 0`：预检通过，`review-output/pre-check-result.json` 已生成 → 继续 Step 2
- `exit 1`：预检未通过，`review-output/pre-check-result.json` + `review-output/pre-check-report.md` 已生成 → **停止。** 返回 `REVIEW_FAILED`，不执行后续步骤
```

替换为：
```
- `exit 0`：预检通过，`../../../review-output/pre-check-result.json` 已生成 → 继续 Step 2
- `exit 1`：预检未通过，`../../../review-output/pre-check-result.json` + `../../../review-output/pre-check-report.md` 已生成 → **停止。** 返回 `REVIEW_FAILED`，不执行后续步骤
```

- [ ] **Step 2: 更新 Step 2 产物路径**

将第 33 行：
```
- `review-output/pre-check-result.json` — 程序预检的线索和上下文
```
替换为：
```
- `../../../review-output/pre-check-result.json` — 程序预检的线索和上下文
```

将第 36 行：
```
输出：`review-output/review-result.json`
```
替换为：
```
输出：`../../../review-output/review-result.json`
```

- [ ] **Step 3: 更新 Step 3 产物路径**

将第 41 行：
```
将生成的 `review-output/final-review-report.md` 内容展示给用户。
```
替换为：
```
将生成的 `../../../review-output/final-review-report.md` 内容展示给用户。
```

- [ ] **Step 4: 更新产物路径说明**

在 review.skill.md Step 2 的工作目录说明后，添加产物路径说明。将：
```
工作目录为 `agents/reviewer/check_system/`（与 Step 1 和 Step 3 保持一致），产物路径 `review-output/` 均相对于此目录。
```
替换为：
```
工作目录为 `agents/reviewer/check_system/`（与 Step 1 和 Step 3 保持一致）。产物输出到项目根目录的 `review-output/`，从当前工作目录的引用路径为 `../../../review-output/`。
```

- [ ] **Step 5: 验证路径更新**

```bash
grep "review-output/" agents/reviewer/review.skill.md
```
Expected: 所有 `review-output/` 前都有 `../../../` 前缀

- [ ] **Step 6: Commit**

```bash
git add agents/reviewer/review.skill.md
git commit -m "fix: update review.skill.md product paths to project-root review-output/

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 更新 .gitignore — 排除 review-output

**Files:**
- Modify: `.gitignore`（新增一行）

- [ ] **Step 1: 在 .gitignore 末尾追加 review-output/ 排除**

在文件末尾追加一行：
```
/review-output/
```

注意：前面加 `/` 确保只匹配项目根目录的 `review-output/`，避免误匹配深层子目录。

- [ ] **Step 2: 验证 git ignore 生效**

```bash
git status --porcelain -- review-output/ 2>&1
```
Expected: 无输出（git 不追踪 review-output/ 下的文件）

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add /review-output/ to .gitignore

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: 端到端验证

**Files:**
- 只读，不修改任何文件

**目标：** 从文件层面验证所有改动的一致性，确认路径、配置、脚本之间无冲突。

- [ ] **Step 1: 验证 Python CLI 可正常导入**

```bash
cd agents/reviewer/check_system && python3 -c "from code_check.cli import main; print('CLI import OK')"
```
Expected: `CLI import OK`

- [ ] **Step 2: 验证 code-check-config.yaml 的 output_dir 被 CLI 正确解析**

```bash
cd agents/reviewer/check_system && python3 -c "
from code_check.config import load_config
cfg = load_config('code-check-config.yaml')
print(f'output_dir: {cfg.output_dir}')
print(f'strategy: {cfg.strategy}')
assert cfg.strategy == 'normal', f'Expected strategy=normal, got {cfg.strategy}'
print('Config OK')
"
```
Expected: `Config OK`

- [ ] **Step 3: 验证 review-pre-hook.sh 路径一致性**

```bash
# 用 bash -x 干跑（不实际执行 scan），检查变量解析
cd /tmp && bash -n "$OLDPWD/agents/reviewer/hooks/review-pre-hook.sh" && echo "Syntax OK"
```
Expected: `Syntax OK`

- [ ] **Step 4: 验证 review-post-hook.sh 中 PROJECT_DIR 在默认参数之前定义**

```bash
grep -n "PROJECT_DIR\|PRE_CHECK_JSON\|SCRIPT_DIR" agents/reviewer/hooks/review-post-hook.sh | head -10
```
Expected: `PROJECT_DIR` 的行号 < `PRE_CHECK_JSON` 的行号

- [ ] **Step 5: 验证所有文件中的 review-output 路径一致性**

```bash
echo "=== pipeline.yaml ===" && grep "review-output" agents/scheduler/pipeline.yaml && echo "" && echo "=== build.skill.md ===" && grep "review-output" agents/scheduler/build.skill.md && echo "" && echo "=== review.skill.md ===" && grep "review-output" agents/reviewer/review.skill.md
```
Expected: pipeline.yaml 和 build.skill.md 中路径为 `review-output/...`（短路径），review.skill.md 中为 `../../../review-output/...`（从 check_system 出发的相对路径）

- [ ] **Step 6: 验证 review.skill.md 返回协议完整**

```bash
grep -c "REVIEW_PASSED\|REVIEW_FAILED\|REVIEW_ERROR" agents/reviewer/review.skill.md
```
Expected: 至少 3

- [ ] **Step 7: 验证 settings.json hook 配置中的脚本路径存在**

```bash
python3 -c "
import json, os
d = json.load(open('.claude/settings.json'))
for hook_set in d['hooks'].get('PreToolUse', []):
    for h in hook_set.get('hooks', []):
        cmd = h.get('command', '')
        if 'block-agents-write.sh' in cmd:
            script = cmd.split()[-1]
            script = script.replace('\${CLAUDE_PROJECT_DIR}', os.getcwd())
            print(f'Checking: {script}')
            assert os.path.exists(script), f'Script not found: {script}'
            print('Hook script exists OK')
"
```
Expected: `Hook script exists OK`

- [ ] **Step 8: 验证 hook 脚本可执行**

```bash
test -x hooks/block-agents-write.sh && echo "Executable OK" || echo "NOT EXECUTABLE"
```
Expected: `Executable OK`

- [ ] **Step 9: 列出本次所有改动文件，做最终盘点**

```bash
echo "=== Modified/Created files ===" && git diff --stat HEAD~8 2>/dev/null || git diff --stat HEAD~7 2>/dev/null
```
Expected: 9 个文件改动（含 1 个新建），覆盖设计文档中的所有改动项

- [ ] **Step 10: 运行已有测试确保未破坏**

```bash
cd agents/reviewer/check_system && python3 -m pytest tests/ -q
```
Expected: 所有测试通过（126 passed）

- [ ] **Step 11: Commit（如有修改）**

如果验证中触发了任何修改：
```bash
git add -A
git commit -m "chore: end-to-end validation of P0/P1 pipeline fix

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
否则：输出 "验证通过，无需修改"
