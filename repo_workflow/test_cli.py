"""Unified public test commands."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
import platform
from pathlib import Path
import re
import subprocess

from .git import changed_files, current_branch, git, head_sha
from .local import verify_local
from .self_ci import group_command
from .test_catalogue import load_test_catalogue

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


SELECTION = Path(".ci/red-green.txt")


def _issue_prefix(root: Path) -> str:
  match = re.fullmatch(
    r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root),
  )
  if match is None:
    raise TestCommandError("RED/GREEN requires a current issue branch")
  return "issue-" + match.group(1) + "-"


def _validate_selection(root: Path, name: str) -> str:
  prefix = _issue_prefix(root)
  if (
    not name.startswith(prefix)
    or name not in load_test_catalogue(root).groups
  ):
    raise TestCommandError(
      "RED/GREEN tests do not exist for this selection. "
      "Build and register issue-N- groups in .ci/tests.json."
    )
  return name


def read_selection(root: Path) -> str | None:
  path = root / SELECTION
  try:
    raw = path.read_text(encoding="utf-8")
  except FileNotFoundError:
    return None
  lines = raw.splitlines()
  if len(lines) != 1 or raw != lines[0] + "\n" or not lines[0]:
    raise TestCommandError(
      ".ci/red-green.txt must contain exactly one test-group name"
    )
  return _validate_selection(root, lines[0])


def _skip_without_selection() -> int:
  print(
    "Warning: No RED/GREEN test configured "
    "(.ci/red-green.txt is absent).",
    file=__import__("sys").stderr,
  )
  print("RED/GREEN testing skipped; no PASS evidence recorded.")
  return 0


def select_group(root: Path, name: str) -> str:
  name = _validate_selection(root, name)
  path = root / SELECTION
  if path.exists() and path.read_text(encoding="utf-8") == name + "\n":
    return name
  if _git(root, "status", "--porcelain", "--untracked-files=all"):
    raise TestCommandError(
      "commit or discard working tree changes before selecting RED test"
    )
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(name + "\n", encoding="utf-8")
  _git(root, "add", "--", SELECTION.as_posix())
  _git(root, "commit", "-m", "test: select RED/GREEN group " + name)
  return name


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


def _run_group_set(
  root: Path, stage: str, groups: tuple[str, ...], *,
  catalogue_path: Path = Path(".ci/tests.json"),
) -> int:
  if not groups:
    raise TestCommandError(
      "RED/GREEN tests do not exist. Build and register "
      "issue-N- test groups in .ci/tests.json."
      if stage == "GREEN" else "no temporary test groups in .ci/temp-tests.json"
    )
  revision = head_sha(root)
  failures = []
  evidence = []
  for group in groups:
    command = group_command(root, group, catalogue_path)
    completed = subprocess.run(
      command, cwd=root, capture_output=True, text=True, check=False,
      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.stdout:
      print(completed.stdout, end="")
    if completed.stderr:
      import sys
      print(completed.stderr, end="", file=sys.stderr)
    evidence.append({"group": group, "exit_code": completed.returncode})
    if completed.returncode:
      failures.append(group)
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TestCommandError("testing log requires an issue branch")
  path = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  path.parent.mkdir(parents=True, exist_ok=True)
  record = {
    "testSHA": revision,
    "kind": stage,
    "result": "failed" if failures else "succeeded",
    "runner": "local",
    "platform": {"os": platform.system(), "runtime": platform.python_version()},
    "groups": evidence,
  }
  with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
  return 1 if failures else 0


def run_test(
  root: Path, stage: str, *, remote: bool, engine_root: Path,
  group: str | None = None,
) -> int:
  if stage == "results":
    return results(root, remote=remote)
  if stage not in STAGES:
    raise TestCommandError("unknown test stage")
  if stage == "RED":
    selected = select_group(root, group) if group else read_selection(root)
    if selected is None:
      return _skip_without_selection()
    if remote:
      return request_remote(root, stage)
    command = group_command(root, selected)
    result = subprocess.run(
      command, cwd=root, text=True, capture_output=True, check=False,
      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.stdout:
      print(result.stdout, end="")
    if result.stderr:
      import sys
      print(result.stderr, end="", file=sys.stderr)
    if result.returncode == 0:
      raise TestCommandError("RED did not demonstrate the expected failure")
    raise TestCommandError(
      "RED failed; expected RED failure has not been distinguished "
      "from infrastructure error"
    )
  if group is not None:
    raise TestCommandError("test group is only supported for RED")
  if stage == "GREEN":
    selected = read_selection(root)
    if selected is None:
      return _skip_without_selection()
    if remote:
      return request_remote(root, stage)
    return _run_group_set(root, stage, (selected,))
  if not remote and stage == "temporary":
    manifest = Path(".ci/temp-tests.json")
    groups = tuple(sorted(load_test_catalogue(
      root, catalogue_path=manifest,
    ).groups))
    return _run_group_set(root, stage, groups, catalogue_path=manifest)
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
      handle.write(json.dumps(record, sort_keys=True) + "\n")
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]
  raise TestCommandError(stage + " execution not yet implemented")
