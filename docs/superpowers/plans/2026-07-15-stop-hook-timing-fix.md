# Stop Hook 时序修复计划

> **状态:** 待确认 | **日期:** 2026-07-15

## 问题

`/build` 流水线完成时，build skill 在 Stop hook 触发前就删除了 `.pipeline-active`，导致合成引擎静默退出，benchmark 从未自动生成。

## 根因

```
build skill: rm -f .pipeline-active     ← 在响应结束前删除
响应结束后:  Stop hook 触发             ← 标记不存在，跳过合成
```

## 方案

**标记删除权从 build skill 移交给 Stop hook。** build skill 只管流水线执行，不管清理。

## 改动

### 1. `agents/scheduler/build.skill.md`

done 分支：删掉清理命令

```
# 改前：
- `action == "done"` → **清理标记文件：** `rm -f .pipeline-active && rm -f review-output/.current-run`。然后读取 `review-output/{run_id}/final-review-report.md` 展示结果。

# 改后：
- `action == "done"` → 读取 `review-output/{run_id}/final-review-report.md` 展示结果。流水线完成。
```

error 分支：同样删掉清理命令

```
# 改前：
- `action == "error"` → **清理标记文件：** `rm -f .pipeline-active && rm -f review-output/.current-run`。展示 `message` 内容。

# 改后：
- `action == "error"` → 展示 `message` 内容，提示用户介入。
```

### 2. `benchmarks/benchmark_lib/cli.py`

合成成功后删除 `.pipeline-active`（阻止后续 Stop hook 重复触发）

```python
# cmd_synthesize 末尾，在 cleanup 之后增加：

# 清理流水线标记（阻止后续 Stop hook 重复合成）
pipeline_marker = Path(project_dir, ".pipeline-active")
if pipeline_marker.exists():
    pipeline_marker.unlink()
```

## 执行顺序

```
1. build skill 流程结束（不删标记）
2. 响应结束 → Stop hook 触发
3. cli.py synthesize --auto-detect
   - .pipeline-active 存在 ✓
   - 合成 benchmark.json + report.md
   - 清理过期数据
   - 删除 .pipeline-active
4. 下一次 Stop hook 触发 → .pipeline-active 不存在 → 静默退出
```

## 测试

用一个简单 demo 跑 `/build "输出 Hello World" --project-name hello-test`：

1. PM 阶段 → Phase 2
2. 流水线完成
3. 检查 `benchmarks/{run_id}/benchmark.json` 是否自动生成
4. 检查 `.pipeline-active` 是否在合成后被删除
