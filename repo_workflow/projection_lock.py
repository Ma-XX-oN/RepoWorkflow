"""Repository-local mutual exclusion for lifecycle/CSV projection publication."""

from contextlib import contextmanager
from functools import wraps
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

def serialized_lifecycle_mutation(method):
  """Lock the entire authoritative read-check-write transaction."""
  @wraps(method)
  def guarded(self, *args, **kwargs):
    with projection_lock(self.repository_root):
      return method(self, *args, **kwargs)
  return guarded
