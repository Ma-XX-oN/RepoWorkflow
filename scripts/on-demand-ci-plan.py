#!/usr/bin/env python3
"""Resolve the requested hosted CI stage from a dedicated invocation commit."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.ci_invocation import (
  CiInvocationError, original_candidate, verify_invocation,
)


def plan_invocation(root: Path) -> dict[str, str]:
  request = verify_invocation(root)
  invocation_sha = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    text=True,
  ).strip()
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
  raise SystemExit(main())
