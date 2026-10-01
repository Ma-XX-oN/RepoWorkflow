from __future__ import annotations

from pathlib import Path
import re

from .git import changed_files, repository_state
from .process import run_command


DEVELOPMENT_VERSION_RE = re.compile(
  r"^\d+\.\d+\.\d+-issue\.\d+\.\d+\.\d+$"
)
STABLE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class VersionAdapterError(RuntimeError):
  pass


def _assert_git_state_unchanged(root: Path, before) -> None:
  after = repository_state(root)
  if after.commit != before.commit:
    raise VersionAdapterError("repository version adapter modified candidate history")
  if after.head_ref != before.head_ref:
    raise VersionAdapterError("repository version adapter modified HEAD reference")
  if after.refs != before.refs:
    raise VersionAdapterError("repository version adapter modified local Git refs")


def _run_adapter(
  root: Path,
  config: dict,
  arguments: list[str],
  *,
  allow_worktree_changes: bool,
) -> str:
  before_state = repository_state(root)
  before_changes = changed_files(root)
  result = run_command([*config["versionCommand"], *arguments], root)
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise VersionAdapterError(
      "repository version adapter failed"
      + (f": {detail}" if detail else "")
    )
  _assert_git_state_unchanged(root, before_state)
  if not allow_worktree_changes and changed_files(root) != before_changes:
    raise VersionAdapterError("repository version query modified the worktree")
  return result.stdout


def _query_version(root: Path, config: dict) -> str:
  stdout = _run_adapter(root, config, [], allow_worktree_changes=False)
  lines = [line.strip() for line in stdout.splitlines() if line.strip()]
  if len(lines) != 1:
    raise VersionAdapterError(
      "repository version adapter must print exactly one version"
    )
  return lines[0]


def read_version(root: Path, config: dict) -> str:
  value = _query_version(root, config)
  if not (
    DEVELOPMENT_VERSION_RE.fullmatch(value)
    or STABLE_VERSION_RE.fullmatch(value)
  ):
    raise VersionAdapterError("repository version adapter printed an invalid version")
  return value


def _read_matching(
  root: Path,
  config: dict,
  pattern: re.Pattern[str],
  label: str,
) -> str:
  value = _query_version(root, config)
  if not pattern.fullmatch(value):
    raise VersionAdapterError(
      f"repository version adapter must print exactly one valid {label}"
    )
  return value


def read_development_version(root: Path, config: dict) -> str:
  return _read_matching(
    root,
    config,
    DEVELOPMENT_VERSION_RE,
    "development version",
  )


def read_stable_version(root: Path, config: dict) -> str:
  return _read_matching(
    root,
    config,
    STABLE_VERSION_RE,
    "stable version",
  )


def run_transition(
  root: Path,
  config: dict,
  *arguments: str,
) -> None:
  if not arguments:
    raise VersionAdapterError("repository version transition requires arguments")
  _run_adapter(
    root,
    config,
    list(arguments),
    allow_worktree_changes=True,
  )
