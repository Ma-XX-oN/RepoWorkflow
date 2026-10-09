#!/usr/bin/env python3
"""Publish hosted test observations as a single-file fast-forward commit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )
  if result.returncode:
    raise ValueError("git " + args[0] + " failed: " + result.stderr.strip())
  return result.stdout.strip()


def publish(
  root: Path, *, branch: str, invocation: str,
  candidate: str, stage: str, run_id: str,
) -> None:
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
  if match is None:
    raise ValueError("publication requires a current issue branch")
  if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (
    invocation, candidate,
  )):
    raise ValueError("publication requires exact commit SHAs")
  if not run_id.isdecimal() or int(run_id) < 1:
    raise ValueError("publication requires a provider run ID")
  if stage not in {
    "RED-testing", "temp-testing", "GREEN-testing",
    "regression-testing", "integration-testing",
  }:
    raise ValueError("publication requires a known testing stage")
  relative = (
    ".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"
  )
  path = root / relative
  try:
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
  except (OSError, ValueError, IndexError) as error:
    raise ValueError("cannot publish absent or malformed observations") from error
  if (
    not isinstance(record, dict)
    or record.get("testSHA") != candidate
    or record.get("kind") != {
      "RED-testing": "RED",
      "temp-testing": "temporary",
      "GREEN-testing": "GREEN",
      "regression-testing": "regression",
      "integration-testing": "integration",
    }[stage]
  ):
    raise ValueError("latest observation does not bind requested candidate")
  if _git(root, "rev-parse", "HEAD") != candidate:
    raise ValueError("testing modified checkout history")
  local_dirty = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
  if any(line[3:] != relative for line in local_dirty.splitlines() if line):
    raise ValueError("unexpected test side effects prevent publication")
  record["runner"] = "github-actions"
  record["providerRunId"] = int(run_id)
  record["providerInvocationSHA"] = invocation
  record["providerCandidateSHA"] = candidate
  record["providerStage"] = stage
  original = "\\n".join([
    *lines[:-1], json.dumps(record, sort_keys=True),
  ]) + "\\n"
  _git(root, "fetch", "--no-tags", "origin", "refs/heads/" + branch)
  if _git(root, "rev-parse", "FETCH_HEAD") != invocation:
    raise ValueError("remote branch moved since hosted invocation")
  if _git(root, "rev-parse", "FETCH_HEAD^") != candidate:
    raise ValueError("remote invocation parent differs from tested candidate")
  _git(root, "merge", "--ff-only", "FETCH_HEAD")
  # The evidence file is the only publication change. Preserve all observations.
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(original, encoding="utf-8")
  _git(root, "config", "user.name", "github-actions[bot]")
  _git(root, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
  _git(root, "add", "--", relative)
  _git(root, "commit", "--only", "-m",
       "test: publish hosted evidence from run " + run_id, "--", relative)
  _git(root, "push", "origin", "HEAD:refs/heads/" + branch)


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("stage")
  parser.add_argument("candidate")
  parser.add_argument("branch")
  parser.add_argument("invocation")
  parser.add_argument("run_id")
  args = parser.parse_args()
  try:
    publish(
      Path.cwd(), stage=args.stage, candidate=args.candidate,
      branch=args.branch, invocation=args.invocation, run_id=args.run_id,
    )
  except ValueError as error:
    print(str(error), file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
