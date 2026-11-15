"""Prepare an explicit engine-self version before a hosted marker request."""
from __future__ import annotations

from pathlib import Path
import re
from .source_tip import source_tip

from .engine_version_adapter import (
  EngineVersionError, read_engine_version, transition_engine_version,
)
from .phase_terminal import plan_phase
from .owned_commit import commit_owned_files
from .process import CommandResult, run_command


class EnginePreparationError(ValueError):
  pass


def _git(root: Path, *args: str, check: bool = True) -> CommandResult:
  result = run_command(["git", "-C", str(root), *args], root)
  if check and result.returncode:
    raise EnginePreparationError("engine Git preparation failed: " + args[0])
  return result


def prepare_engine_request(
  root: Path, *, stage: str, issue: int, remote: str = "origin",
) -> str:
  """Commit a repo-owned version transition before .ci/run, or replay it."""
  if stage not in {"regression", "integration"}:
    raise EnginePreparationError("only terminal phases need version preparation")
  if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
    raise EnginePreparationError("invalid issue identity")
  from .testing_identity import testing_issue
  if testing_issue(root) != issue:
    raise EnginePreparationError("issue branch differs from version authority")
  before = read_engine_version(root)
  stable = re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", before)
  if stable:
    transition_engine_version(root, operation="task --issue", issue=issue)
  else:
    match = re.fullmatch(
      r"[0-9]+\.[0-9]+\.[0-9]+-issue\.([1-9][0-9]*)\.[0-9]+\.(0|[1-9][0-9]*)",
      before,
    )
    if match is None or int(match.group(1)) != issue:
      raise EnginePreparationError("development version belongs to another issue")
    version = before
    if _source_changed_since_testing(root, issue, version, remote=remote):
      transition_engine_version(
        root, operation="task --increment CI-iteration",
      )
  version = read_engine_version(root)
  if version != before:
    commit_owned_files(
      root, [".ci/engine-version"],
      "chore(test): prepare engine development version " + version,
    )
  return version


def _source_changed_since_testing(root: Path, issue: int, version: str,
                                  *, remote: str = "origin") -> bool:
  """Compare verified report identities instead of consuming a terminal tag.

  Parameters
  ----------
  root : Path
      Engine repository.
  issue : int
      Current issue number.
  version : str
      Version being prepared for testing.
  remote : str
      Authoritative remote holding fixed-source terminal tags.

  Returns
  -------
  bool
      Whether this version was tested on different material source.
  """
  from .test_results_reader import parse_testing_log
  from .terminal_tag import _remote_target, _local_target

  log = root / ".repoworkflow/validation" / f"testResults-{issue}.jsonl"
  raw = _git(root, "show", "HEAD:" + log.relative_to(root).as_posix(), check=False)
  records = parse_testing_log(raw.stdout) if raw.returncode == 0 else []
  current = source_tip(root)
  for record in records:
    if record.get("testVersion") == version:
      tested = record.get("testSHA")
      if not isinstance(tested, str) or not re.fullmatch(r"[0-9a-f]{40}", tested):
        raise EnginePreparationError("version report has no exact source identity")
      if source_tip(root, tested) != current:
        return True
  for stage in ("regression", "integration"):
    for outcome in ("PASS", "FAIL"):
      tag = plan_phase(version, phase=stage, outcome=outcome).terminal_tag
      remote_source = _remote_target(root, remote, tag)
      local_source = _local_target(root, tag)
      for tested in {remote_source, local_source} - {None}:
        if _git(root, "cat-file", "-e", tested + "^{commit}", check=False).returncode:
          if tested != remote_source:
            raise EnginePreparationError("local terminal source object unavailable")
          _git(root, "fetch", "--no-tags", remote, "refs/tags/" + tag)
        if source_tip(root, tested) != current:
          return True
  return False
