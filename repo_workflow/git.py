from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


class GitError(RuntimeError):
  pass


@dataclass(frozen=True)
class RepositoryState:
  commit: str
  head_ref: str | None
  refs: dict[str, str]


def git(
  root: Path,
  *args: str,
  check: bool = True,
  capture: bool = True,
) -> subprocess.CompletedProcess[str]:
  try:
    completed = subprocess.run(
      ["git", *args],
      cwd=root,
      text=True,
      capture_output=capture,
      check=False,
    )
  except OSError as exc:
    raise GitError(f"cannot execute git: {exc}") from exc
  if check and completed.returncode:
    detail = (completed.stderr or completed.stdout or "git command failed").strip()
    raise GitError(f"git {' '.join(args)}: {detail}")
  return completed


def head_sha(root: Path) -> str:
  return git(root, "rev-parse", "HEAD").stdout.strip()


def current_branch(root: Path) -> str:
  return git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def head_reference(root: Path) -> str | None:
  result = git(root, "symbolic-ref", "-q", "HEAD", check=False)
  if result.returncode:
    return None
  value = result.stdout.strip()
  return value or None


def changed_files(root: Path) -> list[str]:
  completed = git(
    root,
    "status",
    "--porcelain=v1",
    "--untracked-files=all",
    "-z",
  )
  values: list[str] = []
  parts = completed.stdout.split("\0")
  index = 0
  while index < len(parts):
    entry = parts[index]
    if not entry:
      index += 1
      continue
    path = entry[3:]
    status = entry[:2]
    if "R" in status or "C" in status:
      index += 1
      if index < len(parts) and parts[index]:
        path = parts[index]
    values.append(path.replace("\\", "/"))
    index += 1
  return sorted(set(values))


def local_ref_snapshot(root: Path) -> dict[str, str]:
  completed = git(
    root,
    "for-each-ref",
    "--format=%(refname)%00%(objectname)",
  )
  values: dict[str, str] = {}
  for line in completed.stdout.splitlines():
    if "\0" not in line:
      continue
    ref, object_name = line.split("\0", 1)
    if ref.startswith("refs/remotes/"):
      continue
    values[ref] = object_name
  return values


def repository_state(root: Path) -> RepositoryState:
  return RepositoryState(
    commit=head_sha(root),
    head_ref=head_reference(root),
    refs=local_ref_snapshot(root),
  )


def restore_repository_state(root: Path, state: RepositoryState) -> None:
  if state.head_ref is None:
    git(root, "checkout", "--detach", "--force", state.commit)
  else:
    git(root, "update-ref", state.head_ref, state.commit)
    git(root, "symbolic-ref", "HEAD", state.head_ref)

  current = local_ref_snapshot(root)
  for ref in sorted(set(current) - set(state.refs)):
    git(root, "update-ref", "-d", ref)
  for ref, object_name in state.refs.items():
    if current.get(ref) != object_name:
      git(root, "update-ref", ref, object_name)

  git(root, "reset", "--hard", state.commit)
  git(root, "clean", "-fd")
