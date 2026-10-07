#!/usr/bin/env python3
from __future__ import annotations

import argparse
import compileall
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.self_ci import group_command


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--groups", nargs="+")
  parser.add_argument("--groups-json")
  args = parser.parse_args()
  if bool(args.groups) == bool(args.groups_json):
    parser.error("provide exactly one of --groups or --groups-json")
  groups = (
    args.groups
    if args.groups is not None
    else json.loads(args.groups_json)
  )
  if not isinstance(groups, list) or not groups or not all(
    isinstance(group, str) and group for group in groups
  ):
    parser.error("selected groups must be a non-empty string array")

  started = time.monotonic()
  RelationshipStore(ROOT).read()
  if not compileall.compile_dir(
    ROOT / "repo_workflow",
    quiet=1,
    force=False,
  ):
    return 1

  evidence = []
  for group in groups:
    command = group_command(ROOT, group)
    result = subprocess.run(
      command,
      cwd=ROOT,
      text=True,
      capture_output=True,
      check=False,
    )
    evidence.append({
      "group": group,
      "command": list(command),
      "returncode": result.returncode,
    })
    if result.stdout:
      print(result.stdout, end="")
    if result.stderr:
      print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
      print(json.dumps({
        "tier": "issue",
        "groups": groups,
        "evidence": evidence,
        "durationSeconds": round(time.monotonic() - started, 3),
      }, separators=(",", ":")))
      return 1

  print(json.dumps({
    "tier": "issue",
    "groups": groups,
    "evidence": evidence,
    "durationSeconds": round(time.monotonic() - started, 3),
  }, separators=(",", ":")))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
