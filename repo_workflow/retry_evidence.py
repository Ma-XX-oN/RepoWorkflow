"""Isolate canonical local test evidence from candidate clean-tree checks.

Only a verified per-issue JSONL log can be hidden from the working tree.
Other dirty inputs remain visible to normal candidate validation.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import stat
from pathlib import Path
import subprocess
import tempfile
from typing import Iterator

from . import git as git_boundary


class RetryEvidenceError(ValueError):
  pass


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
  try:
    return subprocess.run(
      ["git", "-C", str(root), *args],
      capture_output=True, check=False,
    )
  except OSError as error:
    raise RetryEvidenceError("cannot execute Git for retry evidence") from error


def _validate_log(content: bytes) -> None:
  if not content.strip():
    raise RetryEvidenceError("canonical retry evidence is empty")
  try:
    for line in content.splitlines():
      record = json.loads(line)
      if not isinstance(record, dict) or not all(
        field in record for field in ("testSHA", "kind", "result", "runner")
      ):
        raise RetryEvidenceError("canonical log record is incomplete")
  except RetryEvidenceError:
    raise
  except (UnicodeError, ValueError) as error:
    raise RetryEvidenceError("canonical retry evidence is invalid") from error


def _replace_bytes(path: Path, content: bytes, mode: int) -> None:
  """Atomically replace a path without following a substituted symlink."""
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(
      mode="wb", prefix=path.name + ".retry-restore-",
      dir=path.parent, delete=False,
    ) as output:
      temporary = Path(output.name)
      output.write(content)
      if hasattr(os, "fchmod"):
        os.fchmod(output.fileno(), mode)
      else:
        os.chmod(temporary, mode, follow_symlinks=False)
    os.replace(temporary, path)
    temporary = None
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def _recover_parents(root: Path) -> bool:
  """Move substituted parent entries aside without following foreign links."""
  changed = False
  for parent in (root / ".repoworkflow", root / ".repoworkflow/validation"):
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
      conflict = Path(tempfile.mkdtemp(
        prefix=parent.name + ".retry-conflict-", dir=parent.parent,
      ))
      os.replace(parent, conflict / parent.name)
      changed = True
    if not parent.exists():
      parent.mkdir()
      changed = True
  return changed


def _committed_checkout_bytes(root: Path, relative: str) -> bytes | None:
  """Use one Git-authoritative checkout result, never guessed alternatives.

  Validate raw HEAD bytes independently of the committed tree's materialized
  checkout representation.
  """
  committed = _git_bytes(root, "show", "HEAD:" + relative)
  if committed.returncode:
    tracked = _git_bytes(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked.returncode != 1:
      raise RetryEvidenceError("cannot establish canonical Git blob absence")
    return None
  _validate_log(committed.stdout)
  try:
    expected = git_boundary.git_checkout_bytes(root, relative, treeish="HEAD")
  except AttributeError as error:
    raise RetryEvidenceError("RWF #736 Git checkout API is required") from error
  except (git_boundary.GitError, OSError) as error:
    raise RetryEvidenceError("cannot materialize canonical Git checkout") from error
  if expected is None:
    raise RetryEvidenceError("tracked canonical Git checkout is absent")
  _validate_log(expected)
  return expected


def _status(root: Path) -> list[bytes]:
  """Use raw NUL-delimited Git records; never lose bytes to host locales."""
  status = _git_bytes(root, "status", "--porcelain", "--untracked-files=all", "-z")
  if status.returncode:
    raise RetryEvidenceError("cannot inspect candidate worktree")
  return [item for item in status.stdout.split(b"\0") if item]


@contextmanager
def isolate_retry_evidence(root: Path, issue: int) -> Iterator[Path]:
  """Temporarily expose HEAD's checkout representation, then restore evidence.

  The canonical committed blob stays byte-for-byte intact in Git. Checkout
  bytes respect attributes and filters; a dirty non-evidence path never hides.
  """
  root = root.resolve()
  if issue < 1:
    raise RetryEvidenceError("issue must be positive")
  relative = f".repoworkflow/validation/testResults-{issue}.jsonl"
  log = root / relative
  if any(parent.is_symlink() for parent in (
    root / ".repoworkflow", log.parent,
  )):
    raise RetryEvidenceError("canonical log parent must not be a symlink")
  if log.is_symlink():
    raise RetryEvidenceError("canonical log must not be a symlink")
  if not log.exists():
    yield log
    return
  if not log.is_file():
    raise RetryEvidenceError("canonical log must be a regular file")
  try:
    original = log.read_bytes()
    original_mode = stat.S_IMODE(log.stat(follow_symlinks=False).st_mode)
    _validate_log(original)
  except RetryEvidenceError:
    raise
  except OSError as error:
    raise RetryEvidenceError("cannot read canonical retry evidence") from error

  entries = _status(root)
  if any(item[:3] not in {b"?? ", b" M "} or
         item[3:] != relative.encode("ascii") for item in entries):
    raise RetryEvidenceError("source or unrelated files are dirty")
  expected = _committed_checkout_bytes(root, relative)
  if log.is_symlink() or not log.is_file() or log.read_bytes() != original:
    raise RetryEvidenceError("canonical retry evidence changed before isolation")

  active = False
  preflight_dirty = False
  try:
    if expected is None:
      log.unlink()
    else:
      _replace_bytes(log, expected, original_mode)
    active = True
    if _status(root):
      preflight_dirty = True
      raise RetryEvidenceError("candidate remained dirty after evidence isolation")
    yield log
  finally:
    if active:
      parent_changed = _recover_parents(root)
      substituted_symlink = log.is_symlink()
      substituted_nonfile = log.exists() and not log.is_file()
      if substituted_symlink or substituted_nonfile:
        # Preserve substituted directories, links and their contents without
        # following them or blocking restoration of the original evidence.
        quarantine = Path(tempfile.mkdtemp(
          prefix=log.name + ".retry-conflict-", dir=log.parent,
        ))
        os.replace(log, quarantine / log.name)
      current = log.read_bytes() if log.exists() and log.is_file() else None
      unexpected = (current != expected)
      status_error = None
      try:
        dirty = bool(_status(root))
      except RetryEvidenceError as error:
        status_error = error
        dirty = True
      if unexpected and current is not None:
        with tempfile.NamedTemporaryFile(
          mode="wb", prefix=log.name + ".retry-conflict-",
          dir=log.parent, delete=False,
        ) as conflict:
          conflict.write(current)
      _replace_bytes(log, original, original_mode)
      if parent_changed:
        raise RetryEvidenceError("operation changed canonical log parent")
      if substituted_symlink:
        raise RetryEvidenceError("operation replaced canonical log with symlink")
      if substituted_nonfile:
        raise RetryEvidenceError("operation replaced canonical log with non-file")
      if unexpected:
        raise RetryEvidenceError("operation changed isolated canonical evidence")
      if status_error is not None:
        raise status_error
      if dirty and not preflight_dirty:
        raise RetryEvidenceError("operation dirtied candidate worktree")
