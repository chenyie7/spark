"""CLI 入口 — 基准测试命令行工具。

命令：
  synthesize  合成 benchmark.json 和 report.md
  cleanup     清理过期数据
"""

import argparse
import json
import sys
from pathlib import Path

from benchmark_lib.config import load_config
from benchmark_lib.models import validate_benchmark
from benchmark_lib.synthesize import synthesize
from benchmark_lib.report import render_report
from benchmark_lib.cleanup import cleanup


def _detect_run_id(project_dir: str) -> str | None:
    """从 review-output/.current-run 自动检测 run_id。"""
    current_run_path = Path(project_dir) / "review-output" / ".current-run"
    if not current_run_path.is_file():
        return None
    try:
        with open(current_run_path, "r") as f:
            return json.load(f).get("run_id", "")
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def cmd_synthesize(args):
    """合成 benchmark.json 和 report.md。"""
    project_dir = args.project_dir

    # 开关：非流水线场景静默退出（Stop hook 每次响应都触发）
    if not Path(project_dir, ".pipeline-active").exists():
        return

    # 自动检测 run_id
    run_id = args.run_id
    if not run_id:
        run_id = _detect_run_id(project_dir)
        if not run_id:
            return  # .current-run 不存在，静默退出

    config = load_config(project_dir)
    output_dir = Path(project_dir) / config.paths.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 合成
    try:
        data = synthesize(run_id, project_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 校验
    try:
        validate_benchmark(data)
    except Exception as e:
        print(f"Error: JSON Schema 校验失败 — {e}", file=sys.stderr)
        sys.exit(1)

    # 写入 benchmark.json
    json_path = output_dir / "benchmark.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Benchmark saved: {json_path}", file=sys.stderr)

    # 渲染并写入 report.md
    md_path = output_dir / "report.md"
    with open(md_path, "w") as f:
        f.write(render_report(data))
    print(f"Report saved:   {md_path}", file=sys.stderr)

    # 清理过期数据
    cleaned = cleanup(project_dir, current_run_id=run_id)
    if cleaned > 0:
        print(f"Cleaned {cleaned} expired benchmark(s).", file=sys.stderr)


def cmd_cleanup(args):
    """清理过期数据。"""
    project_dir = args.project_dir
    run_id = _detect_run_id(project_dir)

    cleaned = cleanup(project_dir, current_run_id=run_id)
    if args.dry_run:
        print(f"Would clean {cleaned} expired benchmark(s). (dry-run)")
    else:
        print(f"Cleaned {cleaned} expired benchmark(s).")


def main():
    parser = argparse.ArgumentParser(
        prog="benchmark-lib",
        description="基准测试数据合成、报告、清理工具",
    )
    sub = parser.add_subparsers(dest="command")

    # synthesize
    p_syn = sub.add_parser("synthesize", help="合成 benchmark.json 和 report.md")
    p_syn.add_argument("run_id", nargs="?", default="",
                       help="流水线 run_id（留空则从 .current-run 自动检测）")
    p_syn.add_argument("--project-dir", default=".", help="项目根目录")

    # cleanup
    p_cln = sub.add_parser("cleanup", help="清理过期基准测试数据")
    p_cln.add_argument("--project-dir", default=".", help="项目根目录")
    p_cln.add_argument("--dry-run", action="store_true", help="仅预览，不实际删除")

    args = parser.parse_args()
    if args.command == "synthesize":
        cmd_synthesize(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
