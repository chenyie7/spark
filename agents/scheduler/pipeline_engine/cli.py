#!/usr/bin/env python3
"""pipeline-engine CLI — DAG-based workflow scheduler entry point.

Commands:
  start   — Initialize pipeline state from pipeline.yaml
  next    — Get next node(s) to execute
  report  — Record node execution result
  status  — Show current pipeline state
  reset   — Clear pipeline state
"""

import argparse
import json
import sys
from pathlib import Path

from pipeline_engine.config import load_pipeline, ConfigLoadError
from pipeline_engine.engine import PipelineEngine
from pipeline_engine.models import NodeStatus


def cmd_start(args):
    """Initialize pipeline state."""
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
        # Pipeline already running — return current state info
        existing = engine.status()
        print(json.dumps({
            "status": "already_running",
            "pipeline_name": existing.pipeline_name,
            "current_round": existing.round,
            "message": str(e),
        }))
        sys.exit(0)

    print(json.dumps({
        "status": "started",
        "pipeline_name": state.pipeline_name,
        "round": 0,
        "max_retries": config.defaults.max_retries,
        "message": f"Pipeline '{config.name}' started.",
    }))


def cmd_next(args):
    """Get next node(s) to execute."""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": "No pipeline state found. Run 'start' first.",
        }))
        sys.exit(0)

    pipeline_path = Path(args.pipeline)
    try:
        config = load_pipeline(pipeline_path)
    except ConfigLoadError as e:
        print(json.dumps({
            "action": "error",
            "nodes": [],
            "message": f"Failed to load pipeline config: {e}",
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
    """Record node execution result."""
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
    """Show current pipeline state."""
    state_path = Path(args.state_file)

    if not state_path.exists():
        print(json.dumps({"error": "No pipeline state found."}))
        sys.exit(0)

    with open(state_path, "r", encoding="utf-8") as f:
        state_data = json.load(f)

    print(json.dumps(state_data, ensure_ascii=False, indent=2))


def cmd_reset(args):
    """Clear pipeline state."""
    state_path = Path(args.state_file)

    if state_path.exists():
        state_path.unlink()
        print(json.dumps({"status": "reset", "message": "State cleared."}))
    else:
        print(json.dumps({"status": "reset", "message": "No state file to clear."}))


def main():
    parser = argparse.ArgumentParser(
        prog="pipeline-engine",
        description="DAG-based workflow scheduler for code generation pipelines",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── start ──
    p_start = sub.add_parser("start", help="Initialize a new pipeline run")
    p_start.add_argument("--pipeline", required=True, help="Path to pipeline.yaml")
    p_start.add_argument("--state-file", default="review-output/pipeline-state.json",
                         help="Path to state file")
    p_start.add_argument("--requirement", required=True, help="User requirement description")

    # ── next ──
    p_next = sub.add_parser("next", help="Get next node(s) to execute")
    p_next.add_argument("--pipeline", default="pipeline.yaml", help="Path to pipeline.yaml")
    p_next.add_argument("--state-file", default="review-output/pipeline-state.json",
                        help="Path to state file")

    # ── report ──
    p_report = sub.add_parser("report", help="Record node execution result")
    p_report.add_argument("--pipeline", default="pipeline.yaml", help="Path to pipeline.yaml")
    p_report.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")
    p_report.add_argument("--node", required=True, help="Node ID that completed")
    p_report.add_argument("--status", required=True,
                          choices=["success", "failed", "error", "skipped"],
                          help="Execution status")
    p_report.add_argument("--summary", default="", help="Human-readable summary")
    p_report.add_argument("--verdict", default="",
                          help="Agent verdict (REVIEW_PASSED/REVIEW_FAILED/REVIEW_ERROR)")

    # ── status ──
    p_status = sub.add_parser("status", help="Show current pipeline state")
    p_status.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")

    # ── reset ──
    p_reset = sub.add_parser("reset", help="Clear pipeline state")
    p_reset.add_argument("--state-file", default="review-output/pipeline-state.json",
                          help="Path to state file")

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
