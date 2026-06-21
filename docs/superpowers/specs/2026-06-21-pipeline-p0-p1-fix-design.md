# 流水线 P0/P1 缺陷修复设计

## 背景

首次 `/build` 流水线实际运行（实现登录注册功能）暴露了三个核心问题：

| # | 严重度 | 问题 | 现象 |
|---|--------|------|------|
| 1 | 🚨 P0 | **coder 越权修改 review 系统文件** | R2 中 coder 发现 `@RequiredArgsConstructor` 注解检测不到，直接修改了 `scanner.py` 的 `_has_annotation` 函数——参赛选手改了裁判的规则 |
| 2 | 🟡 P1 | **review-output 路径不合理** | 产物混在 `agents/reviewer/check_system/` 里，和 Agent 源码同目录，路径冗长，Git 管理困难 |
| 3 | 🟡 P1 | **修复收敛慢** | 每轮只修一个级别的问题（R1→P0，R2→P1，R3→AI），本应 2 轮收敛却跑了 3 轮 |

详细运行报告：[2026-06-21-build-login-register.md](../../pipeline-reports/2026-06-21-build-login-register.md)

---

## 改动范围总览

| # | 问题 | 改动文件 | 改动量 |
|---|------|---------|--------|
| P0-1 | coder 越权 | `.claude/settings.json` + 新建 `hooks/block-agents-write.sh` + `pipeline.yaml` + `build.skill.md` | ~4 文件 |
| P0-2 | 路径迁移 | `code-check-config.yaml` + 2 个 hook 脚本 + `pipeline.yaml` + `build.skill.md` + `review.skill.md` + `.gitignore` | ~6 文件 |
| P1 | 收敛优化 | `code-check-config.yaml` + `build.skill.md` | ~2 文件 |

---

## P0-1: Hook + Prompt 双层边界防护

### 问题回顾

Round 2 修复时，coder 为修复 `@RequiredArgsConstructor` 注解检测问题，直接修改了 `agents/reviewer/check_system/code_check/scanner.py`。review 系统的代码被「参赛选手」修改，破坏了分层隔离。

### 方案：B + A 组合

```
┌──────────────────────────────────────────┐
│  Hook（硬约束）                            │
│  PreToolUse → 拦截 Write/Edit to agents/  │
│  → 拒绝 + 返回错误信息                      │
│  不可绕过，适合权限控制                      │
├──────────────────────────────────────────┤
│  Prompt（软约束）                           │
│  "你只能修改 src/main/java 下的文件"        │
│  告知 AI 边界，减少试探性越权                │
└──────────────────────────────────────────┘
```

### Hook 脚本

**新文件**：`hooks/block-agents-write.sh`（项目根目录，和 `agents/` 同级）

脚本逻辑：
1. 解析 `CLAUDE_TOOL_INPUT` 环境变量获取 `file_path`
2. 如果 `file_path` 以 `agents/` 开头 → exit 1（拒绝），附带提示信息
3. 否则 → exit 0（放行）

**原因**：`review-output/` 迁到根目录后（P0-2），不需要在 `agents/` 下开例外。Reviewer 通过 Python CLI（Bash 工具）写产物，不走 Write/Edit。主控 Agent 只编排不写文件。

### settings.json 配置

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
      // 已有配置保持不变
    ]
  }
}
```

### Prompt 边界声明

在 `pipeline.yaml` 的 coder `prompt_template` 末尾新增：

```
⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml。
禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。
```

在 `build.skill.md` Phase 4 修复轮 prompt 中新增边界约束。

### 不改

- 不引入 Docker / worktree 隔离 —— 当前阶段为过度设计
- CLI 自身完整性校验 —— 后续 P2 优化

---

## P0-2: review-output 路径迁移

### 问题回顾

当前产物输出到 `agents/reviewer/check_system/review-output/`，与 Agent 源码混在同一棵目录树下：
- 语义混淆：产物和源码边界模糊
- Git 管理困难：产物不应和源码同目录
- 路径冗长：所有引用方都要拼长路径

### 方案

统一输出到项目根目录，和 `agents/`、`src/` 平级：

```
迁移前：                            迁移后：
agents/reviewer/check_system/       agents/reviewer/check_system/  ← 只有 Agent 源码
├── code_check/                     ├── code_check/
├── rules/                          ├── rules/
├── hooks/                          ├── hooks/
├── review-output/  ← 混在一起      ├── code-check-config.yaml
│   └── ...                         └── ...
└── code-check-config.yaml
                                    review-output/  ← 项目根目录，和 agents/ src/ 平级
                                    ├── pre-check-result.json
                                    ├── pre-check-report.md
                                    ├── review-result.json
                                    └── final-review-report.md
```

### 需要修改的文件（6 个）

| 文件 | 改动 |
|------|------|
| `code-check-config.yaml` | `output_dir: ./review-output/` → `../../../review-output/`（相对于 check_system/ 解析到根目录） |
| `review-pre-hook.sh` | `$CHECK_SYSTEM_DIR/review-output/` → `$PROJECT_DIR/review-output/` |
| `review-post-hook.sh` | 默认参数 `./review-output/` → `$PROJECT_DIR/review-output/`，产物查找路径更新 |
| `pipeline.yaml` | `reviewer.outputs` 的 3 个路径从 `agents/reviewer/check_system/review-output/...` 缩短为 `review-output/...` |
| `build.skill.md` | Phase 3 和 Phase 4 中 5 处路径缩短 |
| `review.skill.md` | Step 1/2/3 中产物路径引用更新 |
| `.gitignore` | 新增 `/review-output/` |

### 不改

- Python CLI 代码 —— 只通过 `code-check-config.yaml` 的 `output_dir` 获取路径，不硬编码
- `review-prompt.md` —— 由 Step 2 的 AI 动态传入路径，不硬编码

---

## P1: 修复收敛优化

### 问题回顾

本次运行中，每轮只处理了一个级别的问题（R1→P0，R2→P1，R3→AI），效率不高。根因是修复轮 prompt 说了「修复所有 P0 问题」而非「修复所有阻断级问题」。

### 方案

**修复轮 prompt 语义变更**：

```diff
- 然后逐个修复所有 P0 问题。
+ 然后逐个修复所有阻断级问题（P0 必须修，P1 和 AI-FAIL 也尽量修），一次性全部解决。
```

修改位置：
- `build.skill.md` Phase 4 修复轮 prompt

这样 coder 在同一轮中修复所有级别的问题，而不是分批。理论上 R0 生成 → R1 修全部 → R2 验证 PASS，2 轮收敛。

---

## 不做的事（YAGNI）

- 不让主控读 JSON 或构造问题详情 — coder 自己读产物（现有设计已满足）
- 不做增量扫描 — 每轮全量扫描（现有行为）
- 不做并行修复 — 单 Agent 顺序修复
- 不引入 Docker / worktree 隔离 — 当前 Hook 方案足够
- 不修复 scanner.py 的 `_has_annotation` bug — 那是另一条变更线，不应在流水线中途由 coder 修

---

## 验证方式

1. Hook 验证：启动 coder Agent，让它尝试 Write 一个 `agents/` 下的文件，验证被拦截
2. 路径验证：流水线跑完后检查 `review-output/` 在项目根目录，产物完整
3. 收敛验证：R0 生成 → 审查发现 P0+P1 → R1 一次性修全部 → 再审查 PASS
