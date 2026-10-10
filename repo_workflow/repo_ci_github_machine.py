"""Internal consumer GitHub machine compatibility via configured repo-ci."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
  sys.path.insert(0, str(ENGINE_ROOT))

from repo_workflow.repo_ci_dispatcher import RepoCiError, dispatch


OPERATIONS = {
  "mode": ("inspect-context", "mode"),
  "matrix": ("resolve-capabilities", "matrix"),
  "prepare-context": ("prepare", "prepare-context"),
}


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("command", choices=sorted(OPERATIONS))
  parser.add_argument("--event-name")
  parser.add_argument("--event-path")
  parser.add_argument("--branch")
  args = parser.parse_args(argv)
  workspace = Path.cwd().resolve()
  required = (
    "RWF_REPO_CI_WORKSPACE", "RWF_CI_BASE_SHA",
    "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
  )
  if any(not os.environ.get(name) for name in required):
    print("repo-ci GitHub machine identity is not configured", file=sys.stderr)
    return 2
  if Path(os.environ["RWF_REPO_CI_WORKSPACE"]).resolve() != workspace:
    print("consumer workspace identity mismatch", file=sys.stderr)
    return 2
  try:
    head = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True,
      check=True, text=True, timeout=10,
    ).stdout.strip()
  except (OSError, subprocess.SubprocessError):
    print("consumer checkout identity unavailable", file=sys.stderr)
    return 2
  operation, legacy = OPERATIONS[args.command]
  inputs = {"consumer_workspace": str(workspace), "legacy": legacy}
  if args.command == "mode":
    if not all((args.event_name, args.event_path, args.branch)):
      parser.error("mode requires event name, event path and branch")
    inputs.update({
      "event_name": args.event_name,
      "event_path": args.event_path,
      "branch": args.branch,
    })
  request = {
    "contract_version": 1,
    "operation": operation,
    "invocation_id": (
      os.environ["GITHUB_RUN_ID"] + "-" +
      os.environ["GITHUB_RUN_ATTEMPT"] + "-" + legacy
    ),
    "candidate": {
      "repository": os.environ["GITHUB_REPOSITORY"],
      "commit": head,
      "base": os.environ["RWF_CI_BASE_SHA"],
    },
    "requirements": {"stages": [], "capabilities": [], "artifacts": []},
    "inputs": inputs,
  }
  try:
    response = dispatch(
      workspace, operation, json.dumps(request).encode("utf-8"),
    )
  except RepoCiError as exc:
    print(f"repo-ci {exc.code}: {exc}", file=sys.stderr)
    return 2
  if response["status"] != "ok":
    print(json.dumps(response["diagnostics"]), file=sys.stderr)
    return 2
  result = response["observations"]["legacy_output"]
  if args.command == "mode":
    if not isinstance(result, str) or result not in (
      "none", "stable", "development",
    ):
      print("invalid legacy execution mode", file=sys.stderr)
      return 2
    print(result)
  else:
    if not isinstance(result, dict):
      print("invalid legacy GitHub context", file=sys.stderr)
      return 2
    print(json.dumps(result, separators=(",", ":")))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
