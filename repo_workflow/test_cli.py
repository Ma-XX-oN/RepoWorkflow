"""Unified public test commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import platform
from pathlib import Path
import re
import subprocess

from .git import changed_files, current_branch, git, head_sha
from .local import verify_local

STAGES = {
  "RED": "RED-testing",
  "temporary": "temp-testing",
  "GREEN": "GREEN-testing",
  "regression": "regression-testing",
  "integration": "integration-testing",
}


class TestCommandError(ValueError):
  pass


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    capture_output=True, text=True, check=False,
  )
  if result.returncode:
    raise TestCommandError(result.stderr.strip() or "git operation failed")
  return result.stdout.strip()


def request_remote(root: Path, stage: str) -> int:
  branch = current_branch(root)
  if branch in {"HEAD", "main"} or branch.startswith("prelim-main-"):
    raise TestCommandError("a work branch is required")
  if changed_files(root) or _git(root, "status", "--porcelain", "--untracked-files=all"):
    raise TestCommandError("the working tree must be clean")
  previous_tip = head_sha(root)
  path = root / ".ci" / "run"
  path.parent.mkdir(parents=True, exist_ok=True)
  request = STAGES[stage] + " " + previous_tip + "\n"
  path.write_text(request, encoding="utf-8")
  _git(root, "add", "--", ".ci/run")
  _git(root, "commit", "-m", "test: request " + stage + " from hosted CI")
  _git(root, "push", "origin", "HEAD:refs/heads/" + branch)
  print("Hosted request for " + stage + " committed after " + previous_tip)
  return 0


def results(root: Path, *, remote: bool) -> int:
  match = re.match(r"^issue-([0-9]+)(?:-|$)", current_branch(root))
  if match is None:
    raise TestCommandError("results require an issue branch")
  relative = ".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"
  if remote:
    branch = current_branch(root)
    _git(root, "fetch", "--no-tags", "origin", "refs/heads/" + branch)
    raw = _git(root, "show", "FETCH_HEAD:" + relative)
  else:
    try:
      raw = (root / relative).read_text(encoding="utf-8")
    except OSError as error:
      raise TestCommandError("testing log is unavailable") from error
  if not raw.strip():
    raise TestCommandError("testing log has no recorded results")
  for line in raw.splitlines():
    try:
      record = json.loads(line)
    except json.JSONDecodeError as error:
      raise TestCommandError("invalid testing log record") from error
    if not isinstance(record, dict) or not all(
      field in record for field in ("testSHA", "kind", "result", "runner")
    ):
      raise TestCommandError("incomplete testing log record")
    print(json.dumps(record, sort_keys=True))
  return 0


def run_test(root: Path, stage: str, *, remote: bool, engine_root: Path) -> int:
  if stage == "results":
    return results(root, remote=remote)
  if stage not in STAGES:
    raise TestCommandError("unknown test stage")
  if remote:
    return request_remote(root, stage)
  if stage == "regression":
    before = head_sha(root)
    outcome = verify_local(root, engine_root=engine_root, push=False)
    after = head_sha(root)
    match = re.match(r"^issue-([0-9]+)(?:-|$)", current_branch(root))
    if match is None:
      raise TestCommandError("regression evidence requires an issue branch")
    path = root / ".repoworkflow" / "validation" / (
      "testResults-" + match.group(1) + ".jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "kind": "regression",
      "branch": current_branch(root),
      "testSHA": after,
      "sourceSHA": before,
      "result": {
        "PASS": "succeeded",
        "FAIL": "failed",
        "INCOMPLETE": "incomplete",
      }[outcome],
      "runner": "local",
      "platform": {
        "os": platform.system(),
        "architecture": platform.machine(),
        "runtime": platform.python_version(),
      },
      "hardware": None,
    }
    with path.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(record, sort_keys=True) + "\\n")
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]
  raise TestCommandError(stage + " execution not yet implemented")
