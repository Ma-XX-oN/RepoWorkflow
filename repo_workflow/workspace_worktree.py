from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .git import GitError, git


WORKSPACE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")


class WorktreeError(RuntimeError):
  """Raised when worktree provisioning or retirement is unsafe."""


@dataclass(frozen=True)
class WorktreeInfo:
  workspace_id: str
  path: Path
  branch: str
  head: str


@dataclass(frozen=True)
class _RegisteredWorktree:
  path: Path
  head: str
  branch: str | None


class WorktreeBackend:
  """Local Git worktree materialization for RWF workspaces."""

  def __init__(self, root: Path):
    self.root = root.resolve()

  def provision(
    self,
    workspace_id: str,
    base_ref: str,
    base_sha: str,
    branch_name: str,
    worktree_path: Path,
  ) -> WorktreeInfo:
    workspace_id = _workspace_id(workspace_id)
    path = Path(worktree_path).resolve()
    _non_empty_text(base_ref, "base_ref")
    _non_empty_text(base_sha, "base_sha")
    _non_empty_text(branch_name, "branch_name")

    current_base = _rev_parse(self.root, base_ref)
    if current_base != base_sha:
      raise WorktreeError(
        f"stale base: {base_ref} is {current_base}, planned {base_sha}"
      )
    if path.exists():
      raise WorktreeError(f"worktree path already exists: {path}")

    registered = self._registered_worktrees()
    if any(item.path == path for item in registered):
      raise WorktreeError(f"worktree path is already registered: {path}")
    if any(item.branch == branch_name for item in registered):
      raise WorktreeError(
        f"branch is already checked out by another worktree: {branch_name}"
      )

    branch_ref = f"refs/heads/{branch_name}"
    branch_existed = _ref_exists(self.root, branch_ref)
    if branch_existed:
      raise WorktreeError(f"branch already exists: {branch_name}")

    created = False
    try:
      result = git(
        self.root,
        "worktree",
        "add",
        "-b",
        branch_name,
        str(path),
        base_sha,
        check=False,
      )
      if result.returncode:
        raise WorktreeError(
          _git_failure("git worktree add failed", result)
        )
      created = True

      head = _rev_parse(path, "HEAD")
      branch = git(
        path,
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
      ).stdout.strip()
      if head != base_sha or branch != branch_name:
        raise WorktreeError(
          "created worktree does not match planned branch/base"
        )
      return WorktreeInfo(
        workspace_id=workspace_id,
        path=path,
        branch=branch,
        head=head,
      )
    except Exception:
      if created:
        self._rollback_created_worktree(path, branch_name)
      elif _ref_exists(self.root, branch_ref):
        self._delete_new_branch_if_safe(branch_name, base_sha)
      raise

  def retire(
    self,
    workspace_id: str,
    worktree_path: Path,
    branch_name: str,
    *,
    delete_branch: bool = False,
  ) -> None:
    _workspace_id(workspace_id)
    path = Path(worktree_path).resolve()
    _non_empty_text(branch_name, "branch_name")

    matches = [
      item
      for item in self._registered_worktrees()
      if item.path == path
    ]
    if len(matches) != 1:
      raise WorktreeError(
        f"worktree is not registered exactly once: {path}"
      )
    item = matches[0]
    if item.branch != branch_name:
      raise WorktreeError(
        f"worktree branch mismatch: expected {branch_name}, "
        f"found {item.branch}"
      )

    if _has_protected_local_work(path):
      raise WorktreeError(
        f"protected local work prevents retirement: {path}"
      )

    result = git(
      self.root,
      "worktree",
      "remove",
      str(path),
      check=False,
    )
    if result.returncode:
      raise WorktreeError(
        _git_failure("git worktree remove failed", result)
      )
    git(self.root, "worktree", "prune")

    if delete_branch:
      result = git(
        self.root,
        "branch",
        "-d",
        branch_name,
        check=False,
      )
      if result.returncode:
        raise WorktreeError(
          _git_failure(
            "worktree removed but safe branch deletion failed",
            result,
          )
        )

    if any(
      entry.path == path
      for entry in self._registered_worktrees()
    ):
      raise WorktreeError(
        f"worktree remains registered after retirement: {path}"
      )

  def _registered_worktrees(self) -> tuple[_RegisteredWorktree, ...]:
    output = git(
      self.root,
      "worktree",
      "list",
      "--porcelain",
    ).stdout
    entries: list[_RegisteredWorktree] = []
    current: dict[str, str] = {}

    def finish() -> None:
      if "worktree" not in current:
        current.clear()
        return
      branch = current.get("branch")
      if branch and branch.startswith("refs/heads/"):
        branch = branch[len("refs/heads/"):]
      entries.append(_RegisteredWorktree(
        path=Path(current["worktree"]).resolve(),
        head=current.get("HEAD", ""),
        branch=branch,
      ))
      current.clear()

    for line in output.splitlines():
      if not line:
        finish()
        continue
      key, _, value = line.partition(" ")
      if key in {"worktree", "HEAD", "branch"}:
        current[key] = value
    finish()
    return tuple(entries)

  def _rollback_created_worktree(
    self,
    path: Path,
    branch_name: str,
  ) -> None:
    if path.exists():
      status = git(
        path,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        check=False,
      )
      if status.returncode == 0 and status.stdout.strip():
        return

    git(
      self.root,
      "worktree",
      "remove",
      str(path),
      check=False,
    )
    git(self.root, "worktree", "prune", check=False)

    branch_ref = f"refs/heads/{branch_name}"
    if _ref_exists(self.root, branch_ref):
      git(
        self.root,
        "branch",
        "-d",
        branch_name,
        check=False,
      )

  def _delete_new_branch_if_safe(
    self,
    branch_name: str,
    base_sha: str,
  ) -> None:
    branch_ref = f"refs/heads/{branch_name}"
    try:
      if _rev_parse(self.root, branch_ref) != base_sha:
        return
    except WorktreeError:
      return
    git(
      self.root,
      "branch",
      "-d",
      branch_name,
      check=False,
    )


def _workspace_id(value: str) -> str:
  if not isinstance(value, str) or not WORKSPACE_ID_RE.fullmatch(value):
    raise WorktreeError(f"invalid workspace id: {value!r}")
  return value


def _non_empty_text(value: str, name: str) -> None:
  if not isinstance(value, str) or not value.strip():
    raise WorktreeError(f"{name} must be non-empty text")


def _rev_parse(root: Path, ref: str) -> str:
  result = git(
    root,
    "rev-parse",
    "--verify",
    ref,
    check=False,
  )
  if result.returncode:
    raise WorktreeError(
      _git_failure(f"cannot resolve {ref}", result)
    )
  return result.stdout.strip()


def _ref_exists(root: Path, ref: str) -> bool:
  return git(
    root,
    "show-ref",
    "--verify",
    "--quiet",
    ref,
    check=False,
  ).returncode == 0


def _has_protected_local_work(path: Path) -> bool:
  result = git(
    path,
    "status",
    "--porcelain=v1",
    "--untracked-files=all",
    check=False,
  )
  if result.returncode:
    return True
  if result.stdout.strip():
    return True

  for marker in (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "rebase-merge",
    "rebase-apply",
  ):
    marker_result = git(
      path,
      "rev-parse",
      "--git-path",
      marker,
      check=False,
    )
    if marker_result.returncode:
      return True
    marker_path = Path(marker_result.stdout.strip())
    if not marker_path.is_absolute():
      marker_path = (path / marker_path).resolve()
    if marker_path.exists():
      return True
  return False


def _git_failure(prefix: str, result) -> str:
  detail = (
    result.stderr
    or result.stdout
    or "git command failed"
  ).strip()
  return f"{prefix}: {detail}"
