# 项目目录管理改进 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单一 `--target-dir` 参数拆分为 `base_path + project_name → output_dir` 两级目录结构

**Architecture:** 数据层（models.py）新增 base_path/project_name/output_dir 字段替换 target_dir；引擎层（engine.py）透传新字段到模板渲染；CLI 层（cli.py）接收新参数并拼接 output_dir；配置层（pipeline.yaml）defaults 新增字段；交互层（build.skill.md）强制要求 project_name；下游 Agent 从 .current-run 读取现成路径

**Tech Stack:** Python 3 (dataclasses, argparse), YAML, Shell

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `agents/scheduler/pipeline_engine/models.py` | `_generate_run_id()` 函数、`PipelineState` 数据类 | 修改 |
| `agents/scheduler/pipeline_engine/engine.py` | `PipelineEngine.start()` 和 `_render_prompt()` | 修改 |
| `agents/scheduler/pipeline_engine/cli.py` | `cmd_start()` CLI 参数和路径拼接 | 修改 |
| `agents/scheduler/pipeline.yaml` | defaults 节点、prompt_template 变量 | 修改 |
| `agents/scheduler/build.skill.md` | `/build` 参数解析、交互流程、.current-run 内容 | 修改 |
| `agents/coder/coder.skill.md` | 边界约束描述 | 修改 |
| `agents/scheduler/tests/conftest.py` | 共享 fixture 和 SAMPLE_PIPELINE_YAML | 修改 |
| `agents/scheduler/tests/test_models.py` | `_generate_run_id` 和 PipelineState 单测 | 修改 |
| `agents/scheduler/tests/test_engine.py` | 引擎 prompt 渲染测试 | 修改 |
| `agents/scheduler/tests/test_cli.py` | CLI 参数测试 | 修改 |
| `README.md` | 用户文档 | 修改 |

---

### Task 1: 修改 models.py — 数据模型层

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py`

- [ ] **Step 1: 修改 `_generate_run_id` 函数签名和逻辑**

将 `models.py:14-22` 替换为：

```python
def _generate_run_id(project_name: str = "") -> str:
    """生成 run_id，格式: YYYYMMDDHHmmss[-project_name]

    project_name 为空时不加后缀，如 "20260702120000"。
    project_name 为 "order-service" 时加后缀，如 "20260702120000-order-service"。
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if project_name:
        return f"{timestamp}-{project_name}"
    return timestamp
```

- [ ] **Step 2: 修改 PipelineState 字段**

将 `models.py:298-311` 的 PipelineState dataclass 字段部分替换：

```python
@dataclass
class PipelineState:
    """持久化运行时状态，保存在 pipeline-state.json 中。"""
    pipeline_name: str
    status: PipelineStatus = PipelineStatus.PENDING
    round: int = 0
    current_nodes: list[str] = field(default_factory=list)
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    requirement: str = ""
    started_at: str = ""
    updated_at: str = ""
    run_id: str = ""
    base_path: str = "."        # 项目存放位置
    project_name: str = ""      # 项目名称（必填）
    output_dir: str = ""        # 拼接结果：{base_path}/{project_name}/
```

- [ ] **Step 3: 修改 `start()` 方法**

将 `models.py:317-329` 替换为：

```python
    def start(self, requirement: str = "", base_path: str = ".", project_name: str = ""):
        """将流水线标记为待命（PENDING），生成 run_id，记录开始时间。

        不直接进入 RUNNING——由 next() 在首次派发节点时完成状态转移。
        这样 Phase 1 可以先拿到 run_id 而不触发流水线执行。
        """
        self.requirement = requirement
        self.base_path = base_path
        self.project_name = project_name
        # 拼接输出目录
        if project_name:
            self.output_dir = f"{base_path.rstrip('/')}/{project_name}/"
        else:
            self.output_dir = base_path if base_path != "." else "."
        self.status = PipelineStatus.PENDING
        self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.run_id:
            self.run_id = _generate_run_id(project_name)
        self._touch()
```

- [ ] **Step 4: 修改 `from_dict()` 和 `to_dict()`**

`from_dict()` 中（行 389 附近），将 `target_dir` 行替换为：

```python
            base_path=d.get("base_path", "."),
            project_name=d.get("project_name", ""),
            output_dir=d.get("output_dir", ""),
```

`to_dict()` 中（行 393-405 附近），将 `target_dir` 行替换为：

```python
            "base_path": self.base_path,
            "project_name": self.project_name,
            "output_dir": self.output_dir,
```

- [ ] **Step 5: 运行现有测试验证破坏性变更**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v 2>&1 | tail -20
```

Expected: 多个测试失败（因为 target_dir 字段已移除），确认变更已被测试感知。

---

### Task 2: 修改 engine.py — 引擎层

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py`

- [ ] **Step 1: 修改 `start()` 方法签名和实现**

将 `engine.py:45-67` 替换为：

```python
    def start(self, requirement: str = "", base_path: str = ".",
              project_name: str = "") -> PipelineState:
        """初始化流水线并持久化状态。

        Args:
            requirement: 用户需求描述。
            base_path: 项目存放位置（相对于项目根）。
            project_name: 项目名称（必填）。

        Raises:
            RuntimeError: 如果已有流水线在运行中（状态文件存在且状态为
                          running 或 pending）。
        """
        if self.state_path.exists():
            existing = self._load_state()
            if existing.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
                raise RuntimeError(
                    f"流水线 '{existing.pipeline_name}' 已在运行中 "
                    f"（状态: {existing.status.value}）。使用 'reset' 清除，"
                    f"或调用 'next' 继续。"
                )
        self.state = PipelineState(pipeline_name=self.config.name)
        self.state.start(requirement=requirement, base_path=base_path,
                         project_name=project_name)
        self._save_state()
        return self.state
```

- [ ] **Step 2: 修改 `_render_prompt()` 方法**

将 `engine.py:331-338` 的 variables 字典中 `target_dir` 替换为 `output_dir`，并新增 `base_path`、`project_name`：

```python
        variables = {
            "requirement": self.state.requirement,
            "review_context": review_context,
            "round": str(self.state.round),
            "max_retries": str(self.config.defaults.max_retries),
            "run_id": self.state.run_id,
            "base_path": self.state.base_path,
            "project_name": self.state.project_name,
            "output_dir": self.state.output_dir,
        }
```

---

### Task 3: 修改 cli.py — CLI 层

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py`

- [ ] **Step 1: 修改 `cmd_start` 函数**

将 `cli.py:22-68` 替换为：

```python
def cmd_start(args):
    """初始化流水线状态。"""
    pipeline_path = Path(args.pipeline)
    state_path = Path(args.state_file)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # project_name 为必填项
    if not args.project_name:
        print(json.dumps({
            "status": "error",
            "message": "project_name 为必填项。请使用 --project-name 指定项目名称。",
        }))
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        state = engine.start(requirement=args.requirement,
                             base_path=args.base_path,
                             project_name=args.project_name)
    except RuntimeError as e:
        existing = engine.status()
        print(json.dumps({
            "status": "already_running",
            "pipeline_name": existing.pipeline_name,
            "current_round": existing.round,
            "message": str(e),
        }))
        sys.exit(0)

    run_id = state.run_id
    output_dir = state.output_dir

    # 同步更新 code-check-config.yaml，确保 reviewer 的扫描路径和输出目录正确
    import yaml as _yaml
    _config_path = Path("agents/reviewer/check_system/code-check-config.yaml")
    if _config_path.exists():
        with open(_config_path, "r") as f:
            _cfg = _yaml.safe_load(f) or {}
        _cfg["default_scan_path"] = f"../../../{output_dir}src/main/java"
        _cfg["output_dir"] = f"../../../{state.base_path}/review-output/{state.project_name}/{run_id}/"
        with open(_config_path, "w") as f:
            _yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)

    print(json.dumps({
        "status": "started",
        "pipeline_name": state.pipeline_name,
        "round": 0,
        "run_id": run_id,
        "base_path": state.base_path,
        "project_name": state.project_name,
        "output_dir": output_dir,
        "max_retries": config.defaults.max_retries,
        "message": f"流水线 '{config.name}' 已启动。",
    }))
```

- [ ] **Step 2: 修改 CLI 参数定义**

将 `cli.py:173-179` 的 start 子命令参数替换为：

```python
    p_start = sub.add_parser("start", help="初始化新的流水线运行")
    p_start.add_argument("--pipeline", required=True, help="pipeline.yaml 的路径")
    p_start.add_argument("--state-file", default="review-output/pipeline-state.json",
                         help="状态文件路径")
    p_start.add_argument("--requirement", required=True, help="用户需求描述")
    p_start.add_argument("--base-path", default=".",
                         help="项目存放位置（相对于项目根）")
    p_start.add_argument("--project-name", default="",
                         help="项目名称（必填）")
```

---

### Task 4: 修改 pipeline.yaml — 流水线配置

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 更新 defaults 节点**

将 `pipeline.yaml:10-13` 替换为：

```yaml
defaults:
  timeout: 600s          # 单节点默认超时（秒）
  max_retries: 3         # reviewer → coder 最大循环轮次
  block_on: [P0]         # 触发回退的严重级别列表
  base_path: "."         # 项目存放位置，默认当前目录
  project_name: ""       # 项目名称，空则需要交互输入
```

- [ ] **Step 2: 更新 coder 节点的 prompt_template 和 outputs**

将 coder 节点中所有 `{target_dir}` 替换为 `{output_dir}`：

行 24: `先读取 review-output/.current-run 获取 output_dir 和 scan_path。`
行 43: `你只能修改 {output_dir}/src/main/java/ 目录下的 Java 文件和 {output_dir}/pom.xml`
行 46: `将生成的 Java 代码写入 {output_dir}/src/main/java 对应包路径下。`
行 51: `outputs: target_dir: "{target_dir}/src/main/java"` → `outputs: output_dir: "{output_dir}/src/main/java"`

- [ ] **Step 3: 更新 reviewer 节点的 prompt_template 和 inputs**

行 60: `先读取 review-output/.current-run 获取 output_dir 和 scan_path。`
行 64: `扫描 {output_dir}/src/main/java`
行 70: `对 {output_dir}/src/main/java 下所有 Java 文件执行统一审查`
行 81: `coder_output: "${coder.outputs.target_dir}"` → `coder_output: "${coder.outputs.output_dir}"`

---

### Task 5: 修改 build.skill.md — 构建调度入口

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 更新用法说明**

将行 8 替换为：

```
用法：`/build <需求描述> [--base-path <目录>] [--project-name <名称>]`
恢复开发：`/build --resume <run_id>`
恢复需求对话：`/build --pm <run_id>`
```

- [ ] **Step 2: 更新 Phase 0 参数解析**

将行 188-194 替换为：

```
## Phase 0: 参数解析

`--base-path` 参数解析：
- 如果用户指定了 `--base-path <值>`，直接使用该值
- 如果未指定，使用 pipeline.yaml defaults 中的 base_path（默认 "."）

`--project-name` 参数解析：
- 如果用户指定了 `--project-name <值>`，直接使用该值
- 如果未指定 → **必须交互询问用户**（不可跳过）：
  - 「请输入项目名称：」
  - 用户输入为空 → 再次询问，不允许跳过

拼接确认：
- 展示所有路径给用户确认后才进入 PM 阶段：
  「确认：
    - 项目位置：{base_path}/
    - 项目名称：{project_name}
    - 代码输出：{base_path}/{project_name}/src/main/java/
    - 审查数据：{base_path}/review-output/{project_name}/
    
    是否继续？」
  - 用户否定 → 重新输入参数
```

- [ ] **Step 3: 更新 Phase 1 start 命令**

将行 41-57 中 `--target-dir` 替换为 `--base-path` 和 `--project-name`：

```bash
   result=$(PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
   python3 -m pipeline_engine.cli start \
     --pipeline agents/scheduler/pipeline.yaml \
     --state-file review-output/.pipeline-state.tmp \
     --base-path "{base_path}" \
     --project-name "{project_name}" \
     --requirement "placeholder")
```

- [ ] **Step 4: 更新 pm-context.json 内容**

将行 62-68 中的 `target_dir` 替换为 `base_path` 和 `project_name`：

```json
   {
     "run_id": "{run_id}",
     "status": "in_progress",
     "base_path": "{base_path}",
     "project_name": "{project_name}",
     "output_dir": "{base_path}/{project_name}/",
     "requirement": "{用户原始需求}",
     "spec_file": "",
     "plan_file": ""
   }
```

- [ ] **Step 5: 更新 Phase 2 .current-run 内容**

将行 121-128 替换为：

```bash
   cat > review-output/.current-run <<EOF
   {
     "run_id": "{run_id}",
     "base_path": "{base_path}",
     "project_name": "{project_name}",
     "output_dir": "{base_path}/{project_name}/",
     "scan_path": "{base_path}/{project_name}/src/main/java",
     "review_dir": "{base_path}/review-output/{project_name}/{run_id}/"
   }
   EOF
```

- [ ] **Step 6: 更新 Phase 2 pm-context.json 读取行**

将行 101 替换为：

```
从 `review-output/{run_id}/pm-context.json` 读取 spec_file、plan_file、base_path、project_name、output_dir、原始需求。
```

- [ ] **Step 7: 更新错误处理速查表**

将行 200-203 中的 `--target-dir` 引用移除。

---

### Task 6: 修改 coder.skill.md — coder Agent 技能文件

**Files:**
- Modify: `agents/coder/coder.skill.md`

- [ ] **Step 1: 更新用法说明**

将行 8 替换为：

```
用法：`/coder <spec_path> <plan_path>`
```

- [ ] **Step 2: 更新边界约束**

将行 79-80 替换为：

```
- 从 `review-output/.current-run` 读取 `output_dir`，获取代码输出路径
- 只能修改 `{output_dir}/src/main/java/` 下的 Java 文件和 `{output_dir}/pom.xml`（如需添加依赖）
- 代码输出到 `{output_dir}/src/main/java` 对应包路径下
```

---

### Task 7: 修改测试文件

**Files:**
- Modify: `agents/scheduler/tests/conftest.py`
- Modify: `agents/scheduler/tests/test_models.py`
- Modify: `agents/scheduler/tests/test_engine.py`
- Modify: `agents/scheduler/tests/test_cli.py`

- [ ] **Step 1: 更新 conftest.py**

将 `conftest.py:5-8` 的示例常量替换为：

```python
# 符合 {timestamp}-{project_name} 格式的示例 run_id，供所有测试统一引用
SAMPLE_RUN_ID = "20260624103000-test"
# project_name 为空时的纯时间戳示例 run_id
SAMPLE_RUN_ID_NO_PROJECT = "20260624103000"
```

将 SAMPLE_PIPELINE_YAML 中所有 `{target_dir}` 替换为 `{output_dir}`：
- 行 28: `Output: {output_dir}/src/main/java`
- 行 32: `output_dir: "{output_dir}/src/main/java"`
- 行 40: `Review code at {output_dir}/src/main/java.`
- 行 44: `coder_output: "${coder.outputs.output_dir}"`

将 `sample_pipeline_dict` fixture 中所有 `{target_dir}` 替换为 `{output_dir}`：
- 行 114: `"prompt_template": "Generate: {requirement} to {output_dir}/src/main/java"`
- 行 116: `"outputs": {"output_dir": "{output_dir}/src/main/java"}`
- 行 122: `"prompt_template": "Review {output_dir}/src/main/java. Output: review-output/{run_id}/"`
- 行 123: `"inputs": {"coder_output": "${coder.outputs.output_dir}"}`

- [ ] **Step 2: 更新 test_models.py**

将 `TestPipelineStateTargetDir` 类（行 434-457）替换为 `TestPipelineStateOutputDir`：

```python
class TestPipelineStateOutputDir:
    """PipelineState output_dir / base_path / project_name 字段的测试。"""

    def test_output_dir_defaults_empty(self):
        """新建 PipelineState 时 output_dir 默认值为空字符串"""
        from pipeline_engine.models import PipelineState
        state = PipelineState(pipeline_name="test")
        assert state.output_dir == ""
        assert state.base_path == "."
        assert state.project_name == ""

    def test_start_computes_output_dir(self):
        """start() 根据 base_path 和 project_name 计算 output_dir"""
        from pipeline_engine.models import PipelineState
        state = PipelineState(pipeline_name="test")
        state.start(requirement="test", base_path="workspace", project_name="order-service")
        assert state.output_dir == "workspace/order-service/"
        assert state.base_path == "workspace"
        assert state.project_name == "order-service"

    def test_start_output_dir_trailing_slash_handled(self):
        """start() 处理 base_path 末尾带斜杠的情况"""
        from pipeline_engine.models import PipelineState
        state = PipelineState(pipeline_name="test")
        state.start(requirement="test", base_path="workspace/", project_name="order-service")
        assert state.output_dir == "workspace/order-service/"

    def test_start_no_project_name_falls_back_to_base_path(self):
        """start() 无 project_name 时 output_dir 回退为 base_path"""
        from pipeline_engine.models import PipelineState
        state = PipelineState(pipeline_name="test")
        state.start(requirement="test", base_path="workspace", project_name="")
        assert state.output_dir == "workspace"

    def test_output_dir_roundtrip(self):
        """from_dict / to_dict 往返保持 output_dir 不变"""
        from pipeline_engine.models import PipelineState
        state = PipelineState(pipeline_name="test", base_path="modules",
                              project_name="admin-test",
                              output_dir="modules/admin-test/")
        data = state.to_dict()
        assert data["output_dir"] == "modules/admin-test/"
        assert data["base_path"] == "modules"
        assert data["project_name"] == "admin-test"
        restored = PipelineState.from_dict(data)
        assert restored.output_dir == "modules/admin-test/"
        assert restored.base_path == "modules"
        assert restored.project_name == "admin-test"

    def test_from_dict_missing_fields_defaults(self):
        """from_dict 缺少新字段时回退为默认值"""
        from pipeline_engine.models import PipelineState
        data = {"pipeline_name": "test"}
        state = PipelineState.from_dict(data)
        assert state.base_path == "."
        assert state.project_name == ""
        assert state.output_dir == ""
```

- [ ] **Step 3: 更新 test_engine.py**

将 `test_coder_prompt_contains_target_dir`（行 161-173）替换为：

```python
    def test_coder_prompt_contains_output_dir(self, sample_pipeline_path, state_path):
        """coder prompt 中包含自定义 output_dir"""
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test", base_path="workspace", project_name="admin-test")
        action = engine.next()
        assert action.nodes[0].node_id == "coder"
        assert "workspace/admin-test/src/main/java" in action.nodes[0].prompt
```

将 `test_reviewer_prompt_contains_target_dir`（行 175-190）替换为：

```python
    def test_reviewer_prompt_contains_output_dir(self, sample_pipeline_path, state_path):
        """reviewer prompt 中包含自定义 output_dir"""
        from pipeline_engine.config import load_pipeline
        from pipeline_engine.engine import PipelineEngine
        from pipeline_engine.models import NodeStatus
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test", base_path="modules", project_name="user")
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()  # reviewer
        assert action.nodes[0].node_id == "reviewer"
        assert "modules/user/src/main/java" in action.nodes[0].prompt
```

- [ ] **Step 4: 更新 test_cli.py**

将 `_make_minimal_pipeline` 中的 prompt_template 从 `{target_dir}` 改为 `{output_dir}`（行 42）：

```python
    prompt_template: "Generate: {requirement} to {output_dir}/src/main/java"
```

将 `test_start_stores_target_dir_in_state`（行 118-132）替换为：

```python
    def test_start_stores_base_path_and_project_name_in_state(self, tmp_path):
        """start --base-path --project-name 将值写入状态文件"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
            "--base-path", "workspace",
            "--project-name", "admin-test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data.get("base_path") == "workspace"
        assert data.get("project_name") == "admin-test"
        assert data.get("output_dir") == "workspace/admin-test/"
```

将 `test_start_defaults_target_dir_to_dot`（行 134-147）替换为：

```python
    def test_start_rejects_empty_project_name(self, tmp_path):
        """start 不传 --project-name 时报错"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode != 0
```

将 `test_next_prompt_contains_target_dir`（行 170-182）替换为：

```python
    def test_next_prompt_contains_output_dir(self, tmp_path):
        """next 返回的 prompt 中包含自定义 output_dir"""
        import json
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test",
                 "--base-path", "modules",
                 "--project-name", "custom-module"], cwd=tmp_path)
        result = run_cli(["next", "--state-file", str(state_file),
                          "--pipeline", str(pipeline_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "modules/custom-module/src/main/java" in data["nodes"][0]["prompt"]
```

- [ ] **Step 5: 运行全部测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v 2>&1
```

Expected: 所有测试 PASS。

---

### Task 8: 修改 README.md — 文档同步

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 替换所有 `{target_dir}` → `{output_dir}`**

```bash
# 在项目根目录执行
grep -n "target.dir\|target-dir" README.md
```

逐一检查行 344, 564, 610, 634 等，将 `target_dir` / `--target-dir` 替换为新的参数说明，确保示例命令和描述与新的 `--base-path` + `--project-name` 一致。

---

### Task 9: 最终验证

- [ ] **Step 1: 运行完整测试套件**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v 2>&1
```

Expected: 全部 PASS。

- [ ] **Step 2: 验证 CLI start 端到端**

```bash
cd /Users/chenyi/ai-project/spark

PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-pipeline-state.json \
  --base-path "./workspace" \
  --project-name "test-project" \
  --requirement "test"
```

Expected: 输出包含 `"output_dir": "workspace/test-project/"` 和正确的 `run_id`（格式 `YYYYMMDDHHmmss-test-project`）。

- [ ] **Step 3: 验证 CLI start 拒绝空 project_name**

```bash
PYTHONPATH="${PWD}/agents/scheduler:${PWD}/agents/reviewer/check_system" \
python3 -m pipeline_engine.cli start \
  --pipeline agents/scheduler/pipeline.yaml \
  --state-file /tmp/test-pipeline-state2.json \
  --requirement "test"
```

Expected: 非零退出码（project_name 必填校验生效）。

- [ ] **Step 4: commit**

```bash
git add -A
git commit -m "feat: 项目目录管理改进 — base_path + project_name 两级结构

- models.py: target_dir → base_path + project_name + output_dir
- engine.py: start() 签名和 _render_prompt() 变量更新
- cli.py: --target-dir → --base-path + --project-name，必填校验
- pipeline.yaml: defaults 新增字段，prompt_template 变量替换
- build.skill.md: 交互流程强制 project_name，.current-run 内容更新
- coder.skill.md: 边界约束引用 .current-run
- 所有测试同步更新

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
