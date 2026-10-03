from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .git import changed_files, repository_state
from .process import run_command


DEVELOPMENT_VERSION_RE = re.compile(
  r"^(\d+)\.(\d+)\.(\d+)-issue\.(\d+)\.(\d+)\.(\d+)$"
)
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class VersionAdapterError(RuntimeError):
  pass


@dataclass(frozen=True)
class VersionTransitionResult:
  request: tuple[str, ...]
  before: str
  after: str


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
  try:
    _assert_git_state_unchanged(root, before_state)
  except VersionAdapterError as exc:
    if result.returncode:
      raise VersionAdapterError(
        "repository version adapter failed and violated Git invariants"
      ) from exc
    raise
  if result.returncode:
    detail = (result.stderr or result.stdout).strip()
    raise VersionAdapterError(
      "repository version adapter failed"
      + (f": {detail}" if detail else "")
    )
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


def _components(pattern: re.Pattern[str], value: str) -> tuple[int, ...] | None:
  match = pattern.fullmatch(value)
  if match is None:
    return None
  return tuple(int(item) for item in match.groups())


def _validate_request(arguments: tuple[str, ...]) -> None:
  if (
    len(arguments) == 3
    and arguments[:2] == ("task", "--issue")
    and arguments[2].isdigit()
    and int(arguments[2]) > 0
  ):
    return
  if arguments in {
    ("task", "--increment", "CI-iteration"),
    ("task", "--increment", "merge-integration-failed"),
    ("integrate", "--increment", "patch"),
    ("integrate", "--increment", "minor"),
    ("release-major",),
  }:
    return
  raise VersionAdapterError(
    "unsupported repository version semantic request: "
    + " ".join(arguments)
  )


def _expected_transition(
  before: str,
  after: str,
  arguments: tuple[str, ...],
) -> bool:
  stable_before = _components(STABLE_VERSION_RE, before)
  stable_after = _components(STABLE_VERSION_RE, after)
  development_before = _components(DEVELOPMENT_VERSION_RE, before)
  development_after = _components(DEVELOPMENT_VERSION_RE, after)

  if arguments[:2] == ("task", "--issue"):
    if stable_before is None or development_after is None:
      return False
    major, minor, patch = stable_before
    issue = int(arguments[2])
    return development_after == (major, minor, patch, issue, 0, 1)

  if arguments == ("task", "--increment", "CI-iteration"):
    if development_before is None or development_after is None:
      return False
    major, minor, patch, issue, generation, iteration = development_before
    return development_after == (
      major, minor, patch, issue, generation, iteration + 1
    )

  if arguments == ("task", "--increment", "merge-integration-failed"):
    if development_before is None or development_after is None:
      return False
    major, minor, patch, issue, generation, _ = development_before
    return development_after == (
      major, minor, patch, issue, generation + 1, 1
    )

  if stable_before is None or stable_after is None:
    return False
  major, minor, patch = stable_before
  if arguments == ("integrate", "--increment", "patch"):
    return stable_after == (major, minor, patch + 1)
  if arguments == ("integrate", "--increment", "minor"):
    return stable_after == (major, minor + 1, 0)
  if arguments == ("release-major",):
    return stable_after == (major + 1, 0, 0)
  raise AssertionError(f"unhandled validated version request: {arguments!r}")


def run_transition(
  root: Path,
  config: dict,
  *arguments: str,
) -> VersionTransitionResult:
  request = tuple(arguments)
  _validate_request(request)
  before = read_version(root, config)
  try:
    _run_adapter(
      root,
      config,
      list(request),
      allow_worktree_changes=True,
    )
  except VersionAdapterError as exc:
    try:
      after_failure = read_version(root, config)
    except VersionAdapterError as query_exc:
      raise VersionAdapterError(
        "repository version adapter failed and did not restore readable "
        "canonical version state"
      ) from query_exc
    if after_failure != before:
      raise VersionAdapterError(
        "repository version adapter failed after changing canonical version "
        f"from {before} to {after_failure}"
      ) from exc
    raise

  after = read_version(root, config)
  if not _expected_transition(before, after, request):
    raise VersionAdapterError(
      "repository version adapter produced an invalid semantic transition: "
      f"{before} -> {after} for {' '.join(request)}"
    )
  return VersionTransitionResult(request=request, before=before, after=after)
