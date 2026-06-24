# /build 自定义代码输出目录

> **状态:** 已确认 | **日期:** 2026-06-24

## 目标

允许用户在运行 `/build` 时指定自定义模块根目录，coder agent 将代码生成在 `<target-dir>/src/main/java/` 下，而非始终使用项目根目录。这使得在单一仓库中进行多模块代码生成成为可能。

## 背景

当前 `pipeline.yaml` 将 `src/main/java` 硬编码为 coder 的输出路径。每次 `/build` 运行都写入同一位置。用户如果想要为独立模块（如 `admin-test/`、`modules/user-svc/`）生成代码，无法重定向输出——流水线始终以项目根目录为目标。

## 设计

### 概念模型

`--target-dir` 指定的是**模块根目录**。coder 按照 Maven 标准结构，在 `<target-dir>/src/main/java/` 下生成 Java 代码。

```
默认值（"."）           → ./src/main/java/
admin-test             → ./admin-test/src/main/java/
modules/user-svc       → ./modules/user-svc/src/main/java/
```

### 数据流

```
/build 实现登录 --target-dir admin-test
  │
  ▼
build.skill.md Phase 0
  │  解析 --target-dir 参数，缺失则交互询问
  ▼
pipeline_engine.cli start --target-dir admin-test
  │  → PipelineState.target_dir = "admin-test"
  ▼
pipeline_engine.cli next
  │  → _render_prompt 替换模板变量 {target_dir}
  ▼
coder 的 prompt:
  "将生成的 Java 代码写入 admin-test/src/main/java 对应包路径下"
  ▼
pipeline_engine.cli next（reviewer）
  │  → reviewer prompt 接收 {target_dir}
  ▼
reviewer 的 prompt:
  "审查 admin-test/src/main/java 目录"
```

### 交互流程

```
/build 实现登录 --target-dir admin-test
  → 直接使用 admin-test，不询问

/build 实现登录
  → "是否需要自定义代码输出目录？（当前默认: 项目根目录 src/main/java）
     输入模块目录名或直接回车跳过："
     ├─ admin-test      → 使用 admin-test
     ├─ modules/user    → 使用 modules/user
     └─ <回车>/否/不    → 使用默认值 "."
```

### 模板变量

`pipeline.yaml` prompt 模板中新增的变量：

| 变量 | 来源 | 示例 |
|------|------|------|
| `{target_dir}` | `PipelineState.target_dir` | `"admin-test"` |

已有变量不变：`{requirement}`、`{review_context}`、`{round}`、`{max_retries}`、`{run_id}`。

## 变更清单

### 1. `PipelineState` — 新增字段

**文件:** `agents/scheduler/pipeline_engine/models.py`

```python
@dataclass
class PipelineState:
    # ... 已有字段 ...
    target_dir: str = "."   # 新增：模块根目录，相对于项目根
```

同步更新 `from_dict()` / `to_dict()`。

### 2. CLI `start` — 新增 `--target-dir` 参数

**文件:** `agents/scheduler/pipeline_engine/cli.py`

```python
p_start.add_argument("--target-dir", default=".",
                     help="模块根目录（相对于项目根）")
```

`cmd_start()` 中，除设置 `target_dir` 外，还需同步更新 `code-check-config.yaml`，使 reviewer 的程序预检使用正确的扫描路径和输出目录：

```python
state = engine.start(args.requirement)
state.target_dir = args.target_dir
engine._save_state()

# 同步更新 code-check-config.yaml，确保 reviewer 的扫描路径和输出目录正确
_config_path = Path("agents/reviewer/check_system/code-check-config.yaml")
if _config_path.exists():
    import yaml
    with open(_config_path, "r") as f:
        _cfg = yaml.safe_load(f) or {}
    _cfg["default_scan_path"] = f"../../../{state.target_dir}/src/main/java"
    _cfg["output_dir"] = f"../../../review-output/{state.run_id}/"
    with open(_config_path, "w") as f:
        yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)
```

### 3. Engine `_render_prompt` — 新增 `{target_dir}` 变量

**文件:** `agents/scheduler/pipeline_engine/engine.py`

```python
variables = {
    "requirement": self.state.requirement,
    "review_context": review_context,
    "round": str(self.state.round),
    "max_retries": str(self.config.defaults.max_retries),
    "run_id": self.state.run_id,
    "target_dir": self.state.target_dir,    # 新增
}
```

### 4. `pipeline.yaml` — 替换硬编码路径

**文件:** `agents/scheduler/pipeline.yaml`

Coder prompt_template — 三处 `src/main/java` 替换为 `{target_dir}/src/main/java`：

```diff
- ⚠️ 边界约束：你只能修改 src/main/java/ 目录下的 Java 文件和项目根目录的 pom.xml（如需添加依赖）。
+ ⚠️ 边界约束：你只能修改 {target_dir}/src/main/java/ 目录下的 Java 文件和 {target_dir}/pom.xml（如需添加依赖）。

- 将生成的 Java 代码写入 src/main/java 对应包路径下。
+ 代码输出目录：{target_dir}/src/main/java
+ 将生成的 Java 代码写入 {target_dir}/src/main/java 对应包路径下。
```

Reviewer prompt_template 步骤 1：
```diff
- 1. 调用 Skill 工具执行 review：使用 skill="review", args="src/main/java"
+ 1. 调用 Skill 工具执行 review：使用 skill="review", args="{target_dir}/src/main/java"
```

### 5. `build.skill.md` — Phase 0 交互

**文件:** `agents/scheduler/build.skill.md`

Phase 0 更新为：
1. 从用户输入解析 `--target-dir`
2. 缺失时交互询问一次
3. 传入 `pipeline_engine.cli start --target-dir <值>`

### 6. `engine.py` — 修复轮次路径加入 `{run_id}`

**文件:** `agents/scheduler/pipeline_engine/engine.py`

`_render_prompt` 中修复轮次的 `review_context` 路径，加上 `{run_id}` 子目录：

```diff
- "1. review-output/pre-check-result.json — 程序预检结果\n"
- "2. review-output/review-result.json — AI 语义检查结果（如存在）\n"
- "3. review-output/pre-check-report.md — 预检报告\n\n"
+ "1. review-output/{run_id}/pre-check-result.json — 程序预检结果\n"
+ "2. review-output/{run_id}/review-result.json — AI 语义检查结果（如存在）\n"
+ "3. review-output/{run_id}/pre-check-report.md — 预检报告\n\n"
```

### 7. `pipeline.yaml` — reviewer outputs 加入 `{run_id}`

**文件:** `agents/scheduler/pipeline.yaml`

```diff
      outputs:
-       - pre_check: "review-output/pre-check-result.json"
-       - ai_review: "review-output/review-result.json"
-       - final_report: "review-output/final-review-report.md"
+       - pre_check: "review-output/{run_id}/pre-check-result.json"
+       - ai_review: "review-output/{run_id}/review-result.json"
+       - final_report: "review-output/{run_id}/final-review-report.md"
```

### 8. `review-post-hook.sh` — 默认路径去掉硬编码 run_id

**文件:** `agents/reviewer/hooks/review-post-hook.sh`

移除硬编码的旧 run_id，改为从 `code-check-config.yaml` 读取 `output_dir`：

```diff
- PRE_CHECK_JSON="${1:-$PROJECT_DIR/review-output/20260624035444-001/pre-check-result.json}"
- AI_CHECK_JSON="${2:-$PROJECT_DIR/review-output/20260624035444-001/review-result.json}"
- OUTPUT_MD="${3:-$PROJECT_DIR/review-output/20260624035444-001/final-review-report.md}"
+ # 从 code-check-config.yaml 读取 output_dir
+ OUTPUT_DIR=$(python3 -c "
+ import yaml, sys
+ with open(sys.argv[1]) as f:
+     c = yaml.safe_load(f)
+ print(c.get('output_dir', 'review-output'))
+ " "$CHECK_SYSTEM_DIR/code-check-config.yaml")
+ PRE_CHECK_JSON="${1:-$PROJECT_DIR/$OUTPUT_DIR/pre-check-result.json}"
+ AI_CHECK_JSON="${2:-$PROJECT_DIR/$OUTPUT_DIR/review-result.json}"
+ OUTPUT_MD="${3:-$PROJECT_DIR/$OUTPUT_DIR/final-review-report.md}"
```

### 9. `build.skill.md` — 终止条件路径加入 `{run_id}`

**文件:** `agents/scheduler/build.skill.md`

```diff
- `next` 返回 `action=="done"` → 读取 `review-output/final-review-report.md` 展示结果
+ `next` 返回 `action=="done"` → 读取 `review-output/{run_id}/final-review-report.md` 展示结果
```

### 10. `review.skill.md` — 产物路径加入 `{run_id}` 子目录

**文件:** `agents/reviewer/review.skill.md`

所有 `../../../review-output/` 引用改为 `../../../review-output/{run_id}/`。skill 文件由 reviewer agent 执行，agent 从 pipeline prompt 中获取 `{run_id}`，自行替换路径。

关键变更：

```diff
- `exit 0`：预检通过，`../../../review-output/pre-check-result.json` 已生成
+ `exit 0`：预检通过，`../../../review-output/{run_id}/pre-check-result.json` 已生成

- `exit 1`：预检未通过，`../../../review-output/pre-check-result.json` + `../../../review-output/pre-check-report.md` 已生成
+ `exit 1`：预检未通过，`../../../review-output/{run_id}/pre-check-result.json` + `../../../review-output/{run_id}/pre-check-report.md` 已生成

- 产物输出到项目根目录的 `review-output/`，从当前工作目录的引用路径为 `../../../review-output/`。
+ 产物输出到项目根目录的 `review-output/{run_id}/`，从当前工作目录的引用路径为 `../../../review-output/{run_id}/`。

- `../../../review-output/pre-check-result.json` — 程序预检的线索和上下文
+ `../../../review-output/{run_id}/pre-check-result.json` — 程序预检的线索和上下文

- 输出：`../../../review-output/review-result.json`
+ 输出：`../../../review-output/{run_id}/review-result.json`

- 将生成的 `../../../review-output/final-review-report.md` 内容展示给用户。
+ 将生成的 `../../../review-output/{run_id}/final-review-report.md` 内容展示给用户。
```

### 11. `review-prompt.md` — AI 检查清单路径加入 `{run_id}`

**文件:** `agents/reviewer/check_system/rules/review-prompt.md`

```diff
- 你已经拿到了程序预检的结果（`review-output/pre-check-result.json`）
+ 你已经拿到了程序预检的结果（`review-output/{run_id}/pre-check-result.json`）

- 2. **程序预检报告：** `review-output/pre-check-result.json`（含 hints_for_ai 线索）
+ 2. **程序预检报告：** `review-output/{run_id}/pre-check-result.json`（含 hints_for_ai 线索）

- 将所有检查结果汇总，输出到 **`review-output/review-result.json`**
+ 将所有检查结果汇总，输出到 **`review-output/{run_id}/review-result.json`**
```

## 测试计划

### 模型单元测试（`test_models.py`）
- 新建 `PipelineState` 时 `target_dir` 默认值为 `"."`
- `from_dict` / `to_dict` 往返保持 `target_dir` 不变
- `from_dict` 缺少 `target_dir` 时回退为 `"."`

### 引擎单元测试（`test_engine.py`）
- `_render_prompt` 在 coder prompt 中替换 `{target_dir}`
- `_render_prompt` 在 reviewer prompt 中替换 `{target_dir}`
- coder prompt 中包含自定义 `target_dir` 的值
- reviewer prompt 中包含自定义 `target_dir` 的值

### CLI 测试（`test_cli.py`）
- `start --target-dir admin-test` 将值写入状态文件
- `start` 不传 `--target-dir` 时默认为 `"."`
- `next` 返回的 prompt 中包含自定义 `target_dir`

### 集成测试
- 端到端：`/build 简单需求 --target-dir test-output` 验证文件生成在 `test-output/src/main/java/`
- 端到端：`/build 简单需求`（无参数）验证交互询问正常

## 非目标

- 不自动创建目标目录——coder agent 按需创建
- 不预先校验目标目录是否存在——无效目录在生成时自然失败
- 不在多次 `/build` 运行间持久化 `target_dir`——每次运行独立设置
