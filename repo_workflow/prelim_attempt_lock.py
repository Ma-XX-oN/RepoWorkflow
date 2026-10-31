"""Clone-local PRELIM attempt workspaces and process-scoped OS locks."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import time

from .git import git
from .state_store import JsonRecordStore


class PrelimError(RuntimeError):
  """A preliminary candidate is invalid, stale or needs operator resolution."""

def _workspace(root: Path, attempt: str) -> Path:
  common = Path(git(root, "rev-parse", "--git-common-dir").stdout.strip())
  if not common.is_absolute():
    common = (root / common).resolve()
  return common / "repoworkflow" / "prelim-worktrees" / attempt


@contextmanager
def _attempt_lock(root: Path, store: JsonRecordStore, attempt: str):
  """Process-scoped lock released by the OS even after an abrupt crash."""
  # Locks are clone-local coordination metadata, never tracked workflow
  # records. Keep the inode stable so simultaneous waiters cannot split locks.
  path = (_workspace(root, attempt).parent.parent / "prelim-locks" /
          f"{attempt}.lock")
  path.parent.mkdir(parents=True, exist_ok=True)
  fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
  locked = False
  try:
    if os.fstat(fd).st_size == 0:
      os.write(fd, b"0")
    deadline = time.monotonic() + 5.0
    while True:
      try:
        if os.name == "nt":
          import msvcrt
          os.lseek(fd, 0, os.SEEK_SET)
          msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
          import fcntl
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        break
      except OSError as exc:
        if time.monotonic() >= deadline:
          raise PrelimError(f"attempt lock is busy: {path}") from exc
        time.sleep(0.01)
    yield
  finally:
    if locked:
      if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
      else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)

