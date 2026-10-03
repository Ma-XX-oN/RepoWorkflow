from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import time

from .git import git


WORKSPACE_SCHEMA_VERSION = 1
CLAIM_STATUSES = {"available", "claimed", "blocked", "closed"}
WORKSPACE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")


class WorkspaceClaimError(RuntimeError):
  """Raised when workspace state or claim mutation is invalid."""


class WorkspaceStore:
  """Clone-common repository-local workspace records and CAS claims."""

  def __init__(self, root: Path):
    self.root = root.resolve()
    common = git(self.root, "rev-parse", "--git-common-dir").stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
      common_path = (self.root / common_path).resolve()
    self.common_dir = common_path
    self.workspaces_root = self.common_dir / "repoworkflow" / "workspaces"

  def workspace_dir(self, workspace_id: str) -> Path:
    return self.workspaces_root / _workspace_id(workspace_id)

  def create(
    self,
    workspace_id: str,
    *,
    issue: int,
    work_identity: str,
  ) -> dict:
    workspace_id = _workspace_id(workspace_id)
    if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
      raise WorkspaceClaimError(f"invalid issue number: {issue!r}")
    if not isinstance(work_identity, str) or not work_identity.strip():
      raise WorkspaceClaimError("work_identity must be non-empty text")

    directory = self.workspace_dir(workspace_id)
    try:
      directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
      raise WorkspaceClaimError(
        f"workspace {workspace_id} already exists"
      ) from error

    workspace = {
      "schema_version": WORKSPACE_SCHEMA_VERSION,
      "workspace_id": workspace_id,
      "issue": issue,
      "work_identity": work_identity,
    }
    claim = {
      "schema_version": WORKSPACE_SCHEMA_VERSION,
      "workspace_id": workspace_id,
      "status": "available",
      "revision": 0,
      "worker_id": None,
      "session_id": None,
    }

    try:
      _write_json_atomic(directory / "workspace.json", workspace)
      _write_json_atomic(directory / "claim.json", claim)
    except Exception:
      for name in ("claim.json", "workspace.json"):
        try:
          (directory / name).unlink()
        except FileNotFoundError:
          pass
      try:
        directory.rmdir()
      except OSError:
        pass
      raise
    return workspace

  def read_workspace(self, workspace_id: str) -> dict:
    path = self.workspace_dir(workspace_id) / "workspace.json"
    value = _read_json(path, "workspace")
    _validate_workspace(value, _workspace_id(workspace_id))
    return value

  def read_claim(self, workspace_id: str) -> dict:
    path = self.workspace_dir(workspace_id) / "claim.json"
    value = _read_json(path, "claim")
    _validate_claim(value, _workspace_id(workspace_id))
    return value

  def update_claim(
    self,
    workspace_id: str,
    expected_revision: int,
    status: str,
    worker_id: str | None = None,
    session_id: str | None = None,
  ) -> dict:
    workspace_id = _workspace_id(workspace_id)
    if isinstance(expected_revision, bool) or not isinstance(
      expected_revision,
      int,
    ) or expected_revision < 0:
      raise WorkspaceClaimError("expected revision must be non-negative")
    if status not in CLAIM_STATUSES:
      raise WorkspaceClaimError(f"invalid claim status: {status!r}")

    directory = self.workspace_dir(workspace_id)
    lock = directory / "claim.lock"
    _acquire_lock(lock)
    try:
      current = self.read_claim(workspace_id)
      revision = current["revision"]
      if revision != expected_revision:
        raise WorkspaceClaimError(
          f"stale claim revision for {workspace_id}: "
          f"expected {expected_revision}, current {revision}"
        )

      source = current["status"]
      legal = {
        "available": {"claimed", "closed"},
        "claimed": {"available", "claimed", "blocked", "closed"},
        "blocked": {"claimed", "closed"},
        "closed": set(),
      }
      if status not in legal[source]:
        raise WorkspaceClaimError(
          f"illegal claim transition: {source} -> {status}"
        )

      owner = current["worker_id"]
      if source in {"claimed", "blocked"} and worker_id != owner:
        raise WorkspaceClaimError(
          f"workspace {workspace_id} is owned by {owner}"
        )

      if status in {"claimed", "blocked"}:
        if not isinstance(worker_id, str) or not worker_id.strip():
          raise WorkspaceClaimError(
            f"{status} workspace requires worker_id"
          )
        next_worker = worker_id
        next_session = session_id
      else:
        next_worker = None
        next_session = None

      updated = dict(current)
      updated.update({
        "status": status,
        "revision": revision + 1,
        "worker_id": next_worker,
        "session_id": next_session,
      })
      _validate_claim(updated, workspace_id)
      _write_json_atomic(directory / "claim.json", updated)
      return updated
    finally:
      try:
        lock.rmdir()
      except FileNotFoundError:
        pass


def _workspace_id(value: str) -> str:
  if not isinstance(value, str) or not WORKSPACE_ID_RE.fullmatch(value):
    raise WorkspaceClaimError(f"invalid workspace id: {value!r}")
  return value


def _read_json(path: Path, kind: str) -> dict:
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as error:
    raise WorkspaceClaimError(f"{kind} record is missing: {path}") from error
  except json.JSONDecodeError as error:
    raise WorkspaceClaimError(f"{kind} record is invalid JSON: {path}") from error
  if not isinstance(value, dict):
    raise WorkspaceClaimError(f"{kind} record must be an object: {path}")
  return value


def _validate_workspace(value: dict, workspace_id: str) -> None:
  if value.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
    raise WorkspaceClaimError("unsupported workspace schema version")
  if value.get("workspace_id") != workspace_id:
    raise WorkspaceClaimError("workspace id mismatch")
  issue = value.get("issue")
  if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
    raise WorkspaceClaimError("workspace issue must be a positive integer")
  identity = value.get("work_identity")
  if not isinstance(identity, str) or not identity.strip():
    raise WorkspaceClaimError("workspace work_identity must be non-empty text")


def _validate_claim(value: dict, workspace_id: str) -> None:
  if value.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
    raise WorkspaceClaimError("unsupported claim schema version")
  if value.get("workspace_id") != workspace_id:
    raise WorkspaceClaimError("claim workspace id mismatch")
  if value.get("status") not in CLAIM_STATUSES:
    raise WorkspaceClaimError("invalid stored claim status")
  revision = value.get("revision")
  if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
    raise WorkspaceClaimError("claim revision must be non-negative")
  worker = value.get("worker_id")
  if value["status"] in {"claimed", "blocked"}:
    if not isinstance(worker, str) or not worker.strip():
      raise WorkspaceClaimError("owned claim requires worker_id")
  elif worker is not None:
    raise WorkspaceClaimError("unowned claim must have null worker_id")


def _write_json_atomic(path: Path, value: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary = tempfile.mkstemp(
    prefix=f".{path.name}.",
    suffix=".tmp",
    dir=path.parent,
  )
  temporary_path = Path(temporary)
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
      json.dump(value, handle, indent=2, sort_keys=True)
      handle.write("\n")
      handle.flush()
      os.fsync(handle.fileno())
    os.replace(temporary_path, path)
  finally:
    try:
      temporary_path.unlink()
    except FileNotFoundError:
      pass


def _acquire_lock(path: Path, timeout: float = 5.0) -> None:
  deadline = time.monotonic() + timeout
  while True:
    try:
      path.mkdir()
      return
    except FileExistsError:
      if time.monotonic() >= deadline:
        raise WorkspaceClaimError(f"workspace claim lock is busy: {path}")
      time.sleep(0.01)
