"""Provider-backed immutable PRELIM validation and acceptance audit.

The #569-#572 terminal publisher exclusively owns Git test-result tags.
These durable branches preserve already authenticated #102 state records.
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


def _identity(attempt: str) -> tuple[str, str, str]:
  return (
    "refs/heads/prelim-identity-state/" + attempt,
    "prelim/identities/" + attempt,
    "identity-" + attempt,
  )


def _validation(attempt: str, regression: str,
                integration: str) -> tuple[str, str, str]:
  suffix = regression + "-" + integration
  return (
    "refs/heads/prelim-validation-state/" + attempt + "/" + suffix,
    "prelim/validations/" + attempt + "/" + suffix,
    "validation-" + attempt + "-" + regression[:12] + "-" + integration[:12],
  )


def _remote_record(root: Path, remote: str, ref: str, key: str):
  target = _remote_ref(root, remote, ref)
  if target is None:
    return None
  git(root, "fetch", "--no-tags", remote, ref)
  if git(root, "cat-file", "-e", target + "^{commit}",
         check=False).returncode:
    raise PrelimPublicationError("published state object unavailable")
  relative = ".repoworkflow/state/" + key + ".json"
  try:
    record = json.loads(git(root, "show", target + ":" + relative).stdout)
    _validate_record(record, key)
  except (ValueError, TypeError, KeyError, StateStoreError, GitError) as error:
    raise PrelimPublicationError("published PRELIM state is malformed") from error
  if _remote_ref(root, remote, ref) != target:
    raise PrelimPublicationError("published PRELIM state ref moved")
  return record


def _restore(root: Path, remote: str, ref: str, key: str) -> None:
  root = Path(root).resolve()
  store = durable_store(root)
  record = _remote_record(root, remote, ref, key)
  if record is None:
    return
  path = store._path(key)
  if path.exists():
    if store.read(key) != record:
      raise PrelimPublicationError("local/provider PRELIM state disagree")
    return
  _write_json_atomic(path, record)
  if store.read(key) != record:
    raise PrelimPublicationError("restored PRELIM state readback differs")


def _publish(root: Path, remote: str, ref: str, key: str,
             workspace_id: str, record: dict, base_sha: str) -> None:
  root = Path(root).resolve()
  store = durable_store(root)
  with _attempt_lock(root, store, workspace_id):
    existing = _remote_record(root, remote, ref, key)
    if existing is not None:
      if existing != record:
        raise PrelimPublicationError("immutable provider PRELIM collision")
      return
    # Restore the original local publication commit after remote ref loss.
    # Reconstructing a new commit would break immutable provider identity.
    local = git(root, "show-ref", "--verify", ref, check=False)
    if local.returncode == 0:
      original = local.stdout.split()[0]
      relative = ".repoworkflow/state/" + key + ".json"
      try:
        saved = json.loads(git(root, "show", original + ":" + relative).stdout)
      except (ValueError, GitError) as error:
        raise PrelimPublicationError("local PRELIM identity ref is invalid") from error
      if saved != record:
        raise PrelimPublicationError("local PRELIM publication ref differs")
      git(root, "push", remote, ref + ":" + ref)
      if _remote_record(root, remote, ref, key) != record:
        raise PrelimPublicationError("republished PRELIM state differs")
      return
    if local.returncode != 1:
      raise PrelimPublicationError("cannot verify local PRELIM ref")
    workspace = _workspace(root, workspace_id)
    if not workspace.exists():
      workspace.parent.mkdir(parents=True, exist_ok=True)
      git(root, "worktree", "add", "--detach", str(workspace), base_sha)
    relative = ".repoworkflow/state/" + key + ".json"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
      try:
        prior = json.loads(path.read_text(encoding="utf-8"))
      except (ValueError, OSError) as error:
        raise PrelimPublicationError("partial PRELIM state invalid") from error
      if prior != record:
        raise PrelimPublicationError("partial PRELIM state differs")
    else:
      path.write_text(json.dumps(record, sort_keys=True, indent=2)
                      + "\n", encoding="utf-8")
    subject = git(workspace, "log", "-1", "--format=%s").stdout.strip()
    expected = "Durable PRELIM state " + workspace_id
    if subject != expected:
      git(workspace, "add", "--", relative)
      git(workspace, "commit", "-m", expected)
    committed = git(workspace, "rev-parse", "HEAD").stdout.strip()
    expected_payload = json.dumps(record, sort_keys=True, indent=2) + "\n"
    if git(workspace, "show", committed + ":" + relative).stdout != expected_payload:
      raise PrelimPublicationError("committed PRELIM state payload differs")
    local = git(root, "show-ref", "--verify", ref, check=False)
    if local.returncode:
      git(root, "update-ref", ref, committed, "0" * 40)
    elif local.stdout.split()[0] != committed:
      raise PrelimPublicationError("local PRELIM state ref conflicts")
    pushed = git(root, "push", remote, ref + ":" + ref, check=False)
    if pushed.returncode and _remote_record(root, remote, ref, key) != record:
      raise PrelimPublicationError("provider PRELIM publication rejected")
    if _remote_record(root, remote, ref, key) != record:
      raise PrelimPublicationError("provider PRELIM readback differs")
    git(root, "worktree", "remove", str(workspace))


def restore_identity(root: Path, remote: str, attempt: str) -> None:
  ref, key, _ = _identity(attempt)
  _restore(root, remote, ref, key)


def publish_identity(
  root: Path, remote: str, attempt: str, record: dict, base_sha: str,
) -> None:
  ref, key, workspace = _identity(attempt)
  _publish(root, remote, ref, key, workspace, record, base_sha)


def restore_validation(
  root: Path, remote: str, attempt: str,
  regression: str, integration: str,
) -> None:
  ref, key, _ = _validation(attempt, regression, integration)
  _restore(root, remote, ref, key)


def publish_validation(
  root: Path, remote: str, attempt: str, regression: str, integration: str,
  record: dict, base_sha: str,
) -> None:
  ref, key, workspace = _validation(attempt, regression, integration)
  _publish(root, remote, ref, key, workspace, record, base_sha)
