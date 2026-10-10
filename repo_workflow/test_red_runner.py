"""RED execution and canonical evidence with optional predeclared expectations."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Callable

from .git import head_sha
from .test_red_classification import (
  RedExpectation, RedObservation, classify_red,
)
from .test_results_reader import TestCommandError


def record_red(
  root: Path, selected: str, command: tuple[str, ...],
  path: Path, fingerprint: str, *,
  dirty_inputs: Callable[[Path, Path], list[str]],
  expectation: RedExpectation | None = None,
) -> int:
  """Execute and audit one selected group against its source candidate."""
  if expectation is not None:
    preflight = classify_red(
      expectation, RedObservation(None, "", "", False),
    )
    if preflight.reason == "invalid-expected-failure-declaration":
      raise TestCommandError(preflight.reason)
  before = dirty_inputs(root, path)
  candidate = head_sha(root)
  try:
    result = subprocess.run(
      command, cwd=root, text=True, capture_output=True, check=False,
      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
  except (OSError, UnicodeError):
    result = None
  if result is not None and result.stdout:
    print(result.stdout, end="")
  if result is not None and result.stderr:
    print(result.stderr, end="", file=sys.stderr)
  dirty = sorted(set(before) | set(dirty_inputs(root, path)))
  if result is None:
    status = "INCOMPLETE"
    reason = "selected-test-cannot-execute"
  elif expectation is None:
    status = "INCOMPLETE"
    reason = (
      "expected-red-failure-not-demonstrated" if result.returncode == 0
      else "failure-not-classified-as-expected-red"
    )
  else:
    decision = classify_red(
      expectation,
      RedObservation(result.returncode, result.stdout, result.stderr, True),
    )
    status, reason = decision.status, decision.reason
  record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "testSHA": candidate,
    "headChangedDuringTest": head_sha(root) != candidate,
    "catalogueSHA256": fingerprint,
    "kind": "RED",
    "result": (
      "succeeded" if status == "RED" else
      "failed" if status in {"NOT_RED", "FAIL"} else "incomplete"
    ),
    "reason": reason,
    "runner": "local",
    "platform": {
      "os": platform.system(), "architecture": platform.machine(),
      "runtime": platform.python_version(),
    },
    "uncommittedChanges": dirty,
    "reusable": False,
    "groups": [{
      "group": selected,
      "exit_code": result.returncode if result is not None else None,
      "reused": False,
    }],
  }
  if expectation is not None:
    record["redStatus"] = status
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
  if status == "RED":
    return 0
  if result is None:
    raise TestCommandError("RED selected test could not execute")
  if status == "NOT_RED" or result.returncode == 0:
    raise TestCommandError("RED did not demonstrate the expected failure")
  raise TestCommandError(
    "RED failed; expected RED failure has not been distinguished "
    "from infrastructure error" if expectation is None else reason
  )
