# 性能日志系统设计文档

**日期**：2026-06-21
**状态**：待审批
**范围**：为 `/build` 流水线增加自动化的性能数据采集、存储和对比能力

---

## 一、目标

每次 `/build` 流水线运行结束后，自动产出两份文件：

```
benchmarks/
├── run-20260621-002300-login-register.json    ← 结构化性能日志（供脚本对比）
└── run-20260621-002300-login-register.md      ← 人类可读报告（从 JSON 渲染）
```

后续通过对比两次运行的 JSON，可以精确回答：
- coder/reviewer 代码更新后，Token 消耗是否下降？
- 修复收敛轮次是否减少？
- 缓存命中率是否改善？
- 新增异常消耗（如越权修改）是否消除？

---

## 二、架构概览

纯 Hook 驱动，零侵入现有流水线代码。

```
                         /build 流水线运行中
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ coder    │  │ reviewer │  │ coder    │  │ reviewer │  ...
│ Agent()  │  │ Agent()  │  │ Agent()  │  │ Agent()  │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
 PostToolUse    PostToolUse    PostToolUse    PostToolUse
 (Agent)        (Agent)        (Agent)        (Agent)
     │              │              │              │
     │              ├─ 重命名产物    │              ├─ 重命名产物
     │              │  rN-*.json   │              │  rN-*.json
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                         │
                         ▼
              session-xxx.jsonl（累积追加）
                         │
                    流水线结束
                         │
                         ▼
                     Stop hook
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    读 session.jsonl  读 r*-pre-check  算指纹
          │              │              │
          └──────────────┴──────────────┘
                         │
                         ▼
              合成 benchmarks/run-*.json
                         │
                         ▼
              渲染 benchmarks/run-*.md
```

**不改动的文件：**
- `pipeline.yaml`
- `/build` skill
- `code_check/cli.py`
- `agents/coder/**`
- 任何 Java 代码

**新增/修改的文件：**
- `.claude/hooks/dump-agent-payload.sh` — 修改（追加 reviewer 重命名逻辑）
- `.claude/hooks/synthesize-benchmark.sh` — 新建（Stop hook 合成脚本）
- `.claude/settings.json` — 修改（追加 Stop hook 配置）

---

## 三、Hook 设计

### 3.1 Hook 1：PostToolUse (Agent) — 轻量采集 + 产物归档

**触发时机**：每次 `Agent` 工具调用完成
**职责**：
1. 从 stdin 提取关键字段，追加一行 JSONL 到 session dump 文件
2. 检测是否为 reviewer Agent；若是，重命名 review-output 产物，加入轮次号

**stdin 来源**（已验证真实 payload）：

| 字段路径 | 示例值 | 用途 |
|---------|--------|------|
| `session_id` | `"414e930c-..."` | 区分不同会话 |
| `tool_use_id` | `"call_00_xxx"` | 去重标识 |
| `tool_input.description` | `"coder 生成登录注册代码"` | 判断 coder/reviewer 角色 |
| `tool_input.subagent_type` | `"general-purpose"` | 辅助判断 |
| `tool_response.totalDurationMs` | `1370` | Agent 耗时（ms） |
| `tool_response.totalTokens` | `17768` | 总 Token |
| `tool_response.totalToolUseCount` | `0` | 工具调用次数 |
| `tool_response.usage.input_tokens` | `2366` | 输入 Token |
| `tool_response.usage.output_tokens` | `42` | 输出 Token |
| `tool_response.usage.cache_read_input_tokens` | `15360` | 缓存命中 Token |
| `tool_response.usage.cache_creation_input_tokens` | `0` | 缓存创建 Token |
| `tool_response.usage.service_tier` | `"standard"` | 服务等级 |
| `tool_response.usage.speed` | `"standard"` | 速度档位 |
| `tool_response.usage.server_tool_use.*` | `0` | Web 搜索/抓取次数 |
| `tool_response.content[0].text` | `"HELLO_DUMP_TEST"` | Agent 最终回复（取前 200 字符用于状态判定） |

**reviewer 检测逻辑**：

```bash
DESC=$(echo "$RAW" | jq -r '.tool_input.description // ""')
if echo "$DESC" | grep -qiE 'review|审查'; then
    # 是 reviewer，重命名产物
fi
```

**产物重命名逻辑**：

```bash
REVIEW_DIR="agents/reviewer/check_system/review-output"
N=$(find "$REVIEW_DIR" -maxdepth 1 -name "r*-pre-check-result.json" | wc -l | tr -d ' ')

for f in pre-check-result.json pre-check-report.md review-result.json; do
    if [ -f "$REVIEW_DIR/$f" ]; then
        mv "$REVIEW_DIR/$f" "$REVIEW_DIR/r${N}-$f"
    fi
done
```

**产出文件**：
- `.claude/hooks/dumps/session-{session_id}.jsonl` — 每行一条 Agent 记录

**JSONL 单行格式**：

```json
{
  "ts": 1718936627,
  "tool_use_id": "call_00_xxx",
  "description": "coder 生成登录注册代码",
  "subagent_type": "general-purpose",
  "duration_ms": 196000,
  "total_tokens": 65973,
  "total_tool_uses": 57,
  "usage": {
    "input_tokens": 45000,
    "output_tokens": 20973,
    "cache_read_input_tokens": 12000,
    "cache_creation_input_tokens": 0
  },
  "last_message_snippet": "All files are created..."
}
```

### 3.2 Hook 2：Stop — 合成与输出

**触发时机**：流水线对话结束（Claude 停止响应时）
**职责**：
1. 读取 session dump 文件，推断每条记录的 round/phase/role
2. 读取 `review-output/r*-pre-check-result.json`，提取每轮 P0/P1/P2/AI_FAIL 数量
3. 计算 coder 和 reviewer 的版本指纹（sha256）
4. 合成完整 `benchmarks/run-*.json`
5. 渲染 `benchmarks/run-*.md`

**Round 推断规则**：

```
顺序扫描 session.jsonl：
  round = 0
  prev_role = null

  对每条记录：
    role = description 含 review 则为 reviewer，否则为 coder

    如果 role == coder 且 prev_role == reviewer：
      round++

    如果 role == coder 且 prev_role == null：
      phase = "generate"
    如果 role == coder 且 prev_role == reviewer：
      phase = "fix"
    如果 role == reviewer：
      phase = "review"
      从 last_message_snippet 匹配 REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR 作为 result
      读取 review-output/r{round}-pre-check-result.json 获取 issues

    prev_role = role
```

**指纹计算**：

```bash
# coder 指纹
coder_files="agents/coder/ agents/scheduler/pipeline.yaml"
coder_checksum=$(find $coder_files -type f \( -name "*.md" -o -name "*.yaml" \) | sort | xargs cat | sha256sum | cut -c1-8)

# reviewer 指纹
reviewer_files="agents/reviewer/check_system/code_check/ agents/reviewer/check_system/rules/ agents/reviewer/check_system/code-check-config.yaml agents/reviewer/hooks/"
reviewer_checksum=$(find $reviewer_files -type f \( -name "*.py" -o -name "*.yaml" -o -name "*.sh" \) | sort | xargs cat | sha256sum | cut -c1-8)
```

**需求 slug 生成**：从 `/build` 的 requirement 文本取最早 20 个中文字符，转为拼音首字母或直接用中文截断，移除特殊字符。

**配置文件（`.claude/settings.json`）**：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/dump-agent-payload.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/synthesize-benchmark.sh"
          }
        ]
      }
    ]
  }
}
```

---

## 四、数据 Schema

### 4.1 JSON 结构（`benchmarks/run-{timestamp}-{slug}.json`）

```json
{
  "schema_version": "1.0",
  "meta": {
    "run_id": "run-20260621-002300",
    "timestamp_start": "2026-06-21T00:23:47+08:00",
    "timestamp_end":   "2026-06-21T00:38:12+08:00",
    "requirement_slug": "login-register",
    "requirement_full": "实现一个登录注册功能...",
    "config": {
      "max_retries": 3,
      "block_strategy": "strict",
      "block_on": ["P0"]
    }
  },
  "agents": {
    "coder": {
      "fingerprint": "a3f2b91c",
      "fingerprint_full": "sha256:a3f2b91c7d...",
      "source_file_count": 15
    },
    "reviewer": {
      "fingerprint": "d7e0f2b3",
      "fingerprint_full": "sha256:d7e0f2b3a1...",
      "source_file_count": 12
    }
  },
  "rounds": [
    {
      "round": 0,
      "coder": {
        "phase": "generate",
        "duration_ms": 196000,
        "total_tokens": 65973,
        "total_tool_uses": 57,
        "usage": {
          "input_tokens": 45000,
          "output_tokens": 20973,
          "cache_read_input_tokens": 12000,
          "cache_creation_input_tokens": 0
        }
      },
      "reviewer": {
        "phase": "review",
        "duration_ms": 46000,
        "total_tokens": 24700,
        "total_tool_uses": 6,
        "result": "REVIEW_FAILED",
        "issues": {
          "P0": 2,
          "P1": 10,
          "P2": 40,
          "AI_FAIL": 0
        },
        "usage": {
          "input_tokens": 20000,
          "output_tokens": 4700,
          "cache_read_input_tokens": 8000,
          "cache_creation_input_tokens": 0
        }
      }
    }
  ],
  "convergence": {
    "rounds_to_converge": null,
    "termination_reason": "max_retries_exceeded",
    "series": [
      { "round": 0, "P0": 2, "P1": 10, "P2": 40, "AI_FAIL": 0 },
      { "round": 1, "P0": 0, "P1": 10, "P2": 41, "AI_FAIL": 0 },
      { "round": 2, "P0": 0, "P1": 0,  "P2": 38, "AI_FAIL": 1 },
      { "round": 3, "P0": 0, "P1": 0,  "P2": 36, "AI_FAIL": 1 }
    ]
  },
  "summary": {
    "total_duration_ms": 1195000,
    "total_tokens": 435397,
    "total_tool_uses": 244,
    "coder": {
      "total_tokens": 280736,
      "total_duration_ms": 827000,
      "avg_tokens_per_call": 70184
    },
    "reviewer": {
      "total_tokens": 154661,
      "total_duration_ms": 368000,
      "avg_tokens_per_call": 38665
    },
    "cache_efficiency": {
      "total_cache_read_tokens": 85000,
      "total_input_tokens": 200000,
      "cache_hit_ratio": 0.425
    },
    "converged": false
  }
}
```

### 4.2 Markdown 输出（`benchmarks/run-{timestamp}-{slug}.md`）

从 JSON 渲染，结构沿用 `docs/pipeline-reports/2025-06-21-build-login-register.md` 的模板：
- 元信息（时间、Git 状态、指纹对比）
- 资源消耗表（每轮 Token / Tools / 耗时）
- 收敛曲线（ASCII 柱状图）
- 汇总对比（Coder vs Reviewer）

---

## 五、对比分析流程（后续）

两个 benchmarking JSON 可用脚本对比：

```bash
python3 scripts/compare-benchmarks.py \
  benchmarks/run-20260621-login-v1.json \
  benchmarks/run-20260622-login-v2.json
```

输出：
```
Coder: a3f2b91c → b7e0d2f3
  Tokens:  280,736 → 245,000  (-12.7%) ✅
  Duration: 827s → 710s  (-14.2%) ✅

Reviewer: d7e0f2b3 → e1a3c4f5
  Tokens:  154,661 → 168,000  (+8.6%) ⚠️
  Duration: 368s → 390s  (+6.0%) ⚠️

Convergence: 4 rounds → 3 rounds  (-25%) ✅
Cache Hit:  42.5% → 58.2%  (+37%) ✅

Overall: ✅ Regression passed (4/4 improved, 0 degraded)
```

---

## 六、状态机梳理

```
SessionStart
  │
  ├─ /build 启动 ──→ 主控 Agent 开始调度
  │
  ├─ Agent(coder) 完成 ──→ PostToolUse(Agent) ──→ dump JSONL 第 1 行
  ├─ Agent(reviewer) 完成 ──→ PostToolUse(Agent) ──→ dump JSONL 第 2 行
  │                                                    └─→ mv review-output/* → r0-*
  ├─ Agent(coder) 完成 ──→ PostToolUse(Agent) ──→ dump JSONL 第 3 行
  ├─ Agent(reviewer) 完成 ──→ PostToolUse(Agent) ──→ dump JSONL 第 4 行
  │                                                    └─→ mv review-output/* → r1-*
  │  ...（重复 N 轮）
  │
  ├─ /build 结束 ──→ 主控输出最终状态
  │
Stop ──→ synthesize-benchmark.sh
            │
            ├─ 读 session.jsonl
            ├─ 读 r*-pre-check-result.json
            ├─ 算指纹
            ├─ 写 benchmarks/run-*.json
            └─ 写 benchmarks/run-*.md
```

---

## 七、边界条件

| 场景 | 处理 |
|------|------|
| Session dump 为空（没跑流水线） | Stop 脚本退出 0，不生成 benchmark |
| PostToolUse hook 崩溃 | 单条数据丢失，不影响后续采集。Stop 脚本容忍缺失轮次 |
| reviewer 之后没有生成 review-result.json | `issues.AI_FAIL` 标记为 -1（未知） |
| 中途对话被压缩 | 不影响，PostToolUse 按 Agent 完成触发，不依赖消息历史 |
| 多个 /build 在同一 session | 最后一个 Stop 只取当前 session 数据 |
| 文件被删除后 Stop 找不到产物 | 跳过该轮 issue 数据，记录 warning |
| 轮次 > max_retries 依然运行 | 正常记录，convergence.termination_reason=manual |
| 指纹计算时 agents 目录文件不存在 | 记录空指纹 + warning，不阻断日志生成 |

---

## 八、后续扩展

1. **对比命令**：`scripts/compare-benchmarks.py` 实现两个 JSON 的逐项 diff
2. **趋势面板**：多次运行后，用 collected JSON 生成趋势图
3. **CI 集成**：`compare-benchmarks.py` 可在 CI 中做回归测试——阻止性能退化的 PR
4. **自动基准**：固定一个「基准需求」，每次 agent 变更后自动跑一次记录基线
5. **`changed_since_last_run` 字段**：V1 不实现——需要跨 run 对比指纹。V2 在 compare 脚本中通过比较两次 JSON 的 `agents.*.fingerprint` 来计算
6. **source_files 列表**：V1 只存 `source_file_count`，完整路径列表留给 V2（体量较大，对比时可按需反查）
7. **`.gitignore`**：`benchmarks/` 和 `.claude/hooks/dumps/` 应加入 `.gitignore`，这些是运行时产物
