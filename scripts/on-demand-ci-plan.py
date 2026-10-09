#!/usr/bin/env python3
"""Resolve the requested hosted CI stage from a dedicated invocation commit."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.ci_invocation import CiInvocationError, verify_invocation


def main() -> int:
  try:
    request = verify_invocation(ROOT)
  except CiInvocationError as error:
    print(f"CI invocation rejected: {error}", file=sys.stderr)
    return 1
  print(json.dumps({
    "stage": request.stage,
    "previous_tip": request.previous_tip,
    "tested_sha": __import__("subprocess").check_output(
      ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
      text=True,
    ).strip(),
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
