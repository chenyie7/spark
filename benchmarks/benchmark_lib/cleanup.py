"""数据清理模块。

清理 benchmarks/dumps/ 和 benchmarks/{run_id}/ 中超过保留天数的数据。
硬保护当前 run_id 不删除。
"""

import os
import shutil
import time
from pathlib import Path

from benchmark_lib.config import load_config, resolve_path


def cleanup(project_dir: str = ".", current_run_id: str | None = None) -> int:
    """清理过期数据。

    Args:
        project_dir: 项目根目录
        current_run_id: 当前运行 ID，其数据不会被删除（硬保护）

    Returns:
        清理的文件/目录数量
    """
    config = load_config(project_dir)
    max_age_seconds = config.retention.max_days * 24 * 3600
    now = time.time()
    cutoff = now - max_age_seconds
    cleaned = 0

    # ── 清理 dumps/ ──
    dumps_dir = resolve_path(project_dir, config.paths.dumps_dir)
    if dumps_dir.is_dir():
        for f in sorted(dumps_dir.iterdir()):
            if not f.is_file():
                continue
            if not f.name.endswith(".jsonl"):
                continue
            run_id = f.name.replace(".jsonl", "")
            if run_id == current_run_id:
                continue
            if _mtime(f) < cutoff:
                f.unlink()
                cleaned += 1

    # ── 清理 {run_id}/ 目录 ──
    output_dir = resolve_path(project_dir, config.paths.output_dir)
    if output_dir.is_dir():
        for d in sorted(output_dir.iterdir()):
            if not d.is_dir():
                continue
            # 跳过非 run_id 目录（如 hooks/、dumps/、benchmark_lib/）
            run_id = d.name
            if run_id in ("hooks", "dumps", "benchmark_lib"):
                continue
            if run_id == current_run_id:
                continue
            benchmark_file = d / "benchmark.json"
            if benchmark_file.is_file() and _mtime(benchmark_file) < cutoff:
                shutil.rmtree(d)
                cleaned += 1

    return cleaned


def _mtime(path: Path) -> float:
    """获取文件/目录的最后修改时间。"""
    try:
        return os.path.getmtime(str(path))
    except OSError:
        return 0.0
