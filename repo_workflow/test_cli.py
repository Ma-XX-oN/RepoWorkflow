"""Unified public test commands."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
import platform
from pathlib import Path
import re
import subprocess
import sys

from .git import changed_files, current_branch, git, head_sha
from .local import verify_local
from .config import load_config
from .terminal_tag import publish_terminal_tag
from .retry_evidence import isolate_retry_evidence
from .engine_remote import prepare_engine_request
from .engine_version_adapter import read_engine_version
from .test_regression_engine import self_regression
from .test_integration_engine import run_local_integration
from .test_cache import reusable_local_group_passes
from .hosted_cache import verified_hosted_passes
from .self_ci import group_command
from .test_catalogue import load_test_catalogue
from .red_expected import assertion_failure
from .red_skip import skip_without_selection

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
  if len(lines) != 1 or raw not in (lines[0], lines[0] + "\n") or not lines[0]:
    raise TestCommandError(
      ".ci/red-green.txt must contain exactly one test-group name"
    )
  return _validate_selection(root, lines[0])


def _skip_without_selection(
  root: Path, stage: str, *, remote: bool,
) -> int:
  try:
    return skip_without_selection(root, stage, remote=remote)
  except ValueError as error:
    raise TestCommandError(str(error)) from error

def select_group(root: Path, name: str) -> str:
  name = _validate_selection(root, name)
  path = root / SELECTION
  if path.exists() and path.read_text(encoding="utf-8") == name + "\n":
    return name
  match = re.fullmatch(
    r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root),
  )
  if match is None:
    raise TestCommandError("RED selection requires an issue branch")
  audit = ".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"
  if any(changed != audit for changed in changed_files(root)):
    raise TestCommandError(
      "commit or discard working tree changes before selecting RED test"
    )
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(name + "\n", encoding="utf-8")
  _git(root, "add", "--", SELECTION.as_posix())
  _git(
    root, "commit", "--only", "-m",
    "test: select RED/GREEN group " + name, "--", SELECTION.as_posix(),
  )
  return name


def request_remote(root: Path, stage: str, *, engine_root: Path | None = None) -> int:
  branch = current_branch(root)
  if branch in {"HEAD", "main"} or branch.startswith("prelim-main-"):
    raise TestCommandError("a work branch is required")
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
  if match is None:
    raise TestCommandError("a current issue branch is required")
  audit = ".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"
  if any(path != audit for path in changed_files(root)):
    raise TestCommandError("the working tree must be clean")
  if engine_root is not None and root.resolve() == engine_root.resolve() and stage in {"regression", "integration"}:
    prepare_engine_request(root, stage=stage, issue=int(match.group(1)))
  previous_tip = head_sha(root)
  path = root / ".ci" / "run"
  path.parent.mkdir(parents=True, exist_ok=True)
  request = STAGES[stage] + " " + previous_tip + "\n"
  path.write_text(request, encoding="utf-8")
  _git(root, "add", "--", ".ci/run")
  _git(
    root, "commit", "--only", "-m",
    "test: request " + stage + " from hosted CI", "--", ".ci/run",
  )
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
  validated = []
  for line in raw.splitlines():
    try:
      record = json.loads(line)
    except json.JSONDecodeError as error:
      raise TestCommandError("invalid testing log record") from error
    if not isinstance(record, dict) or not all(
      field in record for field in ("testSHA", "kind", "result", "runner")
    ):
      raise TestCommandError("incomplete testing log record")
    validated.append(record)
  for record in validated:
    print(json.dumps(record, sort_keys=True))
  return 0


def _group_fingerprint(root: Path, catalogue_path: Path) -> str:
  path = root / catalogue_path
  try:
    catalogue_bytes = path.read_bytes()
  except OSError as error:
    raise TestCommandError("test catalogue cannot be fingerprinted") from error
  return hashlib.sha256(catalogue_bytes).hexdigest()


def _uncommitted_inputs(root: Path, evidence_path: Path) -> list[str]:
  # The append-only evidence log does not count as a changed test input.
  status = subprocess.run(
    ["git", "-C", str(root), "status", "--porcelain", "-z",
     "--untracked-files=all"],
    capture_output=True, check=False,
  )
  if status.returncode:
    raise TestCommandError("cannot inspect working-tree changes")
  relative_evidence = evidence_path.relative_to(root).as_posix()
  entries = status.stdout.decode("utf-8", errors="surrogateescape").split("\0")
  return sorted({
    entry[3:] for entry in entries
    if entry and entry[3:] != relative_evidence
  })


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
  fingerprint = _group_fingerprint(root, catalogue_path)
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root))
  if match is None:
    raise TestCommandError("testing log requires an issue branch")
  path = root / ".repoworkflow" / "validation" / (
    "testResults-" + match.group(1) + ".jsonl"
  )
  uncommitted_before = _uncommitted_inputs(root, path)
  reusable = (
    reusable_local_group_passes(
      path, stage=stage, revision=revision, fingerprint=fingerprint,
    )
    if not uncommitted_before
    else set()
  )
  if not uncommitted_before and os.environ.get("GITHUB_ACTIONS") == "true":
    # Only an independently verified GitHub run may authorise hosted reuse.
    reusable |= verified_hosted_passes(
      root, stage=stage, revision=revision, fingerprint=fingerprint,
      invocation=os.environ.get("GITHUB_SHA", ""),
      branch=os.environ.get("GITHUB_REF_NAME", ""),
      repository=os.environ.get("GITHUB_REPOSITORY", ""),
      token=os.environ.get("GITHUB_TOKEN", ""),
    )
  failures = []
  evidence = []
  for group in groups:
    if group in reusable:
      print("Reusing valid PASS evidence for " + group)
      evidence.append({
        "group": group, "exit_code": 0, "reused": True,
      })
      continue
    command = group_command(root, group, catalogue_path)
    completed = subprocess.run(
      command, cwd=root, capture_output=True, text=True, check=False,
      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.stdout:
      print(completed.stdout, end="")
    if completed.stderr:
      print(completed.stderr, end="", file=sys.stderr)
    evidence.append({
      "group": group, "exit_code": completed.returncode, "reused": False,
    })
    if completed.returncode:
      failures.append(group)
  uncommitted = sorted(set(uncommitted_before) | set(
    _uncommitted_inputs(root, path)
  ))
  head_changed = head_sha(root) != revision
  path.parent.mkdir(parents=True, exist_ok=True)
  record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "branch": current_branch(root),
    "uncommittedChanges": uncommitted,
    "headChangedDuringTest": head_changed,
    "reusable": not failures and not uncommitted and not head_changed,
    "testSHA": revision,
    "catalogueSHA256": fingerprint,
    "kind": stage,
    "result": "failed" if failures else "succeeded",
    "runner": "local",
    "platform": {"os": platform.system(), "architecture": platform.machine(),
                 "runtime": platform.python_version()},
    "groups": evidence,
  }
  with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
  return 1 if failures else 0


def _assert_no_temporary_issue_sandbox(root: Path) -> None:
  match = re.fullmatch(
    r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root),
  )
  if match is None:
    raise TestCommandError("integration requires a current issue branch")
  sandbox = root / ".ci" / "temp-tests" / match.group(1)
  if sandbox.exists() or sandbox.is_symlink():
    raise TestCommandError(
      "integration requires complete removal of temporary test sandbox "
      + sandbox.relative_to(root).as_posix()
      + " (including sources, fixtures and build files)"
    )


def _consumer_retry_verify(
  root: Path, engine_root: Path, prepared: list[tuple[str, str]],
) -> str:
  match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?",
                       current_branch(root))
  if match is None:
    raise TestCommandError("consumer regression requires an issue branch")
  with isolate_retry_evidence(root, int(match.group(1))):
    return verify_local(
      root, engine_root=engine_root, push=False, tag_result=False,
      candidate_observer=lambda sha, version: prepared.append((sha, version)),
    )


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
      return _skip_without_selection(root, stage, remote=remote)
    if remote:
      return request_remote(root, stage, engine_root=engine_root)
    command = group_command(root, selected)
    match = re.fullmatch(
      r"issue-([1-9][0-9]*)(?:-.*)?", current_branch(root),
    )
    if match is None:
      raise TestCommandError("RED evidence requires an issue branch")
    path = root / ".repoworkflow" / "validation" / (
      "testResults-" + match.group(1) + ".jsonl"
    )
    before = _uncommitted_inputs(root, path)
    red_candidate = head_sha(root)
    red_catalogue = _group_fingerprint(root, Path(".ci/tests.json"))
    result = subprocess.run(
      command, cwd=root, text=True, capture_output=True, check=False,
      env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.stdout:
      print(result.stdout, end="")
    if result.stderr:
      print(result.stderr, end="", file=sys.stderr)
    after_dirty = _uncommitted_inputs(root, path)
    dirty = sorted(set(before) | set(after_dirty))
    head_changed = head_sha(root) != red_candidate
    demonstrated = (
      assertion_failure(command, result.returncode, result.stderr)
      and not head_changed and set(after_dirty).issubset(before)
    )
    record = {
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "testSHA": red_candidate,
      "branch": current_branch(root),
      "headChangedDuringTest": head_changed,
      "catalogueSHA256": red_catalogue,
      "kind": "RED",
      "result": "succeeded" if demonstrated else "incomplete",
      "expectedFailure": demonstrated,
      "reason": (
        "expected-red-assertion-demonstrated" if demonstrated
        else "expected-red-failure-not-demonstrated"
        if result.returncode == 0
        else "failure-not-classified-as-expected-red"
      ),
      "runner": "local",
      "platform": {
        "os": platform.system(), "architecture": platform.machine(),
        "runtime": platform.python_version(),
      },
      "uncommittedChanges": dirty,
      "reusable": False,
      "groups": [{
        "group": selected, "exit_code": result.returncode,
        "reused": False,
      }],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(record, sort_keys=True) + "\n")
    if demonstrated:
      return 0
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
      return _skip_without_selection(root, stage, remote=remote)
    if remote:
      return request_remote(root, stage, engine_root=engine_root)
    return _run_group_set(root, stage, (selected,))
  if stage == "temporary":
    manifest = Path(".ci/temp-tests.json")
    groups = tuple(sorted(load_test_catalogue(
      root, catalogue_path=manifest,
    ).groups))
    if not groups:
      raise TestCommandError("no temporary test groups in .ci/temp-tests.json")
    if remote:
      for name in groups:
        group_command(root, name, manifest)
      return request_remote(root, stage, engine_root=engine_root)
    return _run_group_set(root, stage, groups, catalogue_path=manifest)
  if remote:
    return request_remote(root, stage, engine_root=engine_root)
  if stage == "integration":
    _assert_no_temporary_issue_sandbox(root)
    return run_local_integration(root, engine_root=engine_root)
  if stage == "regression":
    temporary = Path(".ci/temp-tests.json")
    selected = ()
    if (root / temporary).exists():
      selected = tuple(sorted(load_test_catalogue(
        root, catalogue_path=temporary,
      ).groups))
      for name in selected:
        # Validate every selected harness before transactional verification.
        group_command(root, name, temporary)
    before = head_sha(root)
    prepared: list[tuple[str, str]] = []
    outcome = (
      self_regression(root)
      if root.resolve() == engine_root.resolve()
      else _consumer_retry_verify(root, engine_root, prepared)
    )
    after = head_sha(root)
    if outcome == "PASS" and selected and _run_group_set(
      root, "temporary", selected, catalogue_path=temporary,
    ):
      outcome = "FAIL"
    match = re.match(r"^issue-([0-9]+)(?:-|$)", current_branch(root))
    if match is None:
      raise TestCommandError("regression evidence requires an issue branch")
    path = root / ".repoworkflow" / "validation" / (
      "testResults-" + match.group(1) + ".jsonl"
    )
    uncommitted = _uncommitted_inputs(root, path)
    tested_sha = prepared[0][0] if prepared else before
    head_changed = head_sha(root) != tested_sha
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
      "uncommittedChanges": uncommitted,
      "headChangedDuringTest": head_changed,
      "reusable": (
        outcome == "PASS" and not uncommitted and not head_changed
      ),
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "kind": "regression",
      "branch": current_branch(root),
      "testSHA": tested_sha,
      "sourceSHA": before,
      **({"testVersion": prepared[0][1]} if prepared else
         {"testVersion": read_engine_version(root)}
         if root.resolve() == engine_root.resolve()
         and (root / ".ci/engine-version").is_file() else {}),
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
    if prepared and outcome in {"PASS", "FAIL"} and not (
      uncommitted or head_changed
    ):
      remote_name = load_config(root)["repository"]["authoritativeRemote"]
      publish_terminal_tag(
        root, stage="regression", remote=remote_name,
        version=prepared[0][1], candidate=tested_sha,
        outcome=outcome, canonical_log=path, push=False,
      )
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]
  raise TestCommandError(stage + " execution not yet implemented")
