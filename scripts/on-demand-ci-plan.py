#!/usr/bin/env python3
"""Resolve the requested hosted CI stage from a dedicated invocation commit."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.ci_invocation import (
  CiInvocationError, original_candidate, verify_invocation,
)
from repo_workflow.process import run_command


def plan_invocation(root: Path) -> dict[str, str]:
  branch = os.environ.get("GITHUB_REF_NAME")
  if not branch:
    resolved = run_command(["git", "-C", str(root),
                            "symbolic-ref", "--short", "HEAD"], root)
    if resolved.returncode:
      raise CiInvocationError("cannot read current CI branch")
    branch = resolved.stdout.strip()
  if re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch) is None:
    raise CiInvocationError("on-demand CI requires a valid issue branch")
  request = verify_invocation(root)
  observed = run_command(["git", "-C", str(root), "rev-parse", "HEAD"], root)
  if observed.returncode:
    raise CiInvocationError("cannot verify CI invocation revision")
  invocation_sha = observed.stdout.strip()
  return {
    "stage": request.stage,
    "previous_tip": request.previous_tip,
    "tested_sha": original_candidate(root, request.previous_tip),
    "invocation_sha": invocation_sha,
  }


def main() -> int:
  try:
    plan = plan_invocation(ROOT)
  except CiInvocationError as error:
    print(f"CI invocation rejected: {error}", file=sys.stderr)
    return 1
  print(json.dumps(plan, sort_keys=True))
  return 0

if __name__ == "__main__":
  # All Python output, including print() and tracebacks, uses one UTF-8 boundary.
  from pathlib import Path
  import sys
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  from repo_workflow.output import configure_utf8_output
  if not configure_utf8_output():
    raise SystemExit(2)
  raise SystemExit(main())
