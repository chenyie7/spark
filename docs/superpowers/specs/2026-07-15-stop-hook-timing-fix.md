# Stop Hook 时序修复

> **状态:** 待确认 | **日期:** 2026-07-15

## 问题

`/build` 流水线结束时，build skill 在 Stop hook 触发前删除了 `.pipeline-active` 标记文件，导致合成引擎因标记不存在而静默退出，benchmark 数据从未自动生成。

## 根因

```
build skill 执行完毕 → rm -f .pipeline-active （标记删除）
                              ↓
                    响应结束 → Stop hook 触发
                              ↓
                    .pipeline-active 不存在 → 静默退出 → benchmark 未生成
```

Stop hook 是异步的，在响应结束后触发，而标记删除在响应结束前完成，存在不可消除的时序差。

## 方案

**标记删除权从 build skill 移交给 Stop hook。**

- build skill：只管流水线执行和结果展示，不碰标记文件
- Stop hook（合成引擎）：合成成功后删除 `.pipeline-active`，阻止后续重复触发

## 改动

### `agents/scheduler/build.skill.md`

done 分支和 error 分支删除清理标记文件的命令：

```diff
- `action == "done"` → **清理标记文件：** `rm -f .pipeline-active && rm -f review-output/.current-run`。然后读取...
+ `action == "done"` → 读取 `review-output/{run_id}/final-review-report.md` 展示结果。流水线完成。

- `action == "error"` → **清理标记文件：** `rm -f .pipeline-active && rm -f review-output/.current-run`。展示 `message` 内容...
+ `action == "error"` → 展示 `message` 内容，提示用户介入。
```

### `benchmarks/benchmark_lib/cli.py`

`cmd_synthesize` 末尾，合成成功后删除 `.pipeline-active`：

```python
# 清理流水线标记（阻止后续 Stop hook 重复合成）
pipeline_marker = Path(project_dir, ".pipeline-active")
if pipeline_marker.exists():
    pipeline_marker.unlink()
```

## 非目标

- `.current-run` 不删除（下次 `/build` 会覆盖，无影响）
- Stop hook 的 PostToolUse 开关机制不变

## 验证

用简单 demo 跑一次 `/build`，检查 benchmark 是否自动生成。
