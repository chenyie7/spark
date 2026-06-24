# 续接机制和 run_id 命名优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/build` 默认全新开始（`--continue` 才续接），run_id 从 `YYYYMMDDHHmmss-NNN` 改为 `YYYYMMDDHHmmss[-target_dir]`

**Architecture:** 修改 `_generate_run_id` 函数去掉计数器逻辑改为拼接 target_dir；简化 `build.skill.md` Phase 0 去掉自动续接询问；在 `conftest.py` 集中定义 run_id 示例常量，消除测试硬编码。

**Tech Stack:** Python 3 (datetime, argparse), Markdown

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|---------|
| `agents/scheduler/pipeline_engine/cli.py` | `_generate_run_id` 新格式 + `cmd_start` 调用点 | 修改 |
| `agents/scheduler/build.skill.md` | Phase 0 改为 `--continue` 触发续接 | 修改 |
| `agents/scheduler/pipeline_engine/engine.py` | `PipelineState.start()` 去掉 `-000` 后缀 | 修改 |
| `agents/scheduler/tests/conftest.py` | 新增 `SAMPLE_RUN_ID` / `SAMPLE_RUN_ID_NO_TARGET` 常量 | 修改 |
| `agents/scheduler/tests/test_cli.py` | 更新 run_id 长度断言；硬编码替换为常量 | 修改 |
| `agents/scheduler/tests/test_engine.py` | 硬编码 run_id 替换为常量 | 修改 |
| `agents/scheduler/tests/test_models.py` | 硬编码 run_id 替换为常量 | 修改 |

---

### Task 1: `cli.py` — `_generate_run_id` 改为新格式

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py:22-43` (函数定义)
- Modify: `agents/scheduler/pipeline_engine/cli.py:72` (调用点)

- [ ] **Step 1: 重写 `_generate_run_id` 函数**

将当前函数（第 22-43 行）：

```python
def _generate_run_id(output_base: Path) -> str:
    """生成唯一运行 ID，格式: YYYYMMDDHHmmss-NNN

    扫描 output_base 目录下当天已有的子目录名，计数器 +1。
    例如当天第 1 次运行 → 20260624103000-001。
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    prefix = now.strftime("%Y%m%d%H%M%S")

    # 扫描当天已有目录，找出最大计数器
    max_counter = 0
    if output_base.exists():
        for entry in output_base.iterdir():
            if entry.is_dir() and entry.name.startswith(prefix):
                try:
                    counter = int(entry.name.split("-")[-1])
                    max_counter = max(max_counter, counter)
                except (ValueError, IndexError):
                    pass

    return f"{prefix}-{max_counter + 1:03d}"
```

替换为：

```python
def _generate_run_id(target_dir: str) -> str:
    """生成运行 ID，格式: YYYYMMDDHHmmss[-target_dir]

    target_dir 为 "." 时不加后缀，如 20260624153000。
    target_dir 为 "admin-test" 时加后缀，如 20260624153000-admin-test。
    """
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if target_dir and target_dir != ".":
        return f"{timestamp}-{target_dir}"
    return timestamp
```

- [ ] **Step 2: 更新 `cmd_start` 中的调用点**

将第 72 行：

```python
    run_id = _generate_run_id(Path("review-output"))
```

替换为：

```python
    run_id = _generate_run_id(args.target_dir)
```

- [ ] **Step 3: 运行 CLI 测试确认变更正确**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py::TestCLIStart -v
```

Expected: `test_start_ok` 和 `test_start_returns_run_id` 的 run_id 断言可能需要更新（长度不再是固定 18 位），这两个测试会失败——这是预期的，Task 5 会修复。

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/pipeline_engine/cli.py
git commit -m "feat: 重写 _generate_run_id 为 {timestamp}[-{target_dir}] 格式"
```

---

### Task 2: `engine.py` — 去掉默认 `-000` 后缀

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py:310`

- [ ] **Step 1: 更新 `PipelineState.start()` 中的 run_id 默认值**

将 `models.py` 第 310 行（在 `PipelineState.start()` 方法内）：

```python
            self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-000"
```

替换为：

```python
            self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
```

- [ ] **Step 2: 运行测试确认**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py::TestPipelineState -v
```

Expected: 所有 PipelineState 测试 PASS。

- [ ] **Step 3: 提交**

```bash
git add agents/scheduler/pipeline_engine/models.py
git commit -m "fix: PipelineState.start() 默认 run_id 去掉 -000 后缀"
```

---

### Task 3: `build.skill.md` — 改为 `--continue` 触发的续接

**Files:**
- Modify: `agents/scheduler/build.skill.md:8` (用法说明)
- Modify: `agents/scheduler/build.skill.md:16-21` (Phase 0 step 1)

- [ ] **Step 1: 更新用法说明**

将第 8 行：

```markdown
用法：`/build <需求描述>`
```

替换为：

```markdown
用法：`/build <需求描述> [--target-dir <目录>]`
续接：`/build --continue`
```

- [ ] **Step 2: 重写 Phase 0 step 1**

将第 18-21 行：

```markdown
1. 检测 `review-output/pipeline-state.json` 是否存在：
   - 存在 → 调用 `python3 -m pipeline_engine.cli status --state-file review-output/pipeline-state.json`，询问用户「检测到未完成的流水线，是否续接？」
   - 续接 → 直接进入 Phase 1 循环
   - 重新开始 → `python3 -m pipeline_engine.cli reset --state-file review-output/pipeline-state.json`，然后继续初始化
```

替换为：

```markdown
1. 如果用户使用了 `--continue`：
   - 检测 `review-output/pipeline-state.json` 是否存在
   - 存在 → 直接进入 Phase 1 循环
   - 不存在 → 提示「没有可续接的流水线，请使用 /build <需求> 开始新的构建」
```

- [ ] **Step 3: 更新错误处理速查表中 CTRL+C 的说明**

将第 87 行：

```markdown
| 用户 Ctrl+C | 状态文件保留，下次运行可续接 |
```

替换为：

```markdown
| 用户 Ctrl+C | 状态文件保留，使用 `/build --continue` 续接 |
```

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: build.skill.md 改为 --continue 触发的续接，默认全新开始"
```

---

### Task 4: `conftest.py` — 新增 run_id 示例常量

**Files:**
- Modify: `agents/scheduler/tests/conftest.py:1-5` (顶部)
- Modify: `agents/scheduler/tests/test_cli.py:104`
- Modify: `agents/scheduler/tests/test_engine.py:198,204`
- Modify: `agents/scheduler/tests/test_models.py:362-375`

- [ ] **Step 1: 在 conftest.py 顶部新增常量**

在 `conftest.py` 的 import 之后（第 4 行后）添加：

```python
# 符合 {timestamp}-{target_dir} 格式的示例 run_id，供所有测试统一引用
SAMPLE_RUN_ID = "20260624103000-test"
# target_dir="." 时的纯时间戳示例 run_id
SAMPLE_RUN_ID_NO_TARGET = "20260624103000"
```

- [ ] **Step 2: 更新 `test_cli.py` 第 104 行 — 去掉固定长度断言**

将：

```python
        assert len(data["run_id"]) == 18  # YYYYMMDDHHmmss-NNN
```

替换为：

```python
        # run_id 格式: YYYYMMDDHHmmss[-target_dir]
        assert len(data["run_id"]) >= 14
        assert data["run_id"][:8].isdigit()  # 前 8 位是日期
```

- [ ] **Step 3: 更新 `test_engine.py` 第 198 行和第 204 行**

在文件顶部 import 区域（已有 `from pathlib import Path` 之后）添加：

```python
from tests.conftest import SAMPLE_RUN_ID
```

将第 198 行：

```python
        engine.state.run_id = "20260624103000-001"
```

替换为：

```python
        engine.state.run_id = SAMPLE_RUN_ID
```

将第 204 行：

```python
        assert "20260624103000-001" in action.nodes[0].prompt
```

替换为：

```python
        assert SAMPLE_RUN_ID in action.nodes[0].prompt
```

- [ ] **Step 4: 更新 `test_models.py` 第 362-375 行**

在文件顶部 import 区域添加：

```python
from tests.conftest import SAMPLE_RUN_ID
```

将三处 `"20260624103000-001"` 全部替换为 `SAMPLE_RUN_ID`：

第 362 行：

```python
        obj = PipelineState(pipeline_name="test", run_id=SAMPLE_RUN_ID)
```

第 363 行：

```python
        assert obj.run_id == SAMPLE_RUN_ID
```

第 370-375 行类似替换（测试函数 `test_run_id_roundtrip`）。

- [ ] **Step 5: 运行全部测试确认**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```

Expected: 全部测试 PASS。

- [ ] **Step 6: 提交**

```bash
git add agents/scheduler/tests/
git commit -m "test: 新增 SAMPLE_RUN_ID 常量，消除测试中硬编码 run_id"
```

---

### 执行顺序

```
Task 1 (cli.py _generate_run_id)
  → Task 2 (engine.py -000 后缀)
    → Task 3 (build.skill.md --continue)
      → Task 4 (测试常量 + 更新)
```

Tasks 1-3 是增量依赖（每个依赖前一个的变更），Task 4 依赖 Task 1。
