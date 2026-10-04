from __future__ import annotations

from pathlib import Path
import re

from .git import git


_TRAILER = re.compile(r"^(RWF-Branch|RWF-Parent): (.+)$")


class ParentRecoveryError(RuntimeError):
  """Raised when semantic parent identity cannot be recovered uniquely."""


def recover_parent(repository_root: Path, work_branch: str) -> str:
  root = Path(repository_root).resolve()
  _branch_name(work_branch, "work branch")
  branch_ref = _resolve_work_branch_ref(root, work_branch)
  history = git(root, "rev-list", "--first-parent", branch_ref).stdout.splitlines()
  matches: list[tuple[str, str]] = []
  for commit in history:
    message = git(root, "show", "-s", "--format=%B", commit).stdout
    marker = _identity_marker(message)
    if marker is not None and marker[0] == work_branch:
      matches.append((commit, marker[1]))
  if len(matches) != 1:
    raise ParentRecoveryError(
      f"work branch {work_branch!r} has {len(matches)} matching identity markers"
    )
  marker_commit, parent = matches[0]
  _branch_name(parent, "parent")
  creation_parent = git(
    root, "rev-parse", f"{marker_commit}^1", check=False
  )
  if creation_parent.returncode:
    raise ParentRecoveryError("identity marker has no first parent")
  creation_tip = creation_parent.stdout.strip()

  refs = _branch_refs(root, parent)
  if not refs:
    raise ParentRecoveryError(
      f"parent branch {parent!r} has no local representation"
    )
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
      raise ParentRecoveryError(
        f"parent representation {ref!r} does not contain creation tip"
      )
  return parent


def _resolve_work_branch_ref(root: Path, branch: str) -> str:
  refs = _branch_refs(root, branch)
  if not refs:
    raise ParentRecoveryError(
      f"work branch {branch!r} has no local representation"
    )
  tips = {git(root, "rev-parse", ref).stdout.strip() for ref in refs}
  if len(tips) != 1:
    raise ParentRecoveryError(
      f"work branch {branch!r} has conflicting local representations"
    )
  return refs[0]


def _branch_refs(root: Path, branch: str) -> tuple[str, ...]:
  result = git(
    root,
    "for-each-ref",
    "--format=%(refname)",
    "refs/heads",
    "refs/remotes",
  )
  local = f"refs/heads/{branch}"
  suffix = f"/{branch}"
  refs = [
    ref
    for ref in result.stdout.splitlines()
    if ref == local
    or (ref.startswith("refs/remotes/") and ref.endswith(suffix))
  ]
  return tuple(sorted(refs))


def _identity_marker(message: str) -> tuple[str, str] | None:
  values: dict[str, list[str]] = {"RWF-Branch": [], "RWF-Parent": []}
  for line in message.splitlines():
    match = _TRAILER.fullmatch(line)
    if match:
      values[match.group(1)].append(match.group(2))
  if not values["RWF-Branch"] and not values["RWF-Parent"]:
    return None
  if len(values["RWF-Branch"]) != 1 or len(values["RWF-Parent"]) != 1:
    return None
  return values["RWF-Branch"][0], values["RWF-Parent"][0]


def _branch_name(value: str, label: str) -> None:
  if not isinstance(value, str) or not value or value.strip() != value:
    raise ParentRecoveryError(f"invalid {label} name: {value!r}")
  if value.startswith("refs/") or value.startswith("origin/"):
    raise ParentRecoveryError(
      f"invalid canonical {label} name: {value!r}"
    )
