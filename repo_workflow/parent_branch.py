from __future__ import annotations

from pathlib import Path
import re

from .git import GitError, git


class ParentBranchError(RuntimeError):
  """Raised when a work branch parent cannot be recovered unambiguously."""


_BRANCH_RE = re.compile(r"^[^\s~^:?*\[\\]+(?:/[^\s~^:?*\[\\]+)*$")


def recover_parent_branch(root: Path, work_branch: str) -> str:
  """Recover one parent from branch-bound identity history and local Git refs."""
  work = _branch_name(work_branch, "work branch")
  work_ref = _work_ref(root, work)
  try:
    commits = git(
      root,
      "rev-list",
      "--first-parent",
      work_ref,
    ).stdout.splitlines()
  except GitError as error:
    raise ParentBranchError(f"work branch {work} is unavailable") from error
  matches: list[tuple[str, str]] = []
  for commit in commits:
    message = git(root, "show", "-s", "--format=%B", commit).stdout
    branch_values = _trailers(message, "RWF-Branch")
    parent_values = _trailers(message, "RWF-Parent")
    if not branch_values and not parent_values:
      continue
    if len(branch_values) != 1 or len(parent_values) != 1:
      if work in branch_values:
        raise ParentBranchError(f"malformed parent identity marker for {work}")
      continue
    if branch_values[0] != work:
      continue
    parent = _branch_name(parent_values[0], "parent branch")
    matches.append((commit, parent))

  if len(matches) != 1:
    raise ParentBranchError(
      f"expected exactly one parent identity marker for {work}; found {len(matches)}"
    )

  marker, parent = matches[0]
  creation_tip = git(root, "rev-parse", f"{marker}^").stdout.strip()
  refs = _parent_refs(root, parent)
  if not refs:
    raise ParentBranchError(f"parent branch {parent} has no local or fetched ref")

  for ref in refs:
    result = git(
      root,
      "merge-base",
      "--is-ancestor",
      creation_tip,
      ref,
      check=False,
    )
    if result.returncode:
      raise ParentBranchError(
        f"parent ref {ref} no longer contains creation tip {creation_tip}"
      )
  return parent


def _work_ref(root: Path, work: str) -> str:
  refs = _branch_refs(root, work)
  if not refs:
    raise ParentBranchError(
      f"work branch {work} has no local or fetched ref"
    )
  tips = {
    git(root, "rev-parse", ref).stdout.strip()
    for ref in refs
  }
  if len(tips) != 1:
    raise ParentBranchError(
      f"work branch {work} has conflicting local/fetched refs"
    )
  return refs[0]


def _branch_refs(root: Path, branch: str) -> tuple[str, ...]:
  refs: list[str] = []
  local = f"refs/heads/{branch}"
  if git(root, "show-ref", "--verify", local, check=False).returncode == 0:
    refs.append(local)
  remote = git(
    root,
    "for-each-ref",
    "--format=%(refname)",
    "refs/remotes",
  ).stdout.splitlines()
  suffix = f"/{branch}"
  refs.extend(
    ref for ref in remote
    if ref.startswith("refs/remotes/") and ref.endswith(suffix)
  )
  return tuple(sorted(set(refs)))


def _parent_refs(root: Path, parent: str) -> tuple[str, ...]:
  return _branch_refs(root, parent)


def _trailers(message: str, key: str) -> list[str]:
  prefix = f"{key}:"
  return [
    line[len(prefix):].strip()
    for line in message.splitlines()
    if line.startswith(prefix)
  ]


def _branch_name(value: str, label: str) -> str:
  if not isinstance(value, str) or not value or value.startswith("refs/"):
    raise ParentBranchError(f"invalid canonical {label}: {value!r}")
  if value.startswith("/") or value.endswith("/") or ".." in value or "//" in value:
    raise ParentBranchError(f"invalid canonical {label}: {value!r}")
  if not _BRANCH_RE.fullmatch(value):
    raise ParentBranchError(f"invalid canonical {label}: {value!r}")
  return value
