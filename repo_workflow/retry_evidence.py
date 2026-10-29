"""Isolate canonical local test evidence from candidate clean-tree checks.

Only a verified per-issue JSONL log can be hidden from the working tree.
Other dirty inputs remain visible to normal candidate validation.
"""

from __future__ import annotations

from contextlib import contextmanager
import base64
import binascii
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path
import subprocess
import tempfile
from typing import Iterator

from . import git as git_boundary


class RetryEvidenceError(ValueError):
  pass


def _is_link_entry(path: Path) -> bool:
  """Reject symlinks and Windows mount-point reparse entries (junctions)."""
  if path.is_symlink():
    return True
  if os.name != "nt":
    return False
  try:
    tag = getattr(path.stat(follow_symlinks=False), "st_reparse_tag", None)
  except FileNotFoundError:
    return False
  return tag == stat.IO_REPARSE_TAG_MOUNT_POINT


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
  try:
    return subprocess.run(
      ["git", "-C", str(root), *args],
      capture_output=True, check=False,
    )
  except OSError as error:
    raise RetryEvidenceError("cannot execute Git for retry evidence") from error


def _reject_non_json_constant(value: str) -> None:
  raise ValueError("non-JSON constant in retry evidence: " + value)


def _validate_log(content: bytes) -> None:
  if not content.strip():
    raise RetryEvidenceError("canonical retry evidence is empty")
  try:
    lines = content.split(b"\n")
    if lines[-1] == b"":
      lines.pop()
    for line in lines:
      record = json.loads(
        line.decode("utf-8"), parse_constant=_reject_non_json_constant,
      )
      if not isinstance(record, dict) or not all(
        field in record for field in ("testSHA", "kind", "result", "runner")
      ):
        raise RetryEvidenceError("canonical log record is incomplete")
  except RetryEvidenceError:
    raise
  except (UnicodeError, ValueError, RecursionError) as error:
    raise RetryEvidenceError("canonical retry evidence is invalid") from error


def _replace_bytes(path: Path, content: bytes, mode: int,
                   parents: tuple[tuple[int, int], ...] | None = None) -> None:
  """Replace only beneath the same real parent directories."""
  initial_parents = _parent_fingerprint(path)
  if parents is not None and initial_parents != parents:
    raise RetryEvidenceError("canonical log parent replaced before mutation")
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
    if _parent_fingerprint(path) != initial_parents:
      raise RetryEvidenceError("canonical log parent changed during replacement")
    os.replace(temporary, path)
    temporary = None
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def _recover_parents(root: Path) -> bool:
  """Move substituted parent entries aside without following foreign links."""
  changed = False
  for parent in (root / ".repoworkflow", root / ".repoworkflow/validation"):
    if _is_link_entry(parent) or (parent.exists() and not parent.is_dir()):
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
  checkout = getattr(git_boundary, "git_checkout_bytes", None)
  if not callable(checkout):
    raise RetryEvidenceError("RWF #736 Git checkout API is required")
  try:
    expected = checkout(root, relative, treeish="HEAD")
  except (git_boundary.GitError, OSError) as error:
    raise RetryEvidenceError("cannot materialize canonical Git checkout") from error
  if expected is None:
    raise RetryEvidenceError("tracked canonical Git checkout is absent")
  if not isinstance(expected, bytes):
    raise RetryEvidenceError("Git checkout API returned non-byte evidence")
  _validate_log(expected)
  return expected


def _status(root: Path) -> list[bytes]:
  """Use raw NUL-delimited Git records; never lose bytes to host locales."""
  status = _git_bytes(root, "status", "--porcelain", "--untracked-files=all", "-z")
  if status.returncode:
    raise RetryEvidenceError("cannot inspect candidate worktree")
  return [item for item in status.stdout.split(b"\0") if item]



def _journal_path(gitdir: Path, issue: int) -> Path:
  return gitdir / f"rwf-retry-evidence-{issue}.backup"


def _write_journal(gitdir: Path, issue: int, original: bytes,
                   mode: int, expected: bytes | None) -> Path:
  """Persist recovery data atomically before changing canonical evidence."""
  journal = _journal_path(gitdir, issue)
  if journal.is_symlink() or journal.exists():
    raise RetryEvidenceError("unresolved or unsafe retry recovery journal")
  payload = json.dumps({
    "version": 1, "mode": mode,
    "original": base64.b64encode(original).decode("ascii"),
    "expected": (None if expected is None else
                 base64.b64encode(expected).decode("ascii")),
    "digest": hashlib.sha256(original).hexdigest(),
  }).encode("ascii")
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=gitdir, prefix=journal.name + ".tmp-", delete=False,
    ) as output:
      temporary = Path(output.name)
      output.write(payload)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temporary, journal)
    temporary = None
    return journal
  except OSError as error:
    raise RetryEvidenceError("cannot persist retry recovery journal") from error
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def _read_journal(journal: Path) -> tuple[bytes, int, bytes | None]:
  if journal.is_symlink() or not journal.is_file():
    raise RetryEvidenceError("unsafe retry recovery journal")
  try:
    value = json.loads(journal.read_bytes().decode("ascii"))
    if (value["version"] != 1 or type(value["mode"]) is not int or
        not 0 <= value["mode"] <= 0o7777):
      raise ValueError("invalid journal schema")
    original = base64.b64decode(value["original"], validate=True)
    encoded = value["expected"]
    expected = (None if encoded is None else
                base64.b64decode(encoded, validate=True))
    if hashlib.sha256(original).hexdigest() != value["digest"]:
      raise ValueError("journal digest mismatch")
    _validate_log(original)
    if expected is not None:
      _validate_log(expected)
    return original, value["mode"], expected
  except (OSError, ValueError, KeyError, TypeError, RecursionError, binascii.Error) as error:
    raise RetryEvidenceError("invalid retry recovery journal") from error


def _parent_fingerprint(log: Path) -> tuple[tuple[int, int], ...]:
  """Require original real parent objects, not substituted paths or links."""
  result = []
  for parent in (log.parent.parent, log.parent):
    if _is_link_entry(parent) or not parent.is_dir():
      raise RetryEvidenceError("canonical log parent changed before isolation")
    details = parent.stat(follow_symlinks=False)
    result.append((details.st_dev, details.st_ino))
  return tuple(result)


def _same_evidence(log: Path, original: bytes, mode: int) -> bool:
  return (not log.is_symlink() and log.is_file() and
          log.read_bytes() == original and
          stat.S_IMODE(log.stat(follow_symlinks=False).st_mode) == mode)


def _recover_journal(root: Path, issue: int, gitdir: Path) -> None:
  journal = _journal_path(gitdir, issue)
  if journal.is_symlink():
    raise RetryEvidenceError("unsafe retry recovery journal symlink")
  if not journal.exists():
    return
  original, mode, expected = _read_journal(journal)
  log = root / f".repoworkflow/validation/testResults-{issue}.jsonl"
  if any(_is_link_entry(parent) for parent in (log.parent.parent, log.parent)):
    raise RetryEvidenceError("retry recovery cannot follow linked parent")
  if _same_evidence(log, original, mode):
    journal.unlink()
    return
  if (expected is None and not log.exists() and not log.is_symlink() or
      expected is not None and not log.is_symlink() and
      log.is_file() and log.read_bytes() == expected and
      stat.S_IMODE(log.stat(follow_symlinks=False).st_mode) == mode):
    _replace_bytes(log, original, mode)
    journal.unlink()
    return
  raise RetryEvidenceError("retry recovery conflict; original retained in Git metadata")


def _remove_recovered_journal_if_restored(root: Path, issue: int,
                                          gitdir: Path) -> None:
  journal = _journal_path(gitdir, issue)
  if journal.is_symlink():
    raise RetryEvidenceError("unsafe retry recovery journal")
  if journal.exists():
    original, mode, _ = _read_journal(journal)
    log = root / f".repoworkflow/validation/testResults-{issue}.jsonl"
    if _same_evidence(log, original, mode):
      journal.unlink()

@contextmanager
def _isolation_lock(root: Path, issue: int) -> Iterator[Path]:
  """Exclude overlapping contexts using SQLite's cross-process Gitdir lock.

  This persistent file lives in the repository's own Git metadata, so it
  never dirties the working tree and is independent of process TMPDIR.
  Closing the SQLite connection releases the lock, including on process exit.
  """
  result = _git_bytes(root, "rev-parse", "--absolute-git-dir")
  if result.returncode:
    raise RetryEvidenceError("cannot locate Git directory for retry lock")
  try:
    gitdir = Path(result.stdout.removesuffix(b"\n").decode("utf-8"))
  except UnicodeError as error:
    raise RetryEvidenceError("cannot decode Git directory for retry lock") from error
  if not gitdir.is_absolute() or not gitdir.is_dir():
    raise RetryEvidenceError("invalid Git directory for retry lock")
  lock = gitdir / f"rwf-retry-evidence-{issue}.sqlite3"
  if lock.is_symlink():
    raise RetryEvidenceError("retry lock may not be a symlink")
  try:
    connection = sqlite3.connect(lock, timeout=0.0, isolation_level=None)
  except (OSError, sqlite3.Error) as error:
    raise RetryEvidenceError("cannot open retry isolation lock") from error
  try:
    try:
      connection.execute("BEGIN IMMEDIATE")
    except sqlite3.Error as error:
      raise RetryEvidenceError("retry evidence isolation already active or lock unavailable") from error
    yield gitdir
  finally:
    connection.close()


@contextmanager
def isolate_retry_evidence(root: Path, issue: int) -> Iterator[Path]:
  """Protect retry isolation with an OS-neutral cross-process Gitdir lock."""
  root = root.resolve()
  if issue < 1:
    raise RetryEvidenceError("issue must be positive")
  with _isolation_lock(root, issue) as gitdir:
    _recover_journal(root, issue, gitdir)
    try:
      with _isolate_retry_evidence_locked(root, issue, gitdir) as log:
        yield log
    finally:
      _remove_recovered_journal_if_restored(root, issue, gitdir)


@contextmanager
def _isolate_retry_evidence_locked(root: Path, issue: int, gitdir: Path) -> Iterator[Path]:
  """Temporarily expose HEAD's checkout representation, then restore evidence.

  The canonical committed blob stays byte-for-byte intact in Git. Checkout
  bytes respect attributes and filters; a dirty non-evidence path never hides.
  """
  root = root.resolve()
  if issue < 1:
    raise RetryEvidenceError("issue must be positive")
  relative = f".repoworkflow/validation/testResults-{issue}.jsonl"
  log = root / relative
  if any(_is_link_entry(parent) for parent in (
    root / ".repoworkflow", log.parent,
  )):
    raise RetryEvidenceError("canonical log parent must not be linked")
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
  if not _same_evidence(log, original, original_mode):
    raise RetryEvidenceError("canonical retry evidence changed before isolation")

  original_parents = _parent_fingerprint(log)
  journal = _write_journal(gitdir, issue, original, original_mode, expected)
  active = False
  preflight_dirty = False
  try:
    if _parent_fingerprint(log) != original_parents:
      raise RetryEvidenceError("canonical log parent replaced before isolation")
    active = True  # Restoration must run even if replacement raises after a write.
    if expected is None:
      log.unlink()
    else:
      _replace_bytes(log, expected, original_mode, original_parents)
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
      current_mode = (stat.S_IMODE(log.stat(follow_symlinks=False).st_mode)
                      if current is not None else None)
      unexpected = (current != expected or
                    (current is not None and current_mode != original_mode))
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
        raise RetryEvidenceError("operation changed isolated canonical evidence bytes or mode")
      if status_error is not None:
        raise status_error
      if dirty and not preflight_dirty:
        raise RetryEvidenceError("operation dirtied candidate worktree")
