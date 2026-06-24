# /build 自定义代码输出目录 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许 `/build <需求> --target-dir <模块目录>` 指定 coder 的输出模块根目录，替代硬编码的 `src/main/java`

**Architecture:** 在 `PipelineState` 中新增 `target_dir` 字段，通过 CLI → Engine → prompt template 的数据流将自定义目录传递到 coder/reviewer 的 prompt 中。同步更新 `code-check-config.yaml` 和 hook 脚本中的硬编码路径，统一使用 `{run_id}` 子目录。

**Tech Stack:** Python 3 (dataclasses, argparse, PyYAML), Bash, YAML

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|---------|
| `agents/scheduler/pipeline_engine/models.py` | 数据模型：`PipelineState.target_dir` 字段 | 修改 |
| `agents/scheduler/pipeline_engine/cli.py` | CLI：`start --target-dir` + 更新 code-check-config.yaml | 修改 |
| `agents/scheduler/pipeline_engine/engine.py` | 引擎：`{target_dir}` 变量 + `{run_id}` 修复路径 | 修改 |
| `agents/scheduler/pipeline.yaml` | 流水线配置：替换硬编码路径 | 修改 |
| `agents/scheduler/build.skill.md` | /build 入口：Phase 0 交互 + 终止条件 | 修改 |
| `agents/reviewer/hooks/review-post-hook.sh` | Post-hook：读取 config 替代硬编码 run_id | 修改 |
| `agents/reviewer/review.skill.md` | /review 技能：产物路径加入 `{run_id}` | 修改 |
| `agents/reviewer/check_system/rules/review-prompt.md` | AI 检查清单：路径加入 `{run_id}` | 修改 |
| `agents/scheduler/tests/test_models.py` | 模型测试：target_dir 往返 | 修改 |
| `agents/scheduler/tests/test_engine.py` | 引擎测试：{target_dir} 渲染 | 修改 |
| `agents/scheduler/tests/test_cli.py` | CLI 测试：--target-dir 参数 | 修改 |
| `agents/scheduler/tests/conftest.py` | 测试夹具：pipeline YAML 适配新字段 | 修改 |

---

### Task 1: `PipelineState` 新增 `target_dir` 字段

**Files:**
- Modify: `agents/scheduler/pipeline_engine/models.py:286-370`

- [ ] **Step 1: 在 `PipelineState` dataclass 中添加 `target_dir` 字段**

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
    target_dir: str = "."   # 新增：模块根目录，相对于项目根
```

- [ ] **Step 2: 更新 `from_dict()` 读取 `target_dir`**

在 `from_dict()` 的 `return cls(...)` 调用中添加：

```python
target_dir=d.get("target_dir", "."),
```

位置在 `run_id=d.get("run_id", ""),` 之后。

- [ ] **Step 3: 更新 `to_dict()` 输出 `target_dir`**

在 `to_dict()` 返回的 dict 中添加：

```python
"target_dir": self.target_dir,
```

位置在 `"run_id": self.run_id,` 之后。

- [ ] **Step 4: 运行已有测试确认未破坏现有功能**

```bash
cd agents/scheduler && python3 -m pytest tests/test_models.py -v -k "PipelineState"
```

Expected: 所有已有 PipelineState 测试 PASS。

- [ ] **Step 5: 提交**

```bash
git add agents/scheduler/pipeline_engine/models.py
git commit -m "feat: PipelineState 新增 target_dir 字段，默认值 '.'"
```

---

### Task 2: CLI `start` 新增 `--target-dir` 参数

**Files:**
- Modify: `agents/scheduler/pipeline_engine/cli.py:180-222`

- [ ] **Step 1: 在 `p_start` 中添加 `--target-dir` 参数**

在 `p_start` 的参数定义（约第 192 行附近）中添加：

```python
p_start.add_argument("--target-dir", default=".",
                     help="模块根目录（相对于项目根）")
```

- [ ] **Step 2: 在 `cmd_start()` 中设置 `target_dir` 并更新 `code-check-config.yaml`**

将 `cmd_start()` 中生成 run_id 后的代码（约第 71-83 行）修改为：

```python
    # 生成 run_id 并存入状态
    run_id = _generate_run_id(Path("review-output"))
    state.run_id = run_id
    state.target_dir = args.target_dir
    engine._save_state()

    # 同步更新 code-check-config.yaml，确保 reviewer 的扫描路径和输出目录正确
    import yaml as _yaml
    _config_path = Path("agents/reviewer/check_system/code-check-config.yaml")
    if _config_path.exists():
        with open(_config_path, "r") as f:
            _cfg = _yaml.safe_load(f) or {}
        _cfg["default_scan_path"] = f"../../../{state.target_dir}/src/main/java"
        _cfg["output_dir"] = f"../../../review-output/{state.run_id}/"
        with open(_config_path, "w") as f:
            _yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)

    print(json.dumps({
        "status": "started",
        "pipeline_name": state.pipeline_name,
        "round": 0,
        "run_id": run_id,
        "target_dir": state.target_dir,
        "max_retries": config.defaults.max_retries,
        "message": f"流水线 '{config.name}' 已启动。",
    }))
```

- [ ] **Step 3: 运行 CLI 测试**

```bash
cd agents/scheduler && python3 -m pytest tests/test_cli.py -v
```

Expected: 所有已有 CLI 测试 PASS。

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/pipeline_engine/cli.py
git commit -m "feat: CLI start 新增 --target-dir 参数，同步更新 code-check-config.yaml"
```

---

### Task 3: Engine `_render_prompt` 新增 `{target_dir}` 变量 + 修复路径 `{run_id}`

**Files:**
- Modify: `agents/scheduler/pipeline_engine/engine.py:292-346`

- [ ] **Step 1: 在 `_render_prompt` 的 variables dict 中添加 `target_dir`**

在 `variables` dict（约第 327-333 行）中添加：

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

- [ ] **Step 2: 修复 review_context 中的路径，加入 `{run_id}` 子目录**

将 review_context 中的三行路径（约第 316-318 行）修改为使用 `{run_id}`：

```python
            review_context = (
                "\n\n⚠️ 这是第 {round}/{max_retries} 轮修复。\n\n"
                "请先读取以下文件，了解上一轮审查发现的问题：\n"
                "1. review-output/{run_id}/pre-check-result.json — 程序预检结果\n"
                "2. review-output/{run_id}/review-result.json — AI 语义检查结果（如存在）\n"
                "3. review-output/{run_id}/pre-check-report.md — 预检报告\n\n"
                "然后逐个修复所有阻断级问题。\n\n"
                "修复原则：\n"
                "- 只修改有问题的文件和行\n"
                "- 修复后必须符合 agents/coder/ 下的所有规范\n"
                "- 不确定的改动，加注释说明原因"
            ).format(round=self.state.round,
                     max_retries=self.config.defaults.max_retries,
                     run_id=self.state.run_id)
```

注意：原来 `.format()` 调用只有 `round` 和 `max_retries` 两个参数，现在新增 `run_id=self.state.run_id`。

- [ ] **Step 3: 运行引擎测试**

```bash
cd agents/scheduler && python3 -m pytest tests/test_engine.py -v
```

Expected: 所有已有引擎测试 PASS。如果 `test_prompt_contains_run_id` 测试因 review_context 路径变化而失败，需要更新其断言。

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/pipeline_engine/engine.py
git commit -m "feat: engine 新增 {target_dir} 变量，修复轮次路径加入 {run_id} 子目录"
```

---

### Task 4: `pipeline.yaml` 替换所有硬编码路径

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 替换 coder prompt_template 中的三处 `src/main/java`**

将 coder 的 `prompt_template` 中所有 `src/main/java` 替换为 `{target_dir}/src/main/java`：

```yaml
    prompt_template: |
      你需要根据用户需求生成 Java 代码。

      用户需求：
      {requirement}

      你必须遵守以下规范（读取 agents/coder/README.md 获取完整索引）：
      - 包结构：controller → service/impl → mapper → entity/dto/vo
      - 返回值：统一 Result<T>
      - 注入：构造注入 @RequiredArgsConstructor，不用 @Autowired 字段注入
      - 日志：@Slf4j，不打敏感信息
      - 异常：抛 BusinessException，不写自由文本
      - SQL：简单查 LambdaQueryWrapper，复杂/联表/子查询走 XML，禁用 @Select
      - 参数：>3 个收敛到 DTO
      - URL：RESTful 复数名词，CRUD 不用动词

      {review_context}

      ⚠️ 边界约束：你只能修改 {target_dir}/src/main/java/ 目录下的 Java 文件和 {target_dir}/pom.xml（如需添加依赖）。禁止修改 agents/ 或 hooks/ 目录下的任何文件。这些是审查系统的规则和配置，修改它们会导致流水线结果不可信。

      代码输出目录：{target_dir}/src/main/java
      将生成的 Java 代码写入 {target_dir}/src/main/java 对应包路径下。
```

- [ ] **Step 2: 替换 coder outputs 中的 `target_dir`**

```yaml
    outputs:
      - target_dir: "{target_dir}/src/main/java"
```

- [ ] **Step 3: 替换 reviewer prompt_template 中的 `src/main/java`**

```yaml
      1. 调用 Skill 工具执行 review：使用 skill="review", args="{target_dir}/src/main/java"
```

- [ ] **Step 4: 替换 reviewer outputs 中的路径，加入 `{run_id}`**

```yaml
    outputs:
      - pre_check: "review-output/{run_id}/pre-check-result.json"
      - ai_review: "review-output/{run_id}/review-result.json"
      - final_report: "review-output/{run_id}/final-review-report.md"
```

- [ ] **Step 5: 更新 coder inputs 中的 review_context 描述**

```yaml
    inputs:
      - requirement: "${user_input}"
      - review_context: "review-output/{run_id}/ 目录下的审查结果（仅修复轮次时存在）"
```

- [ ] **Step 6: 运行调度器测试确保 pipeline.yaml 仍可解析**

```bash
cd agents/scheduler && python3 -m pytest tests/test_config.py tests/test_engine.py -v
```

Expected: 所有配置解析和引擎测试 PASS。

- [ ] **Step 7: 提交**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "refactor: pipeline.yaml 用 {target_dir} 和 {run_id} 替换所有硬编码路径"
```

---

### Task 5: `build.skill.md` Phase 0 交互 + 终止条件

**Files:**
- Modify: `agents/scheduler/build.skill.md`

- [ ] **Step 1: 更新 Phase 0 流程，加入 `--target-dir` 解析和交互询问**

在 Phase 0 的步骤 2 中更新 `start` 命令调用方式。将当前第 22-29 行替换为：

```markdown
2. 解析用户输入中的 `--target-dir` 参数：
   - 如果用户指定了 `--target-dir <值>`，直接使用该值
   - 如果未指定，询问用户一次：
     「是否需要自定义代码输出目录？（当前默认: 项目根目录 src/main/java）
       输入模块目录名或直接回车跳过：」
     ├─ 用户输入了目录 → 使用该目录
     └─ 用户直接回车/说"不"/"否" → 使用默认值 "."
3. 调用：
   ```bash
   python3 -m pipeline_engine.cli start \
     --pipeline agents/scheduler/pipeline.yaml \
     --state-file review-output/pipeline-state.json \
     --target-dir "<目标目录>" \
     --requirement "{用户需求}"
   ```
4. 向用户报告启动信息（pipeline 名称、目标目录、max_retries 等）
```

- [ ] **Step 2: 更新终止条件中的最终报告路径**

将第 66 行：

```
- `next` 返回 `action=="done"` → 读取 `review-output/final-review-report.md` 展示结果
```

改为：

```
- `next` 返回 `action=="done"` → 从 `start` 命令返回的 `run_id` 构造路径，读取 `review-output/{run_id}/final-review-report.md` 展示结果
```

- [ ] **Step 3: 更新 Phase 1 中 `next` 和 `report` 命令的 `--pipeline` 参数路径**

确认 Phase 1 循环中的所有 CLI 调用都使用正确的 `--pipeline` 路径（应为 `agents/scheduler/pipeline.yaml`）。

- [ ] **Step 4: 提交**

```bash
git add agents/scheduler/build.skill.md
git commit -m "feat: build.skill.md 新增 --target-dir 解析和交互询问，更新终止条件路径"
```

---

### Task 6: `review-post-hook.sh` 去除硬编码 run_id

**Files:**
- Modify: `agents/reviewer/hooks/review-post-hook.sh:1-48`

- [ ] **Step 1: 添加 CHECK_SYSTEM_DIR 变量，从 config 读取 output_dir**

在 `SCRIPT_DIR` 和 `PROJECT_DIR` 定义之后添加：

```bash
CHECK_SYSTEM_DIR="$PROJECT_DIR/agents/reviewer/check_system"
```

- [ ] **Step 2: 替换硬编码的默认路径**

将当前第 12-14 行：

```bash
PRE_CHECK_JSON="${1:-$PROJECT_DIR/review-output/20260624035444-001/pre-check-result.json}"
AI_CHECK_JSON="${2:-$PROJECT_DIR/review-output/20260624035444-001/review-result.json}"
OUTPUT_MD="${3:-$PROJECT_DIR/review-output/20260624035444-001/final-review-report.md}"
```

替换为：

```bash
# 从 code-check-config.yaml 读取 output_dir
OUTPUT_DIR=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CHECK_SYSTEM_DIR/code-check-config.yaml")

PRE_CHECK_JSON="${1:-$PROJECT_DIR/$OUTPUT_DIR/pre-check-result.json}"
AI_CHECK_JSON="${2:-$PROJECT_DIR/$OUTPUT_DIR/review-result.json}"
OUTPUT_MD="${3:-$PROJECT_DIR/$OUTPUT_DIR/final-review-report.md}"
```

注意：`OUTPUT_DIR` 是相对于项目根目录的路径（如 `../../../review-output/20260624120000-001`），需要解析为绝对路径。因此路径拼接时需要先计算 output_dir 的实际绝对路径。

实际上，`OUTPUT_DIR` 从 config 读出来是 `../../../review-output/<run_id>/`，这个路径是相对于 `CHECK_SYSTEM_DIR` 的。`$PROJECT_DIR/$OUTPUT_DIR` 拼出来会是 `$PROJECT_DIR/../../../review-output/<run_id>/`。需要调整为使用正确的路径解析。

修正方案：因为 `OUTPUT_DIR` 的值如 `../../../review-output/20260624120000-001/` 是相对于 `CHECK_SYSTEM_DIR` 的，所以应该基于 `CHECK_SYSTEM_DIR` 来解析。

```bash
# 从 code-check-config.yaml 读取 output_dir（相对于 check_system 目录）
OUTPUT_DIR_REL=$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        c = yaml.safe_load(f)
    print(c.get('output_dir', '../../../review-output'))
except Exception:
    print('../../../review-output')
" "$CHECK_SYSTEM_DIR/code-check-config.yaml")

# 解析为绝对路径
OUTPUT_DIR_ABS="$(cd "$CHECK_SYSTEM_DIR/$OUTPUT_DIR_REL" 2>/dev/null && pwd || echo "$PROJECT_DIR/review-output")"

PRE_CHECK_JSON="${1:-$OUTPUT_DIR_ABS/pre-check-result.json}"
AI_CHECK_JSON="${2:-$OUTPUT_DIR_ABS/review-result.json}"
OUTPUT_MD="${3:-$OUTPUT_DIR_ABS/final-review-report.md}"
```

- [ ] **Step 3: 提交**

```bash
git add agents/reviewer/hooks/review-post-hook.sh
git commit -m "fix: review-post-hook.sh 去除硬编码 run_id，改为从 config 读取 output_dir"
```

---

### Task 7: `review.skill.md` 产物路径加入 `{run_id}`

**Files:**
- Modify: `agents/reviewer/review.skill.md`

- [ ] **Step 1: 替换所有 `../../../review-output/` 为 `../../../review-output/{run_id}/`**

注意：`review.skill.md` 是 Claude Code skill 文件，其中 `{run_id}` 是文档占位符，不是模板变量。reviewer agent 收到 pipeline prompt 中 `review-output/{run_id}/` 的具体值后，执行时会自行替换。

逐个替换以下行：

| 行 | 旧值 | 新值 |
|----|------|------|
| 22 | `../../../review-output/pre-check-result.json` 已生成 | `../../../review-output/{run_id}/pre-check-result.json` 已生成 |
| 23 | `../../../review-output/pre-check-result.json` + `../../../review-output/pre-check-report.md` 已生成 | `../../../review-output/{run_id}/pre-check-result.json` + `../../../review-output/{run_id}/pre-check-report.md` 已生成 |
| 27 | `../../../review-output/`。 | `../../../review-output/{run_id}/`。 |
| 33 | `../../../review-output/pre-check-result.json` | `../../../review-output/{run_id}/pre-check-result.json` |
| 36 | `../../../review-output/review-result.json` | `../../../review-output/{run_id}/review-result.json` |
| 44 | `../../../review-output/final-review-report.md` | `../../../review-output/{run_id}/final-review-report.md` |

- [ ] **Step 2: 提交**

```bash
git add agents/reviewer/review.skill.md
git commit -m "docs: review.skill.md 产物路径加入 {run_id} 子目录"
```

---

### Task 8: `review-prompt.md` AI 检查清单路径加入 `{run_id}`

**Files:**
- Modify: `agents/reviewer/check_system/rules/review-prompt.md`

- [ ] **Step 1: 替换三处 `review-output/` 为 `review-output/{run_id}/`**

| 行 | 旧值 | 新值 |
|----|------|------|
| 3 | `review-output/pre-check-result.json` | `review-output/{run_id}/pre-check-result.json` |
| 12 | `review-output/pre-check-result.json` | `review-output/{run_id}/pre-check-result.json` |
| 51 | `review-output/review-result.json` | `review-output/{run_id}/review-result.json` |

- [ ] **Step 2: 提交**

```bash
git add agents/reviewer/check_system/rules/review-prompt.md
git commit -m "docs: review-prompt.md AI 检查清单路径加入 {run_id} 子目录"
```

---

### Task 9: 测试更新

**Files:**
- Modify: `agents/scheduler/tests/conftest.py`
- Modify: `agents/scheduler/tests/test_models.py`
- Modify: `agents/scheduler/tests/test_engine.py`
- Modify: `agents/scheduler/tests/test_cli.py`

- [ ] **Step 1: 更新 `conftest.py` 中的 `SAMPLE_PIPELINE_YAML` 和 `sample_pipeline_dict`**

将 fixtures 中的 prompt_template 加入 `{target_dir}`，同时更新 outputs 路径加入 `{run_id}`。

`SAMPLE_PIPELINE_YAML` 中 coder prompt_template 增加 `{target_dir}` 行（约第 21-22 行）：

```yaml
    prompt_template: |
      Generate code for: {requirement}
      Output: {target_dir}/src/main/java
      {review_context}
```

`SAMPLE_PIPELINE_YAML` 中 reviewer prompt_template（约第 33-36 行）替换对 `{run_id}` 的引用：

```yaml
    prompt_template: |
      Review code at {target_dir}/src/main/java.
      Output directory: review-output/{run_id}/
      Return REVIEW_PASSED, REVIEW_FAILED, or REVIEW_ERROR.
```

`SAMPLE_PIPELINE_YAML` 中 outputs 更新（约第 26、40 行）：

```yaml
      target_dir: "{target_dir}/src/main/java"
```
```yaml
      final_report: "review-output/{run_id}/final-review-report.md"
```

`sample_pipeline_dict` 中对应的 prompt_template 和 outputs 同步更新：

```python
"prompt_template": "Generate: {requirement} to {target_dir}/src/main/java",
```
```python
"outputs": {"target_dir": "{target_dir}/src/main/java"},
```
```python
"prompt_template": "Review {target_dir}/src/main/java. Output: review-output/{run_id}/",
```
```python
"outputs": {"final_report": "review-output/{run_id}/final-review-report.md"},
```

同时更新 `test_cli.py` 中 `_make_minimal_pipeline` 的 coder prompt_template 加入 `{target_dir}`（约第 42 行）：

```python
    prompt_template: "Generate: {requirement} to {target_dir}/src/main/java"
```

- [ ] **Step 2: 添加模型测试 — `test_models.py`**

在 `test_models.py` 中添加三个新测试：

```python
class TestPipelineStateTargetDir:
    def test_target_dir_defaults_to_dot(self):
        """新建 PipelineState 时 target_dir 默认值为 '.'"""
        state = PipelineState(pipeline_name="test")
        assert state.target_dir == "."

    def test_target_dir_roundtrip(self):
        """from_dict / to_dict 往返保持 target_dir 不变"""
        state = PipelineState(pipeline_name="test", target_dir="admin-test")
        data = state.to_dict()
        assert data["target_dir"] == "admin-test"
        restored = PipelineState.from_dict(data)
        assert restored.target_dir == "admin-test"

    def test_target_dir_missing_defaults_to_dot(self):
        """from_dict 缺少 target_dir 时回退为 '.'"""
        data = {"pipeline_name": "test"}
        state = PipelineState.from_dict(data)
        assert state.target_dir == "."
```

- [ ] **Step 3: 添加引擎测试 — `test_engine.py`**

在 `TestPipelineEngineNext` class 中添加 `{target_dir}` 渲染测试：

```python
    def test_coder_prompt_contains_target_dir(self, sample_pipeline_path: Path, state_path: Path):
        """coder prompt 中包含自定义 target_dir"""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine._ensure_state()
        engine.state.target_dir = "admin-test"
        engine._save_state()
        action = engine.next()
        assert action.nodes[0].node_id == "coder"
        assert "admin-test/src/main/java" in action.nodes[0].prompt

    def test_reviewer_prompt_contains_target_dir(self, sample_pipeline_path: Path, state_path: Path):
        """reviewer prompt 中包含自定义 target_dir"""
        config = load_pipeline(sample_pipeline_path)
        engine = PipelineEngine(config, state_path)
        engine.start("test")
        engine._ensure_state()
        engine.state.target_dir = "modules/user"
        engine._save_state()
        engine.next()  # coder
        engine.report("coder", NodeStatus.SUCCESS, "ok")
        action = engine.next()  # reviewer
        assert action.nodes[0].node_id == "reviewer"
        assert "modules/user/src/main/java" in action.nodes[0].prompt
```

- [ ] **Step 4: 添加 CLI 测试 — `test_cli.py`**

在 `TestCLIStart` class 中添加 `--target-dir` 测试：

```python
    def test_start_stores_target_dir_in_state(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
            "--target-dir", "admin-test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data.get("target_dir") == "admin-test"

    def test_start_defaults_target_dir_to_dot(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        result = run_cli([
            "start",
            "--pipeline", str(pipeline_file),
            "--state-file", str(state_file),
            "--requirement", "test",
        ], cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data.get("target_dir") == "."
```

在 `TestCLINext` class 中添加 prompt 包含 `target_dir` 的测试：

```python
    def test_next_prompt_contains_target_dir(self, tmp_path: Path):
        pipeline_file = _make_minimal_pipeline(tmp_path)
        state_file = tmp_path / "state.json"
        run_cli(["start", "--pipeline", str(pipeline_file),
                 "--state-file", str(state_file), "--requirement", "test",
                 "--target-dir", "custom-module"], cwd=tmp_path)
        result = run_cli(["next", "--state-file", str(state_file),
                          "--pipeline", str(pipeline_file)], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "custom-module/src/main/java" in data["nodes"][0]["prompt"]
```

- [ ] **Step 5: 运行全部测试**

```bash
cd agents/scheduler && python3 -m pytest tests/ -v
```

Expected: 全部测试 PASS。

- [ ] **Step 6: 提交**

```bash
git add agents/scheduler/tests/
git commit -m "test: 新增 target_dir 相关测试，更新 fixtures 适配新字段"
```

---

### 执行顺序

Tasks 应按数字顺序执行（1→9），因为每个 Task 依赖前一个 Task 的定义：

```
Task 1 (models.target_dir)
  → Task 2 (cli --target-dir)
    → Task 3 (engine {target_dir})
      → Task 4 (pipeline.yaml 模板)
        → Task 5 (build.skill.md)
Task 6 (review-post-hook.sh) — 独立
Task 7 (review.skill.md) — 独立
Task 8 (review-prompt.md) — 独立
Task 9 (tests) — 依赖 Task 1-4
```

Tasks 6、7、8 可并行执行（它们不互相依赖）。
