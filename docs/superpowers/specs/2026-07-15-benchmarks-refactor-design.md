# 基准测试系统重构

> **状态:** 已确认 | **日期:** 2026-07-15

## 目标

对 `benchmarks/` 目录下的基准测试系统进行完整重构：
1. 所有业务逻辑迁移到纯 Python 包，消除 Shell/Python 混合带来的逻辑分散和重复
2. 消除硬编码，所有可配置项集中到 `benchmarks/config.yaml`
3. 数据按 `run_id` 组织，JSON 格式存储，默认 7 天保留
4. 新增 `spark:benchmarks` skill 用于手动性能分析

## 背景

当前系统由 4 个文件组成：

| 文件 | 职责 | 问题 |
|------|------|------|
| `hooks/dump-agent-payload.sh` | PostToolUse 采集性能数据 | 硬编码关键词、has_error 截取前 200 字符、Shell 内嵌 Python |
| `hooks/schema.py` | 合成 benchmark JSON + MD | `run_id` NameError 导致 CLI 崩溃、轮次推断靠正则、零测试 |
| `hooks/compare.py` | 跨运行对比报告 | 2σ 异常检测无统计意义、sparkline 终端兼容差、过度工程 |
| `hooks/synthesize-benchmark.sh` | Stop hook 触发合成 | 配置读取重复、session_id 推断不可靠 |

重构策略：**完整重写**，保留运行良好的 hook 开关机制（`.pipeline-active`），其余全部重写。

## 架构

### 数据流

```
/build --resume {run_id}
  │
  ├─ touch .pipeline-active                        ← 激活 hook
  │
  ├─ pipeline_engine next → 启动 Agent
  │     │
  │     └─ Agent 完成 → PostToolUse Hook 触发
  │           └─ dump-agent-payload.sh
  │                 └─ 追加 → benchmarks/dumps/{run_id}.jsonl        ← 原始性能数据
  │
  ├─ pipeline_engine report
  │     └─ 追加 → benchmarks/{run_id}/pipeline-log.jsonl             ← 结构化轮次数据
  │
  └─ 流水线结束 → Stop Hook 触发
        └─ python3 -m benchmark_lib.cli synthesize {run_id}
              ├─ 读 dumps/{run_id}.jsonl + {run_id}/pipeline-log.jsonl
              ├─ 合成 → benchmarks/{run_id}/benchmark.json
              ├─ 渲染 → benchmarks/{run_id}/report.md
              └─ 清理 7 天前数据
```

### 职责分离

| 层 | 组件 | 职责 |
|----|------|------|
| 采集层 | `hooks/dump-agent-payload.sh` | 极薄 Shell：读取 `.current-run` 获取 run_id，追加完整 payload 到 JSONL。不下发任何业务判断。 |
| 结构层 | `pipeline_engine report` | 写入 `pipeline-log.jsonl`，提供轮次、节点、verdict 等结构化信息。 |
| 合成层 | `benchmark_lib/synthesize.py` | 合并两路数据，生成 `benchmark.json`。 |
| 渲染层 | `benchmark_lib/report.py` | 从 JSON 渲染人类可读 Markdown。 |
| 清理层 | `benchmark_lib/cleanup.py` | 按 `config.yaml` 的保留天数清理过期数据。 |
| 分析层 | `.claude/skills/spark-benchmarks.skill.md` | 手动调用的性能分析 Skill，AI 读取 benchmark.json 做分析。 |

## 目录结构

```
benchmarks/
├── config.yaml                        # 统一配置
├── hooks/
│   └── dump-agent-payload.sh          # 极薄数据采集 hook
├── dumps/
│   └── {run_id}.jsonl                 # hook 采集的原始性能数据
├── {run_id}/                          # 按 run_id 组织所有产物
│   ├── pipeline-log.jsonl             # pipeline_engine report 写入的结构化日志
│   ├── benchmark.json                 # 合成结果（符合 JSON Schema）
│   └── report.md                      # 人类可读 Markdown 报告
└── benchmark_lib/                     # Python 纯逻辑包
    ├── __init__.py
    ├── config.py                      # 配置加载
    ├── models.py                      # 数据模型 + JSON Schema 定义
    ├── synthesize.py                  # 合成引擎
    ├── report.py                      # Markdown 报告渲染
    ├── cleanup.py                     # 数据清理
    └── cli.py                         # 统一 CLI 入口
```

旧文件（`schema.py`、`compare.py`、`synthesize-benchmark.sh`）在重构完成后删除。

## 配置文件: `benchmarks/config.yaml`

```yaml
# 数据保留
retention:
  max_days: 7

# 数据目录
paths:
  dumps_dir: benchmarks/dumps           # 相对于项目根目录
  output_dir: benchmarks                 # 合成结果输出基目录

# pipeline-log 文件路径模板（相对于 output_dir）
pipeline_log_template: "{run_id}/pipeline-log.jsonl"
```

### 配置加载 (`config.py`)

- 从项目根目录向下查找 `benchmarks/config.yaml`
- 加载后以 dataclass 形式暴露，提供默认值
- 全代码零硬编码路径和阈值

## 数据模型: `benchmark_lib/models.py`

### benchmark.json 结构

```json
{
  "schema_version": "2.0",
  "meta": {
    "run_id": "20260715-143000",
    "timestamp_start": "2026-07-15T14:30:00+08:00",
    "timestamp_end": "2026-07-15T14:35:00+08:00",
    "git_commit": "a1b2c3d",
    "max_retries": 3,
    "block_strategy": "strict"
  },
  "rounds": [
    {
      "round": 1,
      "coder": {
        "phase": "generate",
        "duration_ms": 263000,
        "total_tokens": 50200,
        "total_tool_uses": 50,
        "usage": { "input_tokens": 10000, "cache_read_input_tokens": 40000, "output_tokens": 200 }
      },
      "reviewer": {
        "phase": "review",
        "duration_ms": 72000,
        "total_tokens": 30474,
        "total_tool_uses": 13,
        "usage": { "input_tokens": 2030, "cache_read_input_tokens": 28160, "output_tokens": 284 },
        "result": "REVIEW_FAILED",
        "issues": { "P0": 0, "P1": 15, "P2": 19, "AI_FAIL": -1 }
      }
    }
  ],
  "convergence": {
    "rounds_to_converge": 2,
    "termination_reason": "converged",
    "series": [
      { "round": 1, "P0": 0, "P1": 15, "P2": 19, "AI_FAIL": -1 },
      { "round": 2, "P0": 0, "P1": 0, "P2": 10, "AI_FAIL": 5 }
    ]
  },
  "summary": {
    "total_duration_ms": 700000,
    "total_tokens": 200000,
    "total_tool_uses": 150,
    "coder": { "total_tokens": 120000, "total_duration_ms": 500000, "avg_tokens_per_call": 60000 },
    "reviewer": { "total_tokens": 80000, "total_duration_ms": 200000, "avg_tokens_per_call": 40000 },
    "cache_efficiency": {
      "total_cache_read_tokens": 300000,
      "total_input_tokens": 50000,
      "cache_hit_ratio": 0.857
    },
    "converged": true,
    "models_used": { "claude-sonnet-4-6": 4 }
  }
}
```

### JSON Schema 校验

`models.py` 中定义完整的 JSON Schema（基于 draft-07），`cli.py synthesize` 写入 `benchmark.json` 前先校验。
校验失败 → 打印错误详情到 stderr，不写入无效文件。

## Hook 层: `hooks/dump-agent-payload.sh`

### 职责

唯一职责：把 PostToolUse hook 的 stdin payload 追加到 `benchmarks/dumps/{run_id}.jsonl`。

### 逻辑（伪代码）

```bash
#!/bin/bash
set -euo pipefail

# 开关：非流水线场景静默退出
if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/.pipeline-active" ]; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# 从 .current-run 读取 run_id
RUN_ID=$(python3 -c "
import json
with open('${PROJECT_DIR}/review-output/.current-run') as f:
    print(json.load(f)['run_id'])
")

DUMP_FILE="${PROJECT_DIR}/benchmarks/dumps/${RUN_ID}.jsonl"
mkdir -p "$(dirname "$DUMP_FILE")"

# 读取 stdin，提取所需字段，追加一行 JSONL
python3 -c "
import sys, json, time
raw = json.load(sys.stdin)
ti = raw.get('tool_input', {})
tr = raw.get('tool_response', {})
content = tr.get('content', [])

# 完整 last_message（不截取）
last_msg = ''
if content and isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            last_msg = block.get('text', '')
            break

rec = {
    'ts': int(time.time()),
    'tool_use_id': raw.get('tool_use_id', ''),
    'description': ti.get('description', ''),
    'subagent_type': ti.get('subagent_type', ''),
    'duration_ms': tr.get('totalDurationMs', 0),
    'total_tokens': tr.get('totalTokens', 0),
    'total_tool_uses': tr.get('totalToolUseCount', 0),
    'usage': tr.get('usage', {}),
    'last_message': last_msg,
    'model': tr.get('usage', {}).get('model', ''),
}
print(json.dumps(rec, ensure_ascii=False))
" >> "$DUMP_FILE"
```

### 变化点

| 旧 | 新 |
|----|----|
| 按 session_id 命名 dump 文件 | 按 run_id 命名 |
| 截取前 500 字符 | 存完整 last_message |
| has_error 判断 | 去掉（子 Agent 错误由 verdict 体现） |
| is_dev_agent 判断 | 去掉（由轮次结构数据区分） |
| verdict 提取 | 去掉（由 pipeline-log.jsonl 提供） |
| reviewer 产物重命名 | 去掉（由 pipeline_engine / review skill 内部处理） |

## 结构化轮次数据: `pipeline-log.jsonl`

### 格式

```jsonl
{"ts": 1782313159, "round": 1, "node": "coder", "status": "success", "verdict": ""}
{"ts": 1782313247, "round": 1, "node": "reviewer", "status": "success", "verdict": "REVIEW_FAILED"}
{"ts": 1782313584, "round": 2, "node": "coder", "status": "success", "verdict": ""}
{"ts": 1782313849, "round": 2, "node": "reviewer", "status": "success", "verdict": "REVIEW_PASSED"}
```

### 写入方

`pipeline_engine report` 命令（`cli.py cmd_report`），在 `engine.report()` 调用成功后追加一行。

### 实现细节

`cmd_report` 中 `engine.report()` 返回 `state` 对象后：

```python
# state = engine.report(...)

# 从 state_file 路径提取 run_id: review-output/{run_id}/pipeline-state.json
run_id = state_path.parent.name
log_dir = Path("benchmarks") / run_id
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / "pipeline-log.jsonl"

import time
log_entry = {
    "ts": int(time.time()),
    "round": state.round,
    "node": args.node,
    "status": args.status,
    "verdict": args.verdict or "",
}
with open(log_path, "a") as f:
    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
```

关键设计决策：
- `state.round` 由 `record_result` 后返回，是当前轮次号
- `benchmarks/{run_id}/pipeline-log.jsonl` 路径相对于 CWD（即项目根目录，因为 /build 从项目根执行）
- 用 `mkdir -p / append` 模式确保多次调用不互相覆盖

### 变更点

| 文件 | 变更 |
|------|------|
| `agents/scheduler/pipeline_engine/cli.py` | `cmd_report` 增加写 pipeline-log.jsonl 的逻辑 |

## Stop Hook 如何获取 run_id

Stop hook 的 settings.json 配置从当前 shell 脚本改为直接调用 Python：

```json
{
    "hooks": [
        {
            "type": "command",
            "command": "python3 -m benchmark_lib.cli synthesize --auto-detect"
        }
    ]
}
```

`cli.py synthesize --auto-detect` 从 `review-output/.current-run` 读取 `run_id`：

```python
current_run_path = Path(project_dir) / "review-output" / ".current-run"
with open(current_run_path) as f:
    run_id = json.load(f)["run_id"]
```

这样零 bash 包装，hook 配置也保持简洁。

## 合成引擎: `benchmark_lib/synthesize.py`

### 输入

1. `benchmarks/dumps/{run_id}.jsonl` — 性能数据
2. `benchmarks/{run_id}/pipeline-log.jsonl` — 结构数据
3. 可选：`review-output/{run_id}/` — reviewer 产物（用于提取 issues）

### 处理流程

```
pipeline-log.jsonl                dumps/{run_id}.jsonl
        │                                    │
        ▼                                    ▼
  按 round 分组                     按 tool_use_id 匹配
  提取 role/verdict                提取 duration/tokens/usage
        │                                    │
        └──────────┬─────────────────────────┘
                   ▼
            合并为 rounds[]
                   │
                   ▼
            计算 convergence series
            计算 summary
            计算 cache_efficiency
                   │
                   ▼
            JSON Schema 校验
                   │
                   ▼
            写入 benchmark.json
            渲染 report.md
```

### 核心逻辑

**轮次数据来源**：从 `pipeline-log.jsonl` 直接读取，不再从描述文本正则推断。
每行包含 `node`（节点 ID: coder/reviewer）、`round`、`status`、`verdict`。

**性能数据匹配**：按时序匹配。`dumps/{run_id}.jsonl` 和 `pipeline-log.jsonl` 都是按执行顺序追加的，按 `node` 类型分组后依时序 zip：
1. 读取所有 dump 条目，按 `ts` 排序
2. 用 pipeline 节点描述关键词区分 coder/reviewer/dev-agent：
   - 包含 `"生成"` → coder
   - 包含 `"审查"` 或 `"review"` → reviewer
   - 其他 → dev agent（跳过，不参与合成）
3. 依时序与 pipeline-log 条目匹配合并

**Issues 提取**：如果 `review-output/{run_id}/` 下存在 `r{round}-pre-check-result.json` 和 `r{round}-review-result.json`，读取 issues 并挂载到对应 reviewer 记录。

### 函数签名

```python
def synthesize(run_id: str, project_dir: str = ".") -> dict:
    """合成 benchmark.json 数据。

    Args:
        run_id: 流水线运行 ID
        project_dir: 项目根目录

    Returns:
        符合 schema 2.0 的完整 JSON 对象

    Raises:
        FileNotFoundError: dumps/{run_id}.jsonl 不存在
        ValidationError: 合成结果不满足 JSON Schema
    """
```

## 报告渲染: `benchmark_lib/report.py`

### 职责

从 `benchmark.json` 数据渲染 Markdown 报告。渲染函数纯数据驱动，不访问文件系统。

### 函数签名

```python
def render_report(data: dict) -> str:
    """将 benchmark JSON 渲染为 Markdown 报告。"""
```

### 报告内容

- 运行概览（run_id、时间、git commit）
- 收敛曲线表（轮次号、P0/P1/P2/AI_FAIL 趋势）
- 各轮次详情（coder/reviewer、phase、duration、tokens、tools、cache_hit、result）
- 汇总（总耗时、总 Token、coder/reviewer 占比、缓存命中率、是否收敛）
- 模型使用

## 数据清理: `benchmark_lib/cleanup.py`

### 职责

清理 `benchmarks/dumps/` 和 `benchmarks/{run_id}/` 中超过保留天数的数据。

### 逻辑

1. 读取 `config.yaml` 的 `retention.max_days`
2. 遍历 `benchmarks/dumps/{run_id}.jsonl`，检查 mtime，删除过期文件
3. 遍历 `benchmarks/{run_id}/` 目录，检查 `benchmark.json` 的 mtime，删除过期目录
4. 硬保护：**跳过当前 run_id 的目录和 dump 文件**，即使时间戳异常也不删除

### 触发时机

Stop hook 合成完成后执行，不单独触发。

### 函数签名

```python
def cleanup(project_dir: str, current_run_id: str | None = None) -> int:
    """清理过期数据。

    Args:
        project_dir: 项目根目录
        current_run_id: 当前运行 ID，其数据不会被删除（硬保护）

    Returns:
        清理的文件/目录数量
    """
```

## CLI: `benchmark_lib/cli.py`

### 命令

```bash
# 合成 benchmark（Stop hook 调用）
python3 -m benchmark_lib.cli synthesize <run_id> [--project-dir .]

# 手动清理
python3 -m benchmark_lib.cli cleanup [--project-dir .] [--dry-run]
```

## 性能分析 Skill: `spark:benchmarks`

### 文件

`.claude/skills/spark-benchmarks.skill.md`

### 触发方式

```
/spark:benchmarks <run_id>
/spark:benchmarks <run_id_1> <run_id_2>  # 对比两次运行
```

### Skill 行为

1. 读取指定 run_id 的 `benchmarks/{run_id}/benchmark.json`
2. 如果是两个 run_id：读取两份数据，从以下维度对比：
   - 总 Token / 耗时 / 轮次
   - 收敛曲线（P0 下降速度）
   - 修复效率（每轮修复了多少 P0）
   - 缓存命中率
   - 模型使用
3. 输出分析结果，标明哪次运行综合表现更好

**不做**：统计检验、异常检测、趋势图渲染——这些交给 AI 的文字判断。

## 变更清单

### 新增文件

| 文件 | 职责 |
|------|------|
| `benchmarks/config.yaml` | 统一配置 |
| `benchmarks/hooks/dump-agent-payload.sh` | 数据采集（重写） |
| `benchmarks/benchmark_lib/__init__.py` | 包入口 |
| `benchmarks/benchmark_lib/config.py` | 配置加载 |
| `benchmarks/benchmark_lib/models.py` | 数据模型 + JSON Schema |
| `benchmarks/benchmark_lib/synthesize.py` | 合成引擎 |
| `benchmarks/benchmark_lib/report.py` | Markdown 渲染 |
| `benchmarks/benchmark_lib/cleanup.py` | 数据清理 |
| `benchmarks/benchmark_lib/cli.py` | CLI 入口 |
| `.claude/skills/spark-benchmarks.skill.md` | 性能分析 Skill |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `agents/scheduler/pipeline_engine/cli.py` | `report` 命令增加写 `pipeline-log.jsonl` 的逻辑 |
| `.claude/settings.json` | Stop hook 命令改为 `python3 -m benchmark_lib.cli synthesize --auto-detect`；增加 `spark-benchmarks` skill 注册 |
| `agents/scheduler/build.skill.md` | 无结构变化（hook 机制和 pipeline_engine 调用保持不变） |

### 删除文件

| 文件 | 原因 |
|------|------|
| `benchmarks/hooks/schema.py` | 被 `benchmark_lib/synthesize.py` + `report.py` 替代 |
| `benchmarks/hooks/compare.py` | 被 `spark:benchmarks` skill 替代 |
| `benchmarks/hooks/synthesize-benchmark.sh` | 被 `cli.py synthesize` 替代 |
| `benchmarks/hooks/__pycache__/` | 随旧文件删除 |

## 迁移

- 旧的 `benchmarks/run-*.json` 文件不作自动迁移，手动保留或删除
- 旧的 `benchmarks/dumps/session-*.jsonl` 文件不作自动迁移，手动保留或删除
- 新的合成逻辑写入 `benchmarks/{run_id}/` 目录，与旧文件并存不冲突

## 非目标

- 不做基线统计、异常检测、sparkline 趋势图
- 不做自动对比（对比由 `spark:benchmarks` skill 手动触发）
- 不做指纹计算（保留 git commit hash 即可）
- 不自动迁移旧数据
- 本期不写单元测试（先跑通端到端链路）
