# Agent 子进程权限自动放行 — 设计文档

日期：2026-07-14
状态：设计中

---

## 一、问题

`/build` 流水线通过 pipeline_engine 调度 coder → reviewer 子 Agent 时，Agent 工具调用没有指定 `mode` 参数。子 Agent 以 `default` 模式运行，写文件、执行 Bash 等操作频繁弹出权限确认，打断流水线自动执行。

## 二、方案

在 pipeline 体系中增加 `mode` 字段，从 pipeline.yaml → models → engine → CLI → build.skill.md 一路透传，最终传给 Agent 工具的 `mode` 参数。

### 数据流

```
pipeline.yaml (mode: acceptEdits)
  → models.py: NodeConfig.mode / PipelineDefaults.mode
    → engine.py: _render_nodes() → NodeToExecute.mode
      → CLI next 返回 JSON 含 mode
        → build.skill.md: Agent(mode: "{mode}")
```

### 不做的

- **不创建 `.claude/agents/*.md`** agent 定义文件 — 权限模式走 pipeline 配置足够
- **不修改 `.claude/settings.json`** — 现有 `permissions.allow` 已放行必要的 Bash 命令
- **不在 `prompt_template` 里嵌入配置** — prompt 是纯文本指令，不会被解析为 agent 配置

## 三、`acceptEdits` 模式下的行为

| 操作 | 行为 |
|------|------|
| Read / Grep / Glob | 免确认（默认） |
| Write / Edit Java 文件 | 自动批准 |
| mkdir, mv, cp, rm 等常见文件系统命令 | 自动批准 |
| `python3 -m code_check.cli *` | 已由 permissions.allow 放行 |
| `python3 -m pipeline_engine.cli *` | 已由 permissions.allow 放行 |

## 四、文件改动清单

### 4.1 `agents/scheduler/pipeline.yaml`

`defaults` 加 `mode: acceptEdits`，每个 `node` 可覆盖：

```yaml
defaults:
  timeout: 600s
  max_retries: 3
  block_on: [P0]
  base_path: "."
  project_name: ""
  mode: acceptEdits          # 新增

nodes:
  - id: coder
    ...
    mode: acceptEdits        # 新增（可覆盖 defaults）

  - id: reviewer
    ...
    mode: acceptEdits        # 新增（可覆盖 defaults）
```

### 4.2 `agents/scheduler/pipeline_engine/models.py`

三个 dataclass 加 `mode` 字段：

- `PipelineDefaults` — 加 `mode: str = "default"`
- `NodeConfig` — 加 `mode: Optional[str] = None`（null 时取 defaults）
- `NodeToExecute` — 加 `mode: str = "default"`

对应的 `from_dict` / `to_dict` 更新。

### 4.3 `agents/scheduler/pipeline_engine/engine.py`

`_render_nodes()` 取 `node.mode or self.config.defaults.mode`，传入 `NodeToExecute`。

### 4.4 `agents/scheduler/build.skill.md`

Agent 工具调用步骤加 `mode` 参数：

```
- mode: 使用节点返回的 mode 值
```

### 4.5 测试更新

`tests/test_models.py` 和 `tests/test_engine.py` 需要更新，覆盖 `mode` 字段的默认值、from_dict/to_dict 序列化、defaults 回退逻辑。

## 五、不改动范围

- `.claude/settings.json` — 现有权限配置不变
- `.claude/agents/` — 不创建任何 agent 定义文件
- 流水线 DAG 逻辑 — 只加字段透传，不改业务逻辑
- PM 阶段 — 不受影响
