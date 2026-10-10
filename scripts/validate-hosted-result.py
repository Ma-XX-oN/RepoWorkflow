#!/usr/bin/env python3
"""Fail closed unless hosted testing wrote exact-candidate stage evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repo_workflow.test_results_reader import parse_testing_log
from repo_workflow.test_red_declaration import red_declaration

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
    record = parse_testing_log(path.read_text(encoding="utf-8"))[-1]
  except (OSError, ValueError, IndexError) as error:
    raise ValueError("missing or malformed hosted test result") from error
  if not isinstance(record, dict):
    raise ValueError("hosted result must be an object")
  if (
    record.get("testSHA") != candidate
    or record.get("branch") != branch
    or record.get("kind") != kind
    or record.get("result") != "succeeded"
  ):
    raise ValueError("incomplete or skipped hosted testing")
  if (
    record.get("headChangedDuringTest") is not False
    or record.get("uncommittedChanges") != []
    or record.get("reusable") is not (False if kind == "RED" else True)
  ):
    raise ValueError("hosted PASS does not bind to clean candidate")
  platform = record.get("platform")
  if not isinstance(platform, dict) or any(
    not isinstance(platform.get(field), str) or not platform[field]
    for field in ("os", "architecture", "runtime")
  ):
    raise ValueError("hosted result lacks complete platform identity")
  if kind in {"GREEN", "temporary", "RED"}:
    groups = record.get("groups")
    if not isinstance(groups, list) or not groups:
      raise ValueError("hosted group evidence missing")
    if not all(
      isinstance(group, dict)
      and isinstance(group.get("group"), str)
      and type(group.get("exit_code")) is int
      and (group["exit_code"] > 0 if kind == "RED" else group["exit_code"] == 0)
      for group in groups
    ):
      raise ValueError("hosted group evidence is incomplete")
  if record.get("runner") != "local":
    raise ValueError("hosted pre-publication result is not local execution")
  if kind in {"RED", "GREEN"}:
    selection = root / ".ci" / "red-green.txt"
    try:
      raw = selection.read_text(encoding="utf-8")
    except OSError as error:
      raise ValueError("hosted RED/GREEN selection missing") from error
    selected = raw.removesuffix("\n")
    if not selected or raw not in {selected, selected + "\n"} or (
      "\n" in selected or "\r" in selected
    ):
      raise ValueError("hosted RED/GREEN selection is malformed")
    if [group["group"] for group in groups] != [selected]:
      raise ValueError("hosted RED/GREEN selection does not match result")
    if kind == "RED":
      expected, problem = red_declaration(root, selected)
      if problem or expected is None or (
        record.get("redStatus") != "RED"
        or record.get("reason") != "declared-behavioural-failure-observed"
        or groups[0]["exit_code"] != expected.exit_code
      ):
        raise ValueError("hosted RED expected failure evidence mismatch")
  if kind == "temporary":
    try:
      manifest = json.loads(
        (root / ".ci/temp-tests.json").read_text(encoding="utf-8")
      )
      declared = [
        name for entry in manifest["tests"]
        for name in entry if name not in {"test-harness", "command"}
      ]
    except (OSError, ValueError, KeyError, TypeError) as error:
      raise ValueError("hosted temporary test manifest is malformed") from error
    if not declared or sorted(declared) != sorted(
      group["group"] for group in groups
    ):
      raise ValueError("hosted temporary test groups are incomplete")


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
