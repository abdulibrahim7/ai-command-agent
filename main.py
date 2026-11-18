#!/usr/bin/env python3
"""Interactive CLI for reviewing and running proposed workspace actions."""
import json
from pathlib import Path
import sys

from action_executor import execute_action, log_action
from action_schema import PlanError, validate_action_plan
from llm_client import PlannerError, build_llm_client
from safety import WorkspaceError, safe_parts, workspace_root

ROOT = Path(__file__).resolve().parent


def confirm(question):
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"{question} Type yes to approve: ").strip() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def run(llm, root_fd, log_fd):
    print("=== AI File Assistant ===")
    print("Review proposed actions before they run. Type 'exit' or 'quit' to leave.")
    print("File operations use ./workspace. Workspace contents stay local.\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        try:
            actions = validate_action_plan(llm.plan_actions(user_input))
            for action in actions:
                params = action["params"]
                if "path" in params:
                    safe_parts(params["path"])
        except (PlannerError, PlanError, WorkspaceError):
            print("[BLOCKED] Planner unavailable or plan rejected. No actions ran.")
            log_action(log_fd, "plan", "blocked")
            continue
        print("\n[PLAN]")
        for index, action in enumerate(actions, 1):
            params = dict(action["params"])
            if "content" in params:
                data = params.pop("content")
                params["content_preview"] = data[:240]
                params["content_bytes"] = len(data.encode("utf-8"))
            print(f"  {index}. {action['type']} {json.dumps(params)}")
        if any(action["type"] != "no_op" for action in actions) and not confirm("Run this plan?"):
            log_action(log_fd, "plan", "cancelled")
            print("[SKIPPED] Plan canceled.")
            continue
        for action in actions:
            ok, message = execute_action(action, root_fd, log_fd, approved=True, approve_change=confirm)
            print(f"[{'OK' if ok else 'ERR'}] {message}\n")
            if not ok:
                print("[STOPPED] Remaining actions were skipped.")
                break
    print("Goodbye!")


def main():
    try:
        llm = build_llm_client()
        with workspace_root(ROOT / "workspace") as root_fd, workspace_root(ROOT / "logs") as log_fd:
            log_action(log_fd, "session", "started")
            run(llm, root_fd, log_fd)
    except PlannerError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (WorkspaceError, OSError):
        print("Cannot use the local workspace or audit log. Use macOS, Linux, or WSL and check workspace and logs permissions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
