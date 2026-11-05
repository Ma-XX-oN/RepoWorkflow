"""Commit command-owned files without consuming unrelated staged changes."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Sequence


class OwnedCommitError(RuntimeError):
  """The command cannot safely commit its declared durable files."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
  result = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, check=False,
  )
  if result.returncode:
    raise OwnedCommitError(
      f"git {args[0]} failed: {result.stderr.decode('utf-8', 'replace').strip()}"
    )
  return result


def commit_owned_files(root: Path, paths: Sequence[str], message: str) -> str | None:
  """Commit only declared paths and retain all unrelated index/worktree states.

  Git's path-scoped `commit --only` uses a temporary index. Unlike a broad
  stash, it preserves mixed staged/unstaged edits to unrelated files without
  an error-prone stash pop. Call only after writing the command-owned files.
  """
  if (not isinstance(message, str) or not message.strip()
      or "\x00" in message or "\n" in message):
    raise OwnedCommitError("commit message must be a nonempty single line")
  if not paths or isinstance(paths, (str, bytes)):
    raise OwnedCommitError("command must declare at least one owned path")
  names: list[str] = []
  for value in paths:
    if (not isinstance(value, str) or not value or "\x00" in value
        or "\\" in value or value.startswith("-")
        or re.match(r"^[A-Za-z]:", value)):
      raise OwnedCommitError("invalid command-owned Git path")
    p = PurePosixPath(value)
    if (p.is_absolute() or ".." in p.parts or "." in p.parts
        or ".git" in p.parts or str(p) != value):
      raise OwnedCommitError("command-owned paths must be canonical repository-relative files")
    if value in names:
      raise OwnedCommitError("duplicate command-owned path")
    names.append(value)
  root = Path(root).resolve()
  _git(root, "rev-parse", "--show-toplevel")
  before = _git(root, "rev-parse", "HEAD").stdout.strip()
  # `commit --only` commits complete current file contents from just these
  # paths, regardless of unrelated changes staged in the user's index.
  # Intent-to-add is necessary for a new untracked owned file.
  # Git pathspecs expand directories.  Verify each requested name is exactly
  # one file in the index before staging anything: post-commit checks are too late.
  untracked: list[str] = []
  for name in names:
    indexed = _git(root, "ls-files", "-z", "--", name).stdout
    if indexed:
      if indexed != name.encode("utf-8", "strict") + b"\0":
        raise OwnedCommitError(f"command-owned path is not one tracked file: {name}")
    elif (root / name).is_file() or (root / name).is_symlink():
      untracked.append(name)
    else:
      raise OwnedCommitError(f"command-owned path is missing: {name}")
  intent: list[str] = []
  try:
    for name in untracked:
      _git(root, "add", "-N", "--", name)
      intent.append(name)
    changed = _git(root, "status", "--porcelain", "-z", "--", *names).stdout
    if not changed:
      return None
    result = subprocess.run(
      ["git", "commit", "--only", "-m", message, "--", *names],
      cwd=root, capture_output=True, check=False,
    )
    if result.returncode:
      raise OwnedCommitError(
        "command-owned commit failed: " + result.stderr.decode("utf-8", "replace").strip()
      )
    sha = _git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    if sha.encode("ascii") == before:
      raise OwnedCommitError("command-owned files changed but no commit was created")
    changed_paths = _git(
      root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD",
    ).stdout.decode("utf-8", "strict").splitlines()
    if not changed_paths or set(changed_paths) - set(names):
      raise OwnedCommitError("command-owned commit changed unauthorized paths")
    return sha
  finally:
    if intent:
      # Normally commit --only clears intent-to-add entries. Preserve any
      # existing user stage records and clean up only entries we introduced.
      for name in intent:
        state = subprocess.run(
          ["git", "ls-files", "--stage", "--", name],
          cwd=root, capture_output=True, check=False,
        )
        if state.returncode == 0 and state.stdout:
          fields = state.stdout.split(b"\t", 1)[0].split()
          if len(fields) == 3 and set(fields[1]) == {48}:
            _git(root, "reset", "--quiet", "--", name)
