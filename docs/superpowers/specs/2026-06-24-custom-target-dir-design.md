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

`cmd_start()` 中：

```python
state = engine.start(args.requirement)
state.target_dir = args.target_dir  # engine.start() 设置默认值后覆盖
engine._save_state()
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
