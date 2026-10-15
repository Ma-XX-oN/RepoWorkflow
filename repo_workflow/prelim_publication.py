"""Provider-backed immutable PRELIM acceptance identity.

The stable tag publisher belongs to #569-#572. This module only persists
an already authenticated #102 acceptance record on an ephemeral state ref.
"""
from __future__ import annotations

import json
from pathlib import Path

from .git import GitError, git
from .prelim_attempt import _attempt_lock, _remote_ref, _workspace
from .state_store import (
  StateStoreError, _validate_record, _write_json_atomic, durable_store,
)


class PrelimPublicationError(ValueError):
  pass


def _ref(attempt: str) -> str:
  return "refs/heads/prelim-identity-state/" + attempt


def _key(attempt: str) -> str:
  return "prelim/identities/" + attempt


def _remote_record(root: Path, remote: str, attempt: str):
  ref = _ref(attempt)
  target = _remote_ref(root, remote, ref)
  if target is None:
    return None
  git(root, "fetch", "--no-tags", remote, ref)
  if git(root, "cat-file", "-e", target + "^{commit}",
         check=False).returncode:
    raise PrelimPublicationError("published identity object unavailable")
  path = ".repoworkflow/state/" + _key(attempt) + ".json"
  try:
    record = json.loads(git(root, "show", target + ":" + path).stdout)
    _validate_record(record, _key(attempt))
  except (ValueError, TypeError, KeyError, StateStoreError, GitError) as error:
    raise PrelimPublicationError("published PRELIM identity is malformed") from error
  if _remote_ref(root, remote, ref) != target:
    raise PrelimPublicationError("published PRELIM identity ref moved")
  return record


def restore_identity(root: Path, remote: str, attempt: str) -> None:
  """Restore precisely the provider record, never synthesize a new writer."""
  root = Path(root).resolve()
  store = durable_store(root)
  remote_record = _remote_record(root, remote, attempt)
  if remote_record is None:
    return
  path = store._path(_key(attempt))
  if path.exists():
    if store.read(_key(attempt)) != remote_record:
      raise PrelimPublicationError("local/provider identity disagree")
    return
  _write_json_atomic(path, remote_record)
  if store.read(_key(attempt)) != remote_record:
    raise PrelimPublicationError("restored identity readback differs")


def publish_identity(
  root: Path, remote: str, attempt: str, record: dict, base_sha: str,
) -> None:
  """Idempotent publication with authoritative provider readback and no tags."""
  root = Path(root).resolve()
  store = durable_store(root)
  with _attempt_lock(root, store, "identity-" + attempt):
    current = _remote_record(root, remote, attempt)
    if current is not None:
      if current != record:
        raise PrelimPublicationError("immutable provider identity collision")
      return
    ref = _ref(attempt)
    workspace = _workspace(root, "identity-" + attempt)
    if not workspace.exists():
      workspace.parent.mkdir(parents=True, exist_ok=True)
      git(root, "worktree", "add", "--detach", str(workspace), base_sha)
    relative = ".repoworkflow/state/" + _key(attempt) + ".json"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
      try:
        existing = json.loads(path.read_text(encoding="utf-8"))
      except (ValueError, OSError) as error:
        raise PrelimPublicationError("partial identity record invalid") from error
      if existing != record:
        raise PrelimPublicationError("partial identity record differs")
    else:
      path.write_text(json.dumps(record, sort_keys=True, indent=2)
                      + "\n", encoding="utf-8")
    subject = git(workspace, "log", "-1", "--format=%s").stdout.strip()
    expected = "Durable PRELIM validation " + attempt
    if subject != expected:
      git(workspace, "add", "--", relative)
      git(workspace, "commit", "-m", expected)
    committed = git(workspace, "rev-parse", "HEAD").stdout.strip()
    if git(workspace, "show", committed + ":" + relative).stdout != (
      json.dumps(record, sort_keys=True, indent=2) + "\n"
    ):
      raise PrelimPublicationError("committed identity payload differs")
    # Existing local ref after interruption is reusable only when exact.
    local = git(root, "show-ref", "--verify", ref, check=False)
    if local.returncode:
      git(root, "update-ref", ref, committed, "0" * 40)
    elif local.stdout.split()[0] != committed:
      raise PrelimPublicationError("local identity state ref conflicts")
    pushed = git(root, "push", remote, ref + ":" + ref, check=False)
    if pushed.returncode and _remote_record(root, remote, attempt) != record:
      raise PrelimPublicationError("provider identity publication rejected")
    if _remote_record(root, remote, attempt) != record:
      raise PrelimPublicationError("provider identity readback differs")
    git(root, "worktree", "remove", str(workspace))
