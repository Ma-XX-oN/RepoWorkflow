"""Engine-self repository-owned development version adapter.

The version state is a source file committed before the first .ci/run marker.
The stable VERSION file is a seed only for the explicit task --issue transition;
test evidence and hosted runners must never infer a development version.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

_STABLE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_TASK = re.compile(
  r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
  r"-issue\.([1-9][0-9]*)\.(0|[1-9][0-9]*)\.([1-9][0-9]*)\Z"
)


class EngineVersionError(ValueError):
  pass


def _read_one(path: Path) -> str:
  if path.is_symlink():
    raise EngineVersionError("engine version path cannot be a symlink")
  try:
    value = path.read_text(encoding="utf-8")
  except (OSError, UnicodeError) as error:
    raise EngineVersionError("cannot read engine version authority") from error
  if value != value.strip() + "\n" or "\n" in value[:-1]:
    raise EngineVersionError("engine version must be one canonical line")
  return value.strip()


def read_engine_version(root: Path) -> str:
  state = root / ".ci" / "engine-version"
  if state.exists() or state.is_symlink():
    version = _read_one(state)
    if not _TASK.fullmatch(version):
      raise EngineVersionError("invalid engine development version")
    return version
  version = _read_one(root / "VERSION")
  if not _STABLE.fullmatch(version):
    raise EngineVersionError("invalid engine stable version")
  return version


def transition_engine_version(
  root: Path, *, operation: str, issue: int | None = None,
) -> tuple[str, str]:
  """Make only a documented adapter transition, without committing history."""
  before = read_engine_version(root)
  stable = _STABLE.fullmatch(before)
  task = _TASK.fullmatch(before)
  if operation == "task --issue":
    if stable is None or isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
      raise EngineVersionError("task start requires stable version and positive issue")
    after = f"{before}-issue.{issue}.0.1"
  elif operation == "task --increment CI-iteration":
    if task is None or issue is not None:
      raise EngineVersionError("CI iteration requires a task development version")
    after = f"{'.'.join(task.groups()[:3])}-issue.{task.group(4)}.{task.group(5)}.{int(task.group(6)) + 1}"
  elif operation == "task --increment merge-integration-failed":
    if task is None or issue is not None:
      raise EngineVersionError("integration rejection requires a task development version")
    after = f"{'.'.join(task.groups()[:3])}-issue.{task.group(4)}.{int(task.group(5)) + 1}.1"
  else:
    raise EngineVersionError("unsupported engine version transition")
  path = root / ".ci" / "engine-version"
  if path.is_symlink():
    raise EngineVersionError("engine version path cannot be a symlink")
  path.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.NamedTemporaryFile(
    mode="w", encoding="utf-8", dir=path.parent,
    prefix=".engine-version-", delete=False,
  ) as file:
    temporary = Path(file.name)
    file.write(after + "\n")
  try:
    os.replace(temporary, path)
  finally:
    temporary.unlink(missing_ok=True)
  return before, after
