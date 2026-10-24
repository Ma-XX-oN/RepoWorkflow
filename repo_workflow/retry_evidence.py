"""Isolate canonical local test evidence from candidate clean-tree checks.

Only a verified per-issue JSONL log can be hidden from the working tree.
Other dirty inputs remain visible to normal candidate validation.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Iterator


class RetryEvidenceError(ValueError):
  pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, encoding="utf-8", errors="strict",
    capture_output=True, check=False,
  )


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
  return subprocess.run(
    ["git", "-C", str(root), *args],
    capture_output=True, check=False,
  )


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


def _replace_bytes(path: Path, content: bytes) -> None:
  """Atomically replace a path without following a substituted symlink."""
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(
      mode="wb", prefix=path.name + ".retry-restore-",
      dir=path.parent, delete=False,
    ) as output:
      temporary = Path(output.name)
      output.write(content)
    os.replace(temporary, path)
    temporary = None
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def _committed_checkout_bytes(root: Path, relative: str) -> bytes | None:
  """Read the raw HEAD blob and apply Git's actual checkout filters."""
  committed = _git_bytes(root, "show", "HEAD:" + relative)
  if committed.returncode:
    tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked.returncode != 1:
      raise RetryEvidenceError("cannot establish canonical Git blob absence")
    return None
  _validate_log(committed.stdout)
  converted = _git_bytes(
    root, "cat-file", "--filters", "--path=" + relative,
    "HEAD:" + relative,
  )
  if converted.returncode:
    raise RetryEvidenceError("cannot apply canonical Git checkout filters")
  _validate_log(converted.stdout)
  return converted.stdout


def _status(root: Path) -> list[str]:
  try:
    status = _git(root, "status", "--porcelain", "--untracked-files=all", "-z")
  except UnicodeError as error:
    raise RetryEvidenceError("cannot decode candidate worktree status") from error
  if status.returncode:
    raise RetryEvidenceError("cannot inspect candidate worktree")
  return [item for item in status.stdout.split("\0") if item]


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
  if log.is_symlink():
    raise RetryEvidenceError("canonical log must not be a symlink")
  if not log.exists():
    yield log
    return
  if not log.is_file():
    raise RetryEvidenceError("canonical log must be a regular file")
  try:
    original = log.read_bytes()
    _validate_log(original)
  except RetryEvidenceError:
    raise
  except OSError as error:
    raise RetryEvidenceError("cannot read canonical retry evidence") from error

  entries = _status(root)
  if any(item[:3] not in {"?? ", " M "} or
         item[3:] != relative for item in entries):
    raise RetryEvidenceError("source or unrelated files are dirty")
  expected = _committed_checkout_bytes(root, relative)
  if log.is_symlink() or not log.is_file() or log.read_bytes() != original:
    raise RetryEvidenceError("canonical retry evidence changed before isolation")

  active = False
  try:
    if expected is None:
      log.unlink()
    else:
      _replace_bytes(log, expected)
    active = True
    if _status(root):
      raise RetryEvidenceError("candidate remained dirty after evidence isolation")
    yield log
  finally:
    if active:
      substituted_symlink = log.is_symlink()
      if substituted_symlink:
        log.unlink()
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
      _replace_bytes(log, original)
      if substituted_symlink:
        raise RetryEvidenceError("operation replaced canonical log with symlink")
      if unexpected:
        raise RetryEvidenceError("operation changed isolated canonical evidence")
      if status_error is not None:
        raise status_error
      if dirty:
        raise RetryEvidenceError("operation dirtied candidate worktree")
