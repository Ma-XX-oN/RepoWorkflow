"""Isolate canonical local test evidence from candidate clean-tree checks.

Only a verified per-issue JSONL log can be hidden from the working tree.
Other dirty inputs remain visible to normal candidate validation.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Iterator


class RetryEvidenceError(ValueError):
  pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )


@contextmanager
def isolate_retry_evidence(root: Path, issue: int) -> Iterator[Path]:
  """Temporarily restore the log's committed state, then restore all evidence.

  The caller must validate the candidate while inside the context. Never
  suppress or modify other source changes.
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
  try:
    original = log.read_bytes()
    if not original.strip():
      raise RetryEvidenceError("canonical retry evidence is empty")
    for line in original.splitlines():
      record = json.loads(line)
      if not isinstance(record, dict) or not all(
        field in record for field in ("testSHA", "kind", "result", "runner")
      ):
        raise RetryEvidenceError("canonical log record is incomplete")
  except (OSError, UnicodeError, ValueError) as error:
    raise RetryEvidenceError("canonical retry evidence is invalid") from error

  status = _git(root, "status", "--porcelain", "--untracked-files=all", "-z")
  if status.returncode:
    raise RetryEvidenceError("cannot inspect candidate worktree")
  entries = [item for item in status.stdout.split("\0") if item]
  if any(item[:3] not in {"?? ", " M "} or
         item[3:] != relative for item in entries):
    raise RetryEvidenceError("source or unrelated files are dirty")

  committed = _git(root, "show", "HEAD:" + relative)
  if committed.returncode == 0:
    log.write_bytes(committed.stdout.encode("utf-8"))
  else:
    log.unlink()
  try:
    yield log
  finally:
    # Fail closed if the operation itself wrote new canonical evidence.
    unexpected = None
    substituted_symlink = log.is_symlink()
    if substituted_symlink:
      log.unlink()
    if log.exists():
      current = log.read_bytes()
      if committed.returncode != 0 or current != committed.stdout.encode("utf-8"):
        unexpected = current
    log.parent.mkdir(parents=True, exist_ok=True)
    if unexpected is not None:
      with tempfile.NamedTemporaryFile(
        mode="wb", prefix=log.name + ".retry-conflict-",
        dir=log.parent, delete=False,
      ) as conflict:
        conflict.write(unexpected)
    log.write_bytes(original)
    if substituted_symlink:
      raise RetryEvidenceError("operation replaced canonical log with symlink")
    if unexpected is not None:
      raise RetryEvidenceError("operation changed isolated canonical evidence")
