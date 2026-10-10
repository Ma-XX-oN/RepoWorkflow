"""Local integration: authoritative regression plus current-platform probes.

One local platform PASS never represents the full hosted platform matrix.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from .git import current_branch, head_sha
from .test_regression_engine import self_regression

PROBES = (
  ("argv-limits", "probe-argv-limits.py"),
  ("graph-renderer-platform", "probe-graph-renderer.py"),
  ("ticket-merge-platform", "probe-ticket-merge.py"),
)


def _dirty(root: Path, evidence: Path) -> list[str]:
  output = subprocess.run(
    ["git", "-C", str(root), "status", "--porcelain=v1", "-z",
     "--untracked-files=all"],
    check=True, capture_output=True,
  ).stdout.decode("utf-8", "surrogateescape")
  relative = evidence.relative_to(root).as_posix()
  entries = output.split("\0")
  paths: set[str] = set()
  index = 0
  while index < len(entries):
    entry = entries[index]
    index += 1
    if not entry:
      continue
    if len(entry) < 4 or entry[2] != " ":
      raise ValueError("malformed integration working-tree status")
    paths.add(entry[3:])
    if "R" in entry[:2] or "C" in entry[:2]:
      if index >= len(entries) or not entries[index]:
        raise ValueError("incomplete integration rename record")
      paths.add(entries[index])
      index += 1
  return sorted(paths - {relative})


def _probe(engine_root: Path, filename: str) -> int:
  completed = subprocess.run(
    [sys.executable, str(engine_root / "scripts" / filename)],
    cwd=engine_root, capture_output=True, text=True, check=False,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
  )
  if completed.stdout:
    print(completed.stdout, end="")
  if completed.stderr:
    print(completed.stderr, end="", file=sys.stderr)
  return completed.returncode


def run_local_integration(root: Path, *, engine_root: Path) -> int:
  """Record one locally executed platform result, never an entire matrix."""
  root = root.resolve()
  engine_root = engine_root.resolve()
  if root != engine_root:
    raise ValueError(
      "consumer integration requires an authoritative environment adapter"
    )
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise ValueError("integration requires a current issue branch")
  log = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  candidate = head_sha(root)
  before_dirty = _dirty(root, log)
  regression = self_regression(root)
  observations = [{
    "group": "regression",
    "exit_code": 0 if regression == "PASS" else 1,
  }]
  if regression == "PASS":
    with ThreadPoolExecutor(max_workers=len(PROBES)) as pool:
      futures = [
        (name, pool.submit(_probe, engine_root, script))
        for name, script in PROBES
      ]
      for name, future in futures:
        observations.append({
          "group": name, "exit_code": future.result(),
        })
  dirty = sorted(set(before_dirty) | set(_dirty(root, log)))
  history_changed = head_sha(root) != candidate
  success = (
    regression == "PASS"
    and len(observations) == len(PROBES) + 1
    and all(item["exit_code"] == 0 for item in observations)
  )
  record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "kind": "integration",
    "branch": current_branch(root),
    "testSHA": candidate,
    "sourceSHA": candidate,
    "runner": "local",
    "platform": {
      "os": platform.system(),
      "architecture": platform.machine(),
      "runtime": platform.python_version(),
    },
    "hardware": None,
    "uncommittedChanges": dirty,
    "headChangedDuringTest": history_changed,
    "reusable": success and not dirty and not history_changed,
    "result": (
      "succeeded" if success else
      "incomplete" if regression == "INCOMPLETE" else "failed"
    ),
    "groups": observations,
  }
  log.parent.mkdir(parents=True, exist_ok=True)
  with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
  return 0 if success else 2 if regression == "INCOMPLETE" else 1
