"""Repository-local mutual exclusion for lifecycle/CSV projection publication."""

from contextlib import contextmanager
from pathlib import Path

from .state_store import _acquire_lock, _release_lock


@contextmanager
def projection_lock(repository_root: Path):
  """Serialize lifecycle mutations with publishing a refreshed CSV projection."""
  lock = Path(repository_root).resolve() / ".repoworkflow" / ".lifecycle-projection.lock"
  _acquire_lock(lock)
  try:
    yield
  finally:
    _release_lock(lock)
