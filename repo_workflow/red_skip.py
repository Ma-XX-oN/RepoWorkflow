"""Append durable SKIPPED evidence when RED/GREEN has no selected group."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from .git import current_branch, head_sha


def skip_without_selection(root: Path, stage: str, *, remote: bool) -> int:
  warning = (
    "Warning: No RED/GREEN test configured "
    "(.ci/red-green.txt is absent)."
  )
  print(warning, file=sys.stderr)
  print("RED/GREEN testing skipped; no PASS evidence recorded.")
  match = re.fullmatch(
    r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root),
  )
  if match is None:
    raise ValueError("testing evidence requires an issue branch")
  record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "testSHA": head_sha(root),
    "kind": stage,
    "result": "SKIPPED",
    "runner": "local",
    "requested_remote": remote,
    "warning": warning,
    "reason": "selection-file-absent",
    "groups": [],
  }
  path = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
  return 0
