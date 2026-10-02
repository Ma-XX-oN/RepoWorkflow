from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile

from .git import (
  changed_files,
  git,
  head_sha,
  repository_state,
  restore_repository_state,
)
from .process import run_command


DEVELOPMENT_VERSION_RE = re.compile(
  r"^(\d+)\.(\d+)\.(\d+)-issue\.(\d+)\.(\d+)\.(\d+)$"
)
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class VersionAdapterError(RuntimeError):
  pass


def _git_dir(root: Path) -> Path:
  value = git(root, "rev-parse", "--git-dir").stdout.strip()
  path = Path(value)
  return path if path.is_absolute() else (root / path).resolve()


def _transition_marker_path(root: Path) -> Path:
  return _git_dir(root) / "repoworkflow" / "version-transition.json"


def _write_transition_marker(
  root: Path,
  *,
  before: str,
  after: str,
  paths: list[str],
) -> None:
  marker = _transition_marker_path(root)
  marker.parent.mkdir(parents=True, exist_ok=True)
  marker.write_text(
    json.dumps({
      "candidate": head_sha(root),
      "before": before,
      "after": after,
      "changedFiles": paths,
    }, sort_keys=True) + "\n",
    encoding="utf-8",
  )


def transition_marker(root: Path) -> dict | None:
  try:
    value = json.loads(_transition_marker_path(root).read_text(encoding="utf-8"))
  except (FileNotFoundError, json.JSONDecodeError):
    return None
  if not isinstance(value, dict):
    return None
  if set(value) != {"candidate", "before", "after", "changedFiles"}:
    return None
  if not isinstance(value["changedFiles"], list):
    return None
  return value


def read_head_version(root: Path, config: dict) -> str:
  root = root.resolve()
  with tempfile.TemporaryDirectory() as td:
    worktree = Path(td) / "head"
    git(root, "worktree", "add", "--detach", "--force", str(worktree), "HEAD")
    try:
      return read_version(worktree, config)
    finally:
      git(root, "worktree", "remove", "--force", str(worktree), check=False)


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
  if allow_worktree_changes and before_changes:
    raise VersionAdapterError(
      "repository version transition requires a clean worktree"
    )
  result = run_command([*config["versionCommand"], *arguments], root)
  if result.returncode:
    if allow_worktree_changes:
      restore_repository_state(root, before_state)
    detail = (result.stderr or result.stdout).strip()
    raise VersionAdapterError(
      "repository version adapter failed"
      + (f": {detail}" if detail else "")
    )
  try:
    _assert_git_state_unchanged(root, before_state)
  except VersionAdapterError:
    if allow_worktree_changes:
      restore_repository_state(root, before_state)
    raise
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


def _expected_transition(before: str, arguments: tuple[str, ...]) -> str:
  stable = STABLE_VERSION_RE.fullmatch(before)
  development = DEVELOPMENT_VERSION_RE.fullmatch(before)

  if len(arguments) == 3 and arguments[:2] == ("task", "--issue"):
    if stable is None:
      raise VersionAdapterError("task initialization requires a stable version")
    issue = int(arguments[2])
    if issue < 1:
      raise VersionAdapterError("task issue number must be positive")
    return f"{before}-issue.{issue}.0.1"

  if arguments == ("task", "--increment", "CI-iteration"):
    if development is None:
      raise VersionAdapterError("CI iteration increment requires a task version")
    base = ".".join(development.group(i) for i in range(1, 4))
    issue, generation, iteration = (
      int(development.group(4)),
      int(development.group(5)),
      int(development.group(6)),
    )
    return f"{base}-issue.{issue}.{generation}.{iteration + 1}"

  if arguments == ("task", "--increment", "merge-integration-failed"):
    if development is None:
      raise VersionAdapterError(
        "integration-failure increment requires a task version"
      )
    base = ".".join(development.group(i) for i in range(1, 4))
    issue = int(development.group(4))
    generation = int(development.group(5))
    return f"{base}-issue.{issue}.{generation + 1}.1"

  if arguments in (
    ("integrate", "--increment", "patch"),
    ("integrate", "--increment", "minor"),
  ):
    if stable is None:
      raise VersionAdapterError("integration increment requires a stable version")
    major, minor, patch = (int(stable.group(i)) for i in range(1, 4))
    if arguments[-1] == "patch":
      patch += 1
    else:
      minor += 1
      patch = 0
    return f"{major}.{minor}.{patch}"

  if arguments == ("release-major",):
    if stable is None:
      raise VersionAdapterError("major release requires a stable version")
    major = int(stable.group(1)) + 1
    return f"{major}.0.0"

  raise VersionAdapterError(
    "unsupported repository version transition: " + " ".join(arguments)
  )


def run_transition(
  root: Path,
  config: dict,
  *arguments: str,
) -> None:
  if not arguments:
    raise VersionAdapterError("repository version transition requires arguments")
  before_state = repository_state(root)
  before = read_version(root, config)
  expected = _expected_transition(before, tuple(arguments))
  _run_adapter(
    root,
    config,
    list(arguments),
    allow_worktree_changes=True,
  )
  try:
    after = read_version(root, config)
    if after != expected:
      raise VersionAdapterError(
        "repository version adapter produced inconsistent transition: "
        f"expected {expected}, got {after}"
      )
    paths = changed_files(root)
    if not paths:
      raise VersionAdapterError(
        "repository version adapter transition changed no repository files"
      )
    _write_transition_marker(
      root,
      before=before,
      after=after,
      paths=paths,
    )
  except VersionAdapterError:
    restore_repository_state(root, before_state)
    raise
