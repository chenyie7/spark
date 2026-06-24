#!/usr/bin/env python3
"""pipeline-engine CLI — 基于 DAG 的工作流调度器入口。

命令：
  start   — 从 pipeline.yaml 初始化流水线状态
  next    — 获取下一个要执行的节点
  report  — 记录节点执行结果
  status  — 显示当前流水线状态
  reset   — 清除流水线状态
"""

import argparse
import json
import sys
from pathlib import Path

from pipeline_engine.config import load_pipeline, ConfigLoadError
from pipeline_engine.engine import PipelineEngine
from pipeline_engine.models import NodeStatus


def _generate_run_id(target_dir: str) -> str:
    """生成运行 ID，格式: YYYYMMDDHHmmss[-target_dir]

    target_dir 为 "." 时不加后缀，如 20260624153000。
    target_dir 为 "admin-test" 时加后缀，如 20260624153000-admin-test。
    """
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if target_dir and target_dir != ".":
        return f"{timestamp}-{target_dir}"
    return timestamp


def cmd_start(args):
    """初始化流水线状态。"""
    pipeline_path = Path(args.pipeline)
    state_path = Path(args.state_file)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        state = engine.start(args.requirement)
    except RuntimeError as e:
        # 流水线已在运行 → 返回当前状态信息
        existing = engine.status()
        print(json.dumps({
            "status": "already_running",
            "pipeline_name": existing.pipeline_name,
            "current_round": existing.round,
            "message": str(e),
        }))
        sys.exit(0)

    # 生成 run_id 并存入状态
    run_id = _generate_run_id(args.target_dir)
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


def cmd_next(args):
    """获取下一个要执行的节点。"""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": "未找到流水线状态。请先运行 'start'。",
        }))
        sys.exit(0)

    pipeline_path = Path(args.pipeline)
    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": f"加载流水线配置失败: {e}",
        }))
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        action = engine.next()
    except RuntimeError as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": str(e),
        }))
        sys.exit(0)

    print(action.to_json())


def cmd_report(args):
    """记录节点执行结果。"""
    state_path = Path(args.state_file)
    pipeline_path = Path(args.pipeline)

    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({"accepted": False, "error": str(e)}))
        sys.exit(1)

    engine = PipelineEngine(config, state_path)
    try:
        status = NodeStatus(args.status)
        state = engine.report(
            node_id=args.node,
            status=status,
            summary=args.summary or "",
            agent_verdict=args.verdict or "",
        )
    except (ValueError, RuntimeError) as e:
        print(json.dumps({"accepted": False, "error": str(e)}))
        sys.exit(0)

    print(json.dumps({
        "accepted": True,
        "state": state.status.value,
        "round": state.round,
        "current_nodes": state.current_nodes,
    }))


def cmd_status(args):
    """显示当前流水线状态。"""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({"error": "未找到流水线状态。"}))
        sys.exit(0)

    with open(state_path, "r", encoding="utf-8") as f:
        state_data = json.load(f)

    print(json.dumps(state_data, ensure_ascii=False, indent=2))


def cmd_reset(args):
    """清除流水线状态。"""
    state_path = Path(args.state_file)

    if state_path.exists():
        state_path.unlink()
        print(json.dumps({"status": "reset", "message": "状态已清除。"}))
    else:
        print(json.dumps({"status": "reset", "message": "没有需要清除的状态文件。"}))


def main():
    parser = argparse.ArgumentParser(
        prog="pipeline-engine",
        description="基于 DAG 的工作流调度器，用于代码生成流水线",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── start ──
    p_start = sub.add_parser("start", help="初始化新的流水线运行")
    p_start.add_argument("--pipeline", required=True, help="pipeline.yaml 的路径")
    p_start.add_argument("--state-file", default="review-output/pipeline-state.json",
                         help="状态文件路径")
    p_start.add_argument("--requirement", required=True, help="用户需求描述")
    p_start.add_argument("--target-dir", default=".",
                         help="模块根目录（相对于项目根）")

    # ── next ──
    p_next = sub.add_parser("next", help="获取下一个要执行的节点")
    p_next.add_argument("--pipeline", default="pipeline.yaml", help="pipeline.yaml 的路径")
    p_next.add_argument("--state-file", default="review-output/pipeline-state.json",
                        help="状态文件路径")

    # ── report ──
    p_report = sub.add_parser("report", help="记录节点执行结果")
    p_report.add_argument("--pipeline", default="pipeline.yaml", help="pipeline.yaml 的路径")
    p_report.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="状态文件路径")
    p_report.add_argument("--node", required=True, help="已完成的节点 ID")
    p_report.add_argument("--status", required=True,
                          choices=["success", "failed", "error", "skipped"],
                          help="执行状态")
    p_report.add_argument("--summary", default="", help="人类可读的摘要")
    p_report.add_argument("--verdict", default="",
                          help="Agent 判定（REVIEW_PASSED/REVIEW_FAILED/REVIEW_ERROR）")

    # ── status ──
    p_status = sub.add_parser("status", help="显示当前流水线状态")
    p_status.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="状态文件路径")

    # ── reset ──
    p_reset = sub.add_parser("reset", help="清除流水线状态")
    p_reset.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="状态文件路径")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(args)
    elif args.command == "next":
        cmd_next(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)


if __name__ == "__main__":
    main()
