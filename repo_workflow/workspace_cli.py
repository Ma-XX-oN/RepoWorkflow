from __future__ import annotations

import json
import os
from pathlib import Path

from .git import git
from .issue_start import start_issue
from .relationship_store import RelationshipStore
from .workspace_store import WorkspaceClaimError, WorkspaceStore
from .workspace_worktree import WorktreeBackend, WorktreeError
from .workspace_readiness import readiness_json


class WorkspaceCommandError(RuntimeError):
  """Raised when a public workspace command cannot be completed safely."""


def _identity() -> tuple[str, str | None]:
  worker = os.environ.get("RWF_WORKER_ID", "").strip()
  if not worker:
    raise WorkspaceCommandError(
      "RWF_WORKER_ID is required for workspace ownership operations"
    )
  session = os.environ.get("RWF_SESSION_ID")
  if session is not None:
    session = session.strip() or None
  return worker, session


def _workspace_id(issue: int) -> str:
  return f"RWF-{issue}"


def _branch_name(issue: int) -> str:
  return f"rwf-workspace-{issue}"


def _worktree_path(root: Path, workspace_id: str) -> Path:
  return (root.resolve().parent / f"{root.resolve().name}-{workspace_id}").resolve()


def _base(root: Path, issue: int) -> tuple[str, str]:
  try:
    relation = RelationshipStore(root).issue(issue)
  except Exception as error:
    raise WorkspaceCommandError(
      f"issue {issue} has no registered canonical relationships"
    ) from error
  branch = relation.branch_base
  if branch is None:
    raise WorkspaceCommandError(
      f"issue {issue} has no canonical branch base"
    )
  sha = git(root, "rev-parse", "--verify", branch).stdout.strip()
  return branch, sha


def _combined(store: WorkspaceStore, workspace_id: str) -> dict:
  value = dict(store.read_workspace(workspace_id))
  value["claim"] = store.read_claim(workspace_id)
  return value


def _current_workspace(store: WorkspaceStore, root: Path) -> str:
  current = root.resolve()
  matches = [
    value["workspace_id"]
    for value in store.list_workspaces()
    if Path(value["worktree_path"]).resolve() == current
  ]
  if len(matches) != 1:
    raise WorkspaceCommandError(
      "workspace must be specified outside a registered workspace worktree"
    )
  return matches[0]


def _print(value: dict) -> None:
  print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def handle_workspace(root: Path, words: list[str]) -> int:
  store = WorkspaceStore(root)
  action = words[1]

  if action == "ready":
    print(json.dumps(readiness_json(root), sort_keys=True, separators=(",", ":")))
    return 0

  if action == "list":
    for workspace in store.list_workspaces():
      claim = store.read_claim(workspace["workspace_id"])
      print(
        f'{workspace["workspace_id"]}\t'
        f'issue={workspace["issue"]}\t'
        f'status={claim["status"]}\t'
        f'branch={workspace["branch"]}\t'
        f'path={workspace["worktree_path"]}'
      )
    return 0

  if action == "create":
    issue = int(words[2])
    workspace_id = _workspace_id(issue)
    branch = _branch_name(issue)
    path = _worktree_path(root, workspace_id)
    base_ref, base_sha = _base(root, issue)
    backend = WorktreeBackend(root)
    backend.provision(
      workspace_id,
      base_ref,
      base_sha,
      branch,
      path,
    )
    try:
      start_issue(path, issue)
      workspace = store.create(
        workspace_id,
        issue=issue,
        work_identity=f"issue-{issue}",
        branch=branch,
        worktree_path=path,
      )
    except Exception:
      backend.retire(workspace_id, path, branch, delete_branch=True)
      raise
    _print(_combined(store, workspace["workspace_id"]))
    return 0

  if action == "info":
    workspace_id = words[2] if len(words) == 3 else _current_workspace(store, root)
    _print(_combined(store, workspace_id))
    return 0

  workspace_id = words[2]
  claim = store.read_claim(workspace_id)
  worker, session = _identity()

  if action == "claim":
    updated = store.update_claim(
      workspace_id,
      claim["revision"],
      "claimed",
      worker,
      session,
    )
  elif action == "release":
    updated = store.update_claim(
      workspace_id,
      claim["revision"],
      "available",
      worker,
      session,
    )
  elif action == "resume":
    if claim["status"] not in {"claimed", "blocked"}:
      raise WorkspaceCommandError(
        f"workspace {workspace_id} cannot resume from {claim['status']}"
      )
    updated = store.update_claim(
      workspace_id,
      claim["revision"],
      "claimed",
      worker,
      session,
    )
  elif action == "close":
    updated = store.update_claim(
      workspace_id,
      claim["revision"],
      "closed",
      worker,
      session,
    )
  else:
    raise AssertionError("unreachable workspace command")

  _print(updated)
  return 0
