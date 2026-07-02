# DAG 流水线项目目录管理改进 — 设计文档

## 概述

将当前单一的 `--target-dir` 参数拆分为「项目存放位置（base_path）+ 项目名称（project_name）→ 拼接输出目录」的两级结构，更好地管理多项目、多轮基准测试场景。

### 背景

当前 `/build` 流水线只有一个 `--target-dir` 参数（默认 `.`），所有产出（代码、审查结果）都散落在项目根目录或单个 target_dir 下。对于基准测试场景（同一需求在多配置下多次运行），无法方便地按项目分组、跨运行对比、一键收集数据。

### 目标

- 支持 `{base_path}/{project_name}/` 的层级目录结构
- 审查数据与代码分离，集中在 `{base_path}/review-output/{project_name}/{run_id}/` 下
- `project_name` 为必填项，保证每个项目有明确标识
- 兼容交互式和命令行两种使用方式

---

## 路径公式

```
output_dir  = {base_path}/{project_name}/
code_dir    = {output_dir}/src/main/java/
review_dir  = {base_path}/review-output/{project_name}/{run_id}/
run_id      = YYYYMMDDHHmmss-{project_name}
```

### 目录布局示例

```
workspace/                                    # base_path
├── order-service/                            # project_name
│   ├── src/main/java/                        # 生成的代码
│   │   └── com/example/order/
│   ├── src/main/resources/
│   └── pom.xml
│
├── review-output/
│   └── order-service/
│       ├── 20260702120000-order-service/      # run 1
│       │   ├── pipeline-state.json
│       │   ├── quality.json
│       │   ├── findings.json
│       │   └── final-review-report.md
│       └── 20260702150000-order-service/      # run 2（A/B 对比）
│           └── ...
│
└── user-service/                              # 另一个项目
    └── ...
```

---

## 配置变更

### pipeline.yaml defaults

```yaml
defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]
  base_path: "."           # 新增：项目存放位置，默认当前目录
  project_name: ""         # 新增：项目名称，空则必须交互输入
```

### PipelineState 字段变更

```python
# 旧（移除）
target_dir: str = "."

# 新（新增）
base_path: str = "."
project_name: str = ""
output_dir: str = ""    # 拼接结果：{base_path}/{project_name}/
```

### .current-run 内容变更

```json
{
  "run_id": "20260702120000-order-service",
  "base_path": "./workspace",
  "project_name": "order-service",
  "output_dir": "./workspace/order-service/",
  "scan_path": "./workspace/order-service/src/main/java",
  "review_dir": "./workspace/review-output/order-service/20260702120000-order-service/"
}
```

---

## 命令行参数

```bash
/build "需求描述"
  --base-path ./workspace       # 可选，覆盖 pipeline.yaml 的 base_path
  --project-name order-service   # 可选，手动指定项目名
```

### 交互流程

```
/build "做个订单服务"
  │
  ├── 解析命令行参数（--base-path, --project-name）
  │
  ├── base_path: 命令行 > pipeline.yaml defaults.base_path（默认 "."）
  │
  ├── project_name: 命令行有 → 使用
  │    没有 → 必问：「请输入项目名称：」
  │    用户输入为空 → 再次询问，不允许跳过
  │
  └── 展示确认：
      「确认：
        - 项目位置：./workspace/
        - 项目名称：order-service
        - 代码输出：./workspace/order-service/src/main/java/
        - 审查数据：./workspace/review-output/order-service/
        
        是否继续？」
      
      用户确认 → 进入 PM 需求对话
      用户否定 → 重新输入参数
```

---

## 变更文件清单

| # | 文件 | 变更内容 |
|---|------|---------|
| 1 | `agents/scheduler/pipeline.yaml` | defaults 新增 `base_path`、`project_name`；prompt_template 中 `{target_dir}` → `{output_dir}` |
| 2 | `agents/scheduler/pipeline_engine/models.py` | `_generate_run_id` 参数从 `target_dir` 改为 `project_name`；`PipelineState` 字段从 `target_dir` 改为 `base_path` + `project_name` + `output_dir` |
| 3 | `agents/scheduler/pipeline_engine/engine.py` | `start()` 参数从 `target_dir` 改为 `output_dir`；`_render_prompt()` 变量字典 `target_dir` → `output_dir` |
| 4 | `agents/scheduler/pipeline_engine/cli.py` | `cmd_start` 参数 `--target-dir` 改为 `--base-path` + `--project-name`，拼接后传入 engine；`code-check-config.yaml` 写入字段更新 |
| 5 | `agents/scheduler/build.skill.md` | 参数解析从 `--target-dir` 改为 `--base-path` + `--project-name`；新增交互流程（project_name 必填）；`.current-run` 内容更新 |
| 6 | `agents/coder/coder.skill.md` | 行 8 用法说明、行 79-80 边界约束，从 `{target_dir}` 改为引用 `.current-run` 的 `output_dir` |
| 7 | `agents/scheduler/tests/conftest.py` | fixture 中 `target_dir` → `output_dir` |
| 8 | `agents/scheduler/tests/test_models.py` | `target_dir` 相关测试改为 `output_dir` |
| 9 | `agents/scheduler/tests/test_engine.py` | `target_dir` 相关测试改为 `output_dir` |
| 10 | `agents/scheduler/tests/test_cli.py` | CLI 测试参数 `--target-dir` → `--base-path` + `--project-name` |
| 11 | `README.md` | 文档中 `target_dir` / `--target-dir` 描述同步更新 |

### 不需要变更的文件

以下文件从 `code-check-config.yaml` 读取路径，而 `cli.py` 会继续往该 config 写入正确的值，因此无需修改：

- `agents/reviewer/hooks/review-pre-hook.sh`
- `agents/reviewer/hooks/review-post-hook.sh`
- `agents/reviewer/check_system/code_check/reporter.py`
- `benchmarks/hooks/dump-agent-payload.sh`
- `benchmarks/hooks/synthesize-benchmark.sh`
- `benchmarks/hooks/schema.py`
- `CLAUDE.md`
- `.gitignore`

---

## run_id 生成规则

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

---

## 功能范围

### 包含

- `base_path` + `project_name` 两级目录拼接
- review-output 集中到 `{base_path}/review-output/{project_name}/{run_id}/`
- `project_name` 交互式必填
- 命令行 `--base-path` 和 `--project-name` 参数
- run_id 使用 `project_name` 作为后缀
- `.current-run` 透出全部路径字段

### 不包含

- 三级以上目录层级（如 `{group}/{project}`）
- 从外部配置文件（非 pipeline.yaml）读取 base_path
- 自动创建 base_path 目录
- 项目删除/清理功能
- 已有 `review-output/` 数据的自动迁移
