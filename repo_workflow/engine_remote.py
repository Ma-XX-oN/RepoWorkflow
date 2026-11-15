"""Prepare an explicit engine-self version before a hosted marker request."""
from __future__ import annotations

from pathlib import Path
import re
from .version_evidence import tested_source_changed

from .engine_version_adapter import (
  EngineVersionError, read_engine_version, transition_engine_version,
)
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
    while tested_source_changed(root, issue, version, remote=remote):
      transition_engine_version(
        root, operation="task --increment CI-iteration",
      )
      version = read_engine_version(root)
  version = read_engine_version(root)
  if version != before:
    commit_owned_files(
      root, [".ci/engine-version"],
      "chore(test): prepare engine development version " + version,
    )
  return version
