#!/usr/bin/env python3
"""Resolve the requested hosted CI stage from a dedicated invocation commit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.ci_invocation import CiInvocationError, verify_invocation


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    capture_output=True, text=True, check=False,
  )
  if result.returncode:
    raise CiInvocationError("cannot resolve hosted candidate ancestry")
  return result.stdout.strip()


def _original_candidate(root: Path, previous_tip: str) -> str:
  """Skip only verified request and canonical-result publication commits."""
  sha = previous_tip
  while True:
    parents = _git(root, "rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 2:
      return sha
    parent = parents[1]
    changed = _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha,
    ).splitlines()
    if changed == [".ci/run"]:
      marker = _git(root, "show", sha + ":.ci/run")
      from repo_workflow.ci_invocation import parse_invocation
      request = parse_invocation(marker)
      if request.previous_tip != parent:
        raise CiInvocationError("historical CI invocation ancestry mismatch")
    elif changed == [".repoworkflow/validation/testResults-" +
                     _issue_number(root) + ".jsonl"]:
      pass
    else:
      return sha
    sha = parent


def _issue_number(root: Path) -> str:
  import re
  branch = _git(root, "symbolic-ref", "--short", "HEAD")
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
  if match is None:
    raise CiInvocationError("hosted candidate requires an issue branch")
  return match.group(1)


def plan_invocation(root: Path) -> dict[str, str]:
  request = verify_invocation(root)
  invocation_sha = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    text=True,
  ).strip()
  return {
    "stage": request.stage,
    "previous_tip": request.previous_tip,
    "tested_sha": _original_candidate(root, request.previous_tip),
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
