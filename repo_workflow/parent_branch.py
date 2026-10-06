from __future__ import annotations

from pathlib import Path
import re

from .git import GitError, git


class ParentBranchError(RuntimeError):
  """Raised when a work branch parent cannot be recovered unambiguously."""


_BRANCH_RE = re.compile(r"^[^\s~^:?*\[\\]+(?:/[^\s~^:?*\[\\]+)*$")



def create_parent_identity(
  root: Path,
  work_branch: str,
  parent_branch: str,
) -> str:
  """Record the branch's creation parent once in ordinary Git history."""
  work = _branch_name(work_branch, "work branch")
  parent = _branch_name(parent_branch, "parent branch")
  current = git(root, "branch", "--show-current").stdout.strip()
  if current != work:
    raise ParentBranchError(
      f"work branch {work} must be checked out to record parent identity"
    )
  if work == parent:
    raise ParentBranchError("work branch cannot be its own parent")
  if _trailers_in_history(root, work):
    raise ParentBranchError(f"parent identity already exists for {work}")
  git(
    root,
    "commit",
    "--allow-empty",
    "-m",
    (
      "RepoWorkflow branch identity\n\n"
      f"RWF-Branch: {work}\n"
      f"RWF-Parent: {parent}"
    ),
  )
  return git(root, "rev-parse", "HEAD").stdout.strip()


def _trailers_in_history(root: Path, work: str) -> bool:
  for commit in git(root, "rev-list", "--first-parent", work).stdout.splitlines():
    message = git(root, "show", "-s", "--format=%B", commit).stdout
    if work in _trailers(message, "RWF-Branch"):
      return True
  return False

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

  if not any(
    git(
      root,
      "merge-base",
      "--is-ancestor",
      creation_tip,
      ref,
      check=False,
    ).returncode == 0
    for ref in refs
  ):
    raise ParentBranchError(
      f"parent branch {parent} no longer contains creation tip {creation_tip}"
    )
  return parent


def _work_ref(root: Path, work: str) -> str:
  local = f"refs/heads/{work}"
  refs = _branch_refs(root, work)
  if not refs:
    raise ParentBranchError(
      f"work branch {work} has no local or fetched ref"
    )

  if local in refs:
    local_tip = git(root, "rev-parse", local).stdout.strip()
    local_identity = _parent_identity(root, local, work)
    for ref in refs:
      if ref == local:
        continue
      try:
        remote_identity = _parent_identity(root, ref, work)
      except ParentBranchError as error:
        raise ParentBranchError(
          f"work branch {work} has conflicting local/fetched refs"
        ) from error
      if remote_identity != local_identity:
        raise ParentBranchError(
          f"work branch {work} has conflicting local/fetched refs"
        )
      tip = git(root, "rev-parse", ref).stdout.strip()
      forward = git(
        root,
        "merge-base",
        "--is-ancestor",
        tip,
        local_tip,
        check=False,
      ).returncode == 0
      backward = git(
        root,
        "merge-base",
        "--is-ancestor",
        local_tip,
        tip,
        check=False,
      ).returncode == 0
      if not (forward or backward):
        raise ParentBranchError(
          f"work branch {work} has conflicting local/fetched refs"
        )
    return local

  identities = {
    _parent_identity(root, ref, work)
    for ref in refs
  }
  if len(identities) != 1:
    raise ParentBranchError(
      f"work branch {work} has conflicting fetched parent identities"
    )
  return refs[0]


def _parent_identity(
  root: Path,
  ref: str,
  work: str,
) -> tuple[str, str]:
  matches: list[tuple[str, str]] = []
  for commit in git(root, "rev-list", "--first-parent", ref).stdout.splitlines():
    message = git(root, "show", "-s", "--format=%B", commit).stdout
    branches = _trailers(message, "RWF-Branch")
    parents = _trailers(message, "RWF-Parent")
    if branches == [work] and len(parents) == 1:
      matches.append((commit, parents[0]))
  if len(matches) != 1:
    raise ParentBranchError(
      f"expected exactly one parent identity marker for {work}; "
      f"found {len(matches)} in {ref}"
    )
  return matches[0]


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
