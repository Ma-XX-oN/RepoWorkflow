#!/usr/bin/env python3
"""Fail closed unless hosted testing wrote exact-candidate stage evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

STAGES = {
  "RED-testing": "RED",
  "temp-testing": "temporary",
  "GREEN-testing": "GREEN",
  "regression-testing": "regression",
  "integration-testing": "integration",
}


def validate_result(
  root: Path, *, stage: str, candidate: str, branch: str,
) -> None:
  kind = STAGES.get(stage)
  if kind is None:
    raise ValueError("unknown hosted stage")
  if re.fullmatch(r"[0-9a-f]{40}", candidate) is None:
    raise ValueError("invalid candidate SHA")
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
  if match is None:
    raise ValueError("hosted result requires an issue branch")
  path = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  try:
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
  except (OSError, ValueError, IndexError) as error:
    raise ValueError("missing or malformed hosted test result") from error
  if not isinstance(record, dict):
    raise ValueError("hosted result must be an object")
  if (
    record.get("testSHA") != candidate
    or record.get("kind") != kind
    or record.get("result") != "succeeded"
  ):
    raise ValueError("incomplete or skipped hosted testing")
  if (
    record.get("headChangedDuringTest") is True
    or record.get("uncommittedChanges", []) != []
    or record.get("reusable") is not True
  ):
    raise ValueError("hosted PASS does not bind to clean candidate")
  if kind in {"GREEN", "temporary", "RED"}:
    groups = record.get("groups")
    if not isinstance(groups, list) or not groups:
      raise ValueError("hosted group evidence missing")
    if not all(
      isinstance(group, dict)
      and isinstance(group.get("group"), str)
      and group.get("exit_code") == 0
      for group in groups
    ):
      raise ValueError("hosted group evidence is incomplete")
  if kind == "GREEN":
    selection = root / ".ci" / "red-green.txt"
    try:
      selected = selection.read_text(encoding="utf-8").strip()
    except OSError as error:
      raise ValueError("hosted GREEN selection missing") from error
    if [group["group"] for group in groups] != [selected]:
      raise ValueError("hosted GREEN selection does not match result")


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("stage")
  parser.add_argument("candidate")
  parser.add_argument("branch")
  args = parser.parse_args()
  try:
    validate_result(
      Path.cwd(), stage=args.stage, candidate=args.candidate,
      branch=args.branch,
    )
  except ValueError as error:
    print(str(error), file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
