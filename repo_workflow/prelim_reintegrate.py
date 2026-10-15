"""Reintegrate a stale PRELIM physical candidate without inheriting GREEN.

#83: retain the old candidate's integration-specific changes and resolutions
by merging that exact commit into an updated authoritative-main worktree.
The result has a new GUID, branch, SHA, and unvalidated durable state.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import uuid

from .git import git
from .lifecycle_store import LifecycleStore
from .prelim_attempt import (
  PrelimError, _attempt_lock, _local_ref,
  _record, _remote_ref, _workspace, _restore_remote_record,
)
from .prelim_identity import validate_attempt
from .runtime_identity import runtime_writer_identity
from .state_store import (
  StateStoreError, durable_store, _validate_record, _write_json_atomic,
)

SHA = re.compile(r"[0-9a-f]{40}\Z")


class ReintegrationError(PrelimError):
  pass


@dataclass(frozen=True)
class Reintegration:
  guid: str
  previous_guid: str
  branch: str
  state: str
  candidate: str | None
  base: str
  revision: int
  fresh_validation_required: bool = True


def _guid(value):
  try:
    canonical = str(uuid.UUID(value))
  except (TypeError, ValueError, AttributeError) as error:
    raise ReintegrationError("invalid GUID") from error
  if value != canonical:
    raise ReintegrationError("noncanonical GUID")
  return value


def _key(guid):
  return f"prelim/reintegrations/{guid}"


def _validate(value):
  expected = {
    "guid", "previous_guid", "issue", "source_ref", "source_sha",
    "lifecycle_revision", "previous_base", "previous_candidate",
    "new_base", "branch", "state", "candidate", "proposed_version",
    "fresh_validation_required", "inherited_evidence",
  }
  if not isinstance(value, dict) or set(value) != expected:
    raise ReintegrationError("invalid reintegration schema")
  guid = _guid(value["guid"])
  if _guid(value["previous_guid"]) == guid:
    raise ReintegrationError("old attempt GUID was reused")
  if value["branch"] != f"prelim-main-{guid}":
    raise ReintegrationError("attempt branch identity changed")
  if value["fresh_validation_required"] is not True:
    raise ReintegrationError("fresh validation cannot be omitted")
  if value["inherited_evidence"] is not False:
    raise ReintegrationError("old GREEN/PRELIM cannot be inherited")
  if value["state"] not in {"prepared", "conflict", "ready"}:
    raise ReintegrationError("unknown attempt state")
  for key in ("source_sha", "previous_base", "previous_candidate", "new_base"):
    if not isinstance(value[key], str) or SHA.fullmatch(value[key]) is None:
      raise ReintegrationError("invalid exact Git identity")
  if value["state"] == "ready":
    if not isinstance(value["candidate"], str) or SHA.fullmatch(value["candidate"]) is None:
      raise ReintegrationError("ready result lacks exact candidate")
  elif value["candidate"] is not None:
    raise ReintegrationError("unready result has candidate identity")
  issue = value["issue"]
  if not isinstance(issue, str) or not re.fullmatch(r"[1-9][0-9]*", issue):
    raise ReintegrationError("invalid issue")
  if not isinstance(value["source_ref"], str) or not re.fullmatch(
    rf"refs/heads/issue-{issue}(?:-[A-Za-z0-9._/-]+)?",
    value["source_ref"],
  ):
    raise ReintegrationError("source does not belong to issue")
  if type(value["lifecycle_revision"]) is not int or value["lifecycle_revision"] < 0:
    raise ReintegrationError("invalid lifecycle revision")
  if not isinstance(value["proposed_version"], str):
    raise ReintegrationError("prior proposed version is missing")


def _read(store, guid):
  try:
    record = store.read(_key(guid))
  except StateStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise
  _validate(record["value"])
  return record


def _restore(root, store, remote, guid):
  """Recover a new attempt from exact provider bytes in another clone."""
  ref = f"refs/heads/prelim-reintegration-state/{guid}"
  tip = _remote_ref(root, remote, ref)
  if tip is None:
    return None
  git(root, "fetch", "--no-tags", remote, ref)
  if git(root, "cat-file", "-e", tip + "^{commit}",
         check=False).returncode:
    raise ReintegrationError("remote reintegration record is unavailable")
  path = f".repoworkflow/state/{_key(guid)}.json"
  try:
    payload = json.loads(git(root, "show", f"{tip}:{path}").stdout)
    _validate_record(payload, _key(guid))
    _validate(payload["value"])
  except (ValueError, StateStoreError, KeyError, TypeError) as error:
    raise ReintegrationError("invalid remote reintegration record") from error
  if (payload["value"]["guid"] != guid
      or payload["value"]["state"] != "ready"
      or _remote_ref(root, remote, ref) != tip):
    raise ReintegrationError("remote reintegration record changed")
  target = store._path(_key(guid))
  if target.exists():
    if store.read(_key(guid)) != payload:
      raise ReintegrationError("local/provider reintegration record conflict")
  else:
    _write_json_atomic(target, payload)
  if store.read(_key(guid)) != payload:
    raise ReintegrationError("restored reintegration record mismatch")
  return payload


def _fetch_new_base(root, remote, base, guid):
  """Acquire server main into an attempt-private ref without origin/main races."""
  ref = f"refs/repoworkflow/prelim-fetch/{guid}"
  if git(root, "cat-file", "-e", base + "^{commit}",
         check=False).returncode:
    # An empty refmap suppresses remote.origin.fetch's implicit origin/main
    # update, which otherwise races across different GUIDs in one clone.
    git(root, "fetch", "--refmap=", "--no-tags", "--no-write-fetch-head",
        remote, f"refs/heads/main:{ref}")
    if git(root, "cat-file", "-e", base + "^{commit}",
           check=False).returncode:
      raise ReintegrationError("authoritative main object unavailable")
  if _remote_ref(root, remote, "refs/heads/main") != base:
    raise ReintegrationError("main changed during exact object acquisition")


def _source(root, value):
  if _local_ref(root, value["source_ref"]) != value["source_sha"]:
    raise ReintegrationError("accepted source ref moved")
  state = LifecycleStore(root).read(value["issue"])
  if (state.revision != value["lifecycle_revision"]
      or state.lifecycle.state != "accepted"
      or not state.lifecycle.history
      or state.lifecycle.history[-1].candidate != value["source_sha"]):
    raise ReintegrationError("accepted source lifecycle changed")


def _previous(root, store, remote, guid):
  record = _record(store, guid)
  if record is None:
    record = _restore_remote_record(root, remote, store, guid)
  if record is None:
    raise ReintegrationError("prior PRELIM attempt unavailable")
  old = record["value"]
  validate_attempt(old)
  if old["state"] != "ready":
    raise ReintegrationError("prior attempt is not ready")
  _source(root, old)
  ref = f"refs/heads/{old['branch']}"
  if _remote_ref(root, remote, ref) != old["candidate_sha"]:
    raise ReintegrationError("remote old PRELIM candidate has moved")
  if git(root, "cat-file", "-e", old["candidate_sha"] + "^{commit}",
         check=False).returncode:
    git(root, "fetch", "--no-tags", remote, ref)
  if _remote_ref(root, remote, ref) != old["candidate_sha"]:
    raise ReintegrationError("old candidate changed while fetching")
  for parent in (old["base_sha"], old["source_sha"]):
    if git(root, "merge-base", "--is-ancestor", parent, old["candidate_sha"],
           check=False).returncode:
      raise ReintegrationError("prior physical candidate lost ancestry")
  return old


def _save(store, record, **changes):
  value = {**record["value"], **changes}
  _validate(value)
  return store.replace(record["key"], record["revision"], value,
                       runtime_writer_identity())


def _snapshot(record):
  v = record["value"]
  return Reintegration(v["guid"], v["previous_guid"], v["branch"],
                       v["state"], v["candidate"], v["new_base"],
                       record["revision"])


def _publish(root, remote, record):
  v = record["value"]
  _validate(v)
  if v["state"] != "ready":
    raise ReintegrationError("unready candidate cannot be published")
  ref = f"refs/heads/{v['branch']}"
  actual = _remote_ref(root, remote, ref)
  if actual is not None and actual != v["candidate"]:
    raise ReintegrationError("published candidate differs")
  local = _local_ref(root, ref)
  if local is None and actual == v["candidate"]:
    git(root, "fetch", "--no-tags", remote, f"{ref}:{ref}")
    local = _local_ref(root, ref)
  if local != v["candidate"]:
    raise ReintegrationError("candidate local identity unavailable or changed")
  if actual is None:
    git(root, "push", remote, f"{ref}:{ref}")
  if _remote_ref(root, remote, ref) != v["candidate"]:
    raise ReintegrationError("candidate provider readback failed")
  state_ref = f"refs/heads/prelim-reintegration-state/{v['guid']}"
  path = f".repoworkflow/state/{record['key']}.json"
  existing = _local_ref(root, state_ref)
  if existing is None and _remote_ref(root, remote, state_ref) is not None:
    git(root, "fetch", "--no-tags", remote,
        f"{state_ref}:{state_ref}")
    existing = _local_ref(root, state_ref)
  if existing is None:
    folder = _workspace(root, "reintegration-state-" + v["guid"])
    folder.parent.mkdir(parents=True, exist_ok=True)
    if not folder.exists():
      git(root, "worktree", "add", "--detach", str(folder), v["new_base"])
    dest = folder / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and json.loads(dest.read_text()) != record:
      raise ReintegrationError("unexpected state publication workspace")
    if not dest.exists():
      dest.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    git(folder, "add", "--", path)
    message = f"Durable PRELIM reintegration {v['guid']}"
    if git(folder, "log", "-1", "--format=%s").stdout.strip() != message:
      git(folder, "commit", "-m", message)
    sha = git(folder, "rev-parse", "HEAD").stdout.strip()
    git(root, "update-ref", state_ref, sha, "0" * 40)
    git(root, "worktree", "remove", str(folder))
  advertised = _remote_ref(root, remote, state_ref)
  if advertised is None:
    git(root, "push", remote, f"{state_ref}:{state_ref}")
    advertised = _remote_ref(root, remote, state_ref)
  elif advertised != _local_ref(root, state_ref):
    raise ReintegrationError("remote state ref identity changed")
  git(root, "fetch", "--no-tags", remote, state_ref)
  stored = json.loads(git(root, "show", f"{advertised}:{path}").stdout)
  if stored != record or _remote_ref(root, remote, state_ref) != advertised:
    raise ReintegrationError("remote state record readback mismatch")


def _complete(root, store, remote, record):
  v = record["value"]
  _validate(v)
  if _remote_ref(root, remote, "refs/heads/main") != v["new_base"]:
    raise ReintegrationError("main moved again; another GUID required")
  old = _previous(root, store, remote, v["previous_guid"])
  if (old["source_sha"] != v["source_sha"]
      or old["candidate_sha"] != v["previous_candidate"]
      or old["base_sha"] != v["previous_base"]):
    raise ReintegrationError("previous candidate identity changed")
  if v["state"] == "ready":
    _publish(root, remote, record)
    return _snapshot(record)
  folder = _workspace(root, "reintegration-" + v["guid"])
  if not folder.exists():
    folder.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", str(folder), v["new_base"])
  merging = git(folder, "rev-parse", "MERGE_HEAD", check=False).returncode == 0
  if not merging:
    tip = git(folder, "rev-parse", "HEAD").stdout.strip()
    if tip == v["new_base"]:
      if git(folder, "status", "--porcelain").stdout.strip():
        raise ReintegrationError("dirty reintegration workspace")
      result = git(folder, "merge", "--no-ff", "--no-commit",
                   v["previous_candidate"], check=False)
      if result.returncode and git(folder, "rev-parse", "MERGE_HEAD",
                                   check=False).returncode:
        raise ReintegrationError("merge aborted without recoverable conflicts")
      merging = git(folder, "rev-parse", "MERGE_HEAD",
                    check=False).returncode == 0
      if not merging:
        # The previous candidate may already be an ancestor of new main.
        # Create a fresh physical identity without laundering old evidence.
        if git(folder, "merge-base", "--is-ancestor",
               v["previous_candidate"], v["new_base"],
               check=False).returncode:
          raise ReintegrationError("candidate merge produced no merge state")
        git(folder, "commit", "--allow-empty", "-m",
            f"Reintegrate PRELIM {v['guid']}")
    elif git(folder, "log", "-1", "--format=%s").stdout.strip() != (
        f"Reintegrate PRELIM {v['guid']}"):
      raise ReintegrationError("unrecognized partial transaction")
  if merging:
    if git(folder, "ls-files", "-u").stdout.strip():
      if v["state"] != "conflict":
        _save(store, record, state="conflict")
      raise ReintegrationError("merge conflicts need explicit resolution")
    git(folder, "add", "-u")
    git(folder, "diff", "--cached", "--check")
    git(folder, "commit", "-m", f"Reintegrate PRELIM {v['guid']}")
  candidate = git(folder, "rev-parse", "HEAD").stdout.strip()
  if candidate in (v["new_base"], v["previous_candidate"]):
    raise ReintegrationError("reintegration produced no new candidate")
  for parent in (v["new_base"], v["previous_candidate"], v["source_sha"]):
    if git(root, "merge-base", "--is-ancestor", parent, candidate,
           check=False).returncode:
      raise ReintegrationError("integration-specific history was dropped")
  if _remote_ref(root, remote, "refs/heads/main") != v["new_base"]:
    raise ReintegrationError("main moved during finalization")
  ref = f"refs/heads/{v['branch']}"
  previous = _local_ref(root, ref)
  if previous is None:
    git(root, "update-ref", ref, candidate, "0" * 40)
  elif previous != candidate:
    raise ReintegrationError("new candidate ref was rewritten")
  record = _save(store, record, state="ready", candidate=candidate)
  _publish(root, remote, record)
  git(root, "worktree", "remove", str(folder))
  return _snapshot(record)


def reintegrate_prelim(root: Path, previous_guid: str, config: dict,
                       *, attempt_id: str | None = None, store=None):
  """Rebase integration history by merge into a new main-based candidate."""
  root = Path(root).resolve()
  store = store or durable_store(root)
  previous_guid = _guid(previous_guid)
  guid = _guid(attempt_id) if attempt_id else str(uuid.uuid4())
  if guid == previous_guid:
    raise ReintegrationError("new attempt must have another GUID")
  remote = config["repository"]["authoritativeRemote"]
  with _attempt_lock(root, store, guid):
    record = _read(store, guid)
    if record is None and attempt_id is not None:
      record = _restore(root, store, remote, guid)
    if record is None:
      old = _previous(root, store, remote, previous_guid)
      base = _remote_ref(root, remote, "refs/heads/main")
      if base is None or base == old["base_sha"]:
        raise ReintegrationError("main has not advanced")
      _fetch_new_base(root, remote, base, guid)
      if git(root, "merge-base", "--is-ancestor", old["base_sha"], base,
             check=False).returncode:
        raise ReintegrationError("new main is not a descendant of old base")
      value = {
        "guid": guid, "previous_guid": previous_guid,
        "issue": old["issue"], "source_ref": old["source_ref"],
        "source_sha": old["source_sha"],
        "lifecycle_revision": old["lifecycle_revision"],
        "previous_base": old["base_sha"],
        "previous_candidate": old["candidate_sha"],
        "new_base": base, "branch": f"prelim-main-{guid}",
        "state": "prepared", "candidate": None,
        "proposed_version": old["proposed_version"],
        "fresh_validation_required": True, "inherited_evidence": False,
      }
      _validate(value)
      record = store.create(_key(guid), value, runtime_writer_identity())
    elif record["value"]["previous_guid"] != previous_guid:
      raise ReintegrationError("retry changed previous attempt")
    return _complete(root, store, remote, record)


def finish_reintegration(root: Path, guid: str, config: dict, *, store=None):
  """Explicit conflict-resolved completion with exact base/source CAS."""
  root = Path(root).resolve()
  store = store or durable_store(root)
  guid = _guid(guid)
  with _attempt_lock(root, store, guid):
    record = store.read(_key(guid))
    _validate(record["value"])
    return _complete(root, store, config["repository"]["authoritativeRemote"],
                     record)
