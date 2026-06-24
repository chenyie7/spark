# Custom Target Directory for /build Pipeline

> **Status:** Approved | **Date:** 2026-06-24

## Goal

Allow users to specify a custom module root directory when running `/build`, so the coder agent generates code under `<target-dir>/src/main/java/` instead of always using the project root. This enables multi-module code generation within a single repository.

## Motivation

Currently `pipeline.yaml` hardcodes `src/main/java` as the coder output path. Every `/build` run writes to the same location. Users who want to generate code for a separate module (e.g., `admin-test/`, `modules/user-svc/`) have no mechanism to redirect output — the pipeline always targets the project root.

## Design

### Concept

`--target-dir` specifies the **module root directory**. The coder generates Java code under `<target-dir>/src/main/java/` following standard Maven structure.

```
Default (".")          → ./src/main/java/
admin-test             → ./admin-test/src/main/java/
modules/user-svc       → ./modules/user-svc/src/main/java/
```

### Data Flow

```
/build 实现登录 --target-dir admin-test
  │
  ▼
build.skill.md Phase 0
  │  parse --target-dir, prompt if missing
  ▼
pipeline_engine.cli start --target-dir admin-test
  │  → PipelineState.target_dir = "admin-test"
  ▼
pipeline_engine.cli next
  │  → _render_prompt substitutes {target_dir}
  ▼
coder prompt:
  "将生成的 Java 代码写入 admin-test/src/main/java 对应包路径下"
  ▼
pipeline_engine.cli next (reviewer)
  │  → reviewer prompt receives {target_dir}
  ▼
reviewer prompt:
  "审查 admin-test/src/main/java 目录"
```

### Interaction Flow

```
/build 实现登录 --target-dir admin-test
  → uses admin-test directly, no prompt

/build 实现登录
  → "是否需要自定义代码输出目录？（当前默认: 项目根目录 src/main/java）
     输入模块目录名或直接回车跳过："
     ├─ admin-test      → uses admin-test
     ├─ modules/user    → uses modules/user
     └─ <回车>/否/不    → uses "." (default)
```

### Template Variables

New variable available in `pipeline.yaml` prompt templates:

| Variable | Source | Example |
|----------|--------|---------|
| `{target_dir}` | `PipelineState.target_dir` | `"admin-test"` |

Existing variables unchanged: `{requirement}`, `{review_context}`, `{round}`, `{max_retries}`, `{run_id}`.

## Changes

### 1. `PipelineState` — new field

**File:** `agents/scheduler/pipeline_engine/models.py`

```python
@dataclass
class PipelineState:
    # ... existing fields ...
    target_dir: str = "."   # NEW: 模块根目录，相对于项目根
```

`from_dict()` / `to_dict()` updated accordingly.

### 2. CLI `start` — new `--target-dir` argument

**File:** `agents/scheduler/pipeline_engine/cli.py`

```python
p_start.add_argument("--target-dir", default=".",
                     help="模块根目录（相对于项目根）")
```

In `cmd_start()`:

```python
state = engine.start(args.requirement)
state.target_dir = args.target_dir  # after engine.start() sets default
engine._save_state()
```

### 3. Engine `_render_prompt` — add `{target_dir}`

**File:** `agents/scheduler/pipeline_engine/engine.py`

```python
variables = {
    "requirement": self.state.requirement,
    "review_context": review_context,
    "round": str(self.state.round),
    "max_retries": str(self.config.defaults.max_retries),
    "run_id": self.state.run_id,
    "target_dir": self.state.target_dir,    # NEW
}
```

### 4. `pipeline.yaml` — replace hardcoded path

**File:** `agents/scheduler/pipeline.yaml`

Coder prompt_template — 三处 `src/main/java` 替换为 `{target_dir}/src/main/java`:

```diff
- ⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml（如需添加依赖）。
+ ⚠️ 边界约束：你只能修改 {target_dir}/src/main/java/ 目录下的 Java 文件和 {target_dir}/pom.xml（如需添加依赖）。

- 将生成的 Java 代码写入 src/main/java 对应包路径下。
+ 代码输出目录：{target_dir}/src/main/java
+ 将生成的 Java 代码写入 {target_dir}/src/main/java 对应包路径下。
```

Reviewer prompt_template step 1:
```diff
- 1. 调用 Skill 工具执行 review：使用 skill="review", args="src/main/java"
+ 1. 调用 Skill 工具执行 review：使用 skill="review", args="{target_dir}/src/main/java"
```

### 5. `build.skill.md` — Phase 0 interaction

**File:** `agents/scheduler/build.skill.md`

Phase 0 updated to:
1. Parse `--target-dir` from user input
2. If absent, ask user once
3. Pass to `pipeline_engine.cli start --target-dir <value>`

## Test Plan

### Unit tests (`test_models.py`)
- `target_dir` defaults to `"."` in new `PipelineState`
- `from_dict` / `to_dict` roundtrip preserves `target_dir`
- `from_dict` with missing `target_dir` falls back to `"."`

### Unit tests (`test_engine.py`)
- `_render_prompt` substitutes `{target_dir}` in coder prompt
- `_render_prompt` substitutes `{target_dir}` in reviewer prompt
- `{target_dir}` present in coder prompt with custom value
- `{target_dir}` present in reviewer prompt with custom value

### CLI tests (`test_cli.py`)
- `start --target-dir admin-test` stores value in state file
- `start` without `--target-dir` defaults to `"."`
- `next` returns prompt containing custom `target_dir`

### Integration tests
- End-to-end: `/build 简单需求 --target-dir test-output` verifies files land in `test-output/src/main/java/`
- End-to-end: `/build 简单需求` (no flag) verifies interactive prompt works

## Non-Goals

- Creating the target directory — coder agent creates directories as needed
- Validating the target directory exists before start — invalid directories fail naturally at generation time
- Persisting target_dir across `/build` runs — this is per-run only
