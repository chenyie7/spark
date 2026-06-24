# /build 续接机制和 run_id 命名优化

> **状态:** 已确认 | **日期:** 2026-06-24

## 目标

1. `/build` 默认全新开始，仅 `--continue` 时续接上次未完成的流水线
2. `run_id` 格式从 `YYYYMMDDHHmmss-NNN` 改为 `YYYYMMDDHHmmss-<target_dir>`

## 背景

当前 `/build` 每次启动都检测 `pipeline-state.json` 是否存在，询问用户是否续接。正常完成后再次使用 `/build` 时这个询问是多余的——用户大多数情况下需要全新开始。

同时 `run_id` 的计数器后缀（`-001`、`-002`）没有实际意义。用 `target_dir` 的目录名作为后缀更有可读性，一眼就能知道这次运行生成了哪个模块的代码。

## 设计

### run_id 新格式

```
格式: YYYYMMDDHHmmss-<target_dir目录名>

target_dir = "admin-test"     → 20260624153000-admin-test
target_dir = "modules/user"   → 20260624153000-user
target_dir = "."              → 20260624153000          （默认值不加后缀）
```

### 交互流程

```
之前:
  /build 实现登录
    → 检测 pipeline-state.json → 问「是否续接？」→ 用户感到困扰

之后:
  /build 实现登录
    → 全新开始，不检测旧状态，不询问

  /build --continue
    → 跳过初始化，直接进入 Phase 1 循环（续接上次的 pipeline-state.json）
    → 如果 pipeline-state.json 不存在，提示「没有可续接的流水线」

  /build 实现登录 --target-dir admin-test
    → 全新开始，run_id = 20260624153000-admin-test
```

### CTRL+C 中断处理

CTRL+C 中断时 `pipeline-state.json` 保留。用户如需续接：

```
/build --continue
```

## 变更清单

### 1. `cli.py` — `_generate_run_id` 改为新格式

**文件:** `agents/scheduler/pipeline_engine/cli.py`

```diff
- def _generate_run_id(output_base: Path) -> str:
-     """生成唯一运行 ID，格式: YYYYMMDDHHmmss-NNN
-     扫描 output_base 目录下当天已有的子目录名，计数器 +1。
-     例如当天第 1 次运行 → 20260624103000-001。
-     """
-     from datetime import datetime, timezone
-     now = datetime.now(timezone.utc)
-     prefix = now.strftime("%Y%m%d%H%M%S")
- 
-     max_counter = 0
-     if output_base.exists():
-         for entry in output_base.iterdir():
-             if entry.is_dir() and entry.name.startswith(prefix):
-                 try:
-                     counter = int(entry.name.split("-")[-1])
-                     max_counter = max(max_counter, counter)
-                 except (ValueError, IndexError):
-                     pass
- 
-     return f"{prefix}-{max_counter + 1:03d}"
+ def _generate_run_id(target_dir: str) -> str:
+     """生成运行 ID，格式: YYYYMMDDHHmmss-<target_dir>
+ 
+     target_dir 为 "." 时不加后缀，如 20260624153000。
+     target_dir 为 "admin-test" 时加后缀，如 20260624153000-admin-test。
+     """
+     from datetime import datetime, timezone
+     timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
+     if target_dir and target_dir != ".":
+         return f"{timestamp}-{target_dir}"
+     return timestamp
```

`cmd_start()` 中的调用点同步更新：

```diff
- run_id = _generate_run_id(Path("review-output"))
+ run_id = _generate_run_id(args.target_dir)
```

### 2. `build.skill.md` — Phase 0 简化续接逻辑

**文件:** `agents/scheduler/build.skill.md`

Phase 0 从：

```markdown
1. 检测 `review-output/pipeline-state.json` 是否存在：
   - 存在 → 询问用户「续接？」
   - 续接 → 直接进入 Phase 1 循环
   - 重新开始 → reset，继续初始化
2. 解析用户输入中的 `--target-dir` 参数...
```

改为：

```markdown
1. 如果用户使用了 `--continue`：
   - 检测 `review-output/pipeline-state.json` 是否存在
   - 存在 → 直接进入 Phase 1 循环
   - 不存在 → 提示「没有可续接的流水线，请使用 /build <需求> 开始新的构建」
2. 解析用户输入中的 `--target-dir` 参数...
```

同时更新用法说明（第 8 行）：

```markdown
用法：`/build <需求描述> [--target-dir <目录>]`
续接：`/build --continue`
```

### 3. `engine.py` — `PipelineState.start()` 默认 run_id 格式

**文件:** `agents/scheduler/pipeline_engine/engine.py`

`PipelineState.start()` 在 `run_id` 为空时生成的默认值也需同步更新（移除 `-000` 后缀）：

```diff
  if not self.run_id:
-     self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-000"
+     self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
```

## 测试计划

### CLI 测试（`test_cli.py`）
- `_generate_run_id("admin-test")` 返回 `YYYYMMDDHHmmss-admin-test` 格式
- `_generate_run_id(".")` 返回纯时间戳格式（无后缀）
- `start --target-dir admin-test` 后 state 中的 `run_id` 包含 `-admin-test` 后缀
- `start`（默认 target_dir）后 `run_id` 为纯时间戳

### 引擎测试（`test_engine.py`）
- `PipelineState.start()` 在未设置 `run_id` 时生成纯时间戳格式

## 非目标

- 不改变 `review-output/{run_id}/` 的目录结构——产物仍然放在 run_id 子目录下
- 不改变中断时的状态保留机制——CTRL+C 后 `pipeline-state.json` 仍然保留
