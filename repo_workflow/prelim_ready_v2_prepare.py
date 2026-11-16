"""Build local PRELIM candidate at the actual destination; READY comes later."""
from pathlib import Path
import re
import uuid

from .git import git
from .lifecycle_store import LifecycleStore
from .prelim_attempt import (
  _local_ref, _merge_workspace, _remote_ref, _trusted_inputs,
)
from .prelim_attempt_lock import PrelimError, _attempt_lock
from .prelim_ready_v2_finish import complete_prepared_candidate
from .prelim_ready_v2_record import (
  preparation_key, preparation_ref, prepared_snapshot, validate_preparation,
)
from .runtime_identity import runtime_writer_identity
from .state_store import StateStoreError, durable_store


_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")
_ISSUE = re.compile(r"[1-9][0-9]*\Z")


def _accepted(root, issue, source_ref):
  if (type(source_ref) is not str or re.fullmatch(
      rf"refs/heads/issue-{issue}(?:-[A-Za-z0-9._/-]+)?",
      source_ref) is None):
    raise PrelimError("source branch does not match accepted issue")
  source = _local_ref(root, source_ref)
  if source is None:
    raise PrelimError("accepted issue branch missing")
  lifecycle = LifecycleStore(root).read(issue)
  if (lifecycle.lifecycle.state != "accepted"
      or not lifecycle.lifecycle.history
      or lifecycle.lifecycle.history[-1].candidate != source
      or type(lifecycle.revision) is not int):
    raise PrelimError("accepted lifecycle source is unavailable")
  return source, lifecycle.revision


def _destination_sha(root, remote, destination):
  ref = "refs/heads/" + destination
  sha = _remote_ref(root, remote, ref)
  if sha is None:
    raise PrelimError("authoritative destination missing")
  if git(root, "cat-file", "-e", sha + "^{commit}", check=False).returncode:
    git(root, "fetch", "--no-tags", remote, ref)
  if git(root, "cat-file", "-e", sha + "^{commit}", check=False).returncode:
    raise PrelimError("authoritative destination object missing")
  if _remote_ref(root, remote, ref) != sha:
    raise PrelimError("destination moved during historical base acquisition")
  return sha


def prepare_destination_prelim(
    root: Path, issue: str, source_ref: str, destination: str, config: dict,
    *, resolve_parent, guid: str | None = None, bump: str = "patch",
    store=None,
):
  """Prepare exact local candidate without touching remote PRELIM branches."""
  if (type(issue) is not str or _ISSUE.fullmatch(issue) is None
      or type(destination) is not str or _DEST.fullmatch(destination) is None
      or any(p in ("", ".", "..") for p in destination.split("/"))
      or bump not in ("patch", "minor") or not callable(resolve_parent)):
    raise PrelimError("invalid destination-qualified candidate request")
  try:
    guid = str(uuid.UUID(guid)) if guid is not None else str(uuid.uuid4())
  except (ValueError, TypeError, AttributeError) as error:
    raise PrelimError("invalid candidate GUID") from error
  if resolve_parent(int(issue)) != destination:
    raise PrelimError("destination is not the issue's immediate parent")
  root = Path(root).resolve()
  remote = config["repository"]["authoritativeRemote"]
  store = store or durable_store(root)
  writer = runtime_writer_identity()
  with _attempt_lock(root, store, "v2-" + guid):
    try:
      record = store.read(preparation_key(guid))
    except StateStoreError as error:
      if "record is missing:" not in str(error):
        raise
      record = None
    if record is None:
      source, revision = _accepted(root, issue, source_ref)
      base = _destination_sha(root, remote, destination)
      value = {
        "guid": guid, "issue": issue, "destination": destination,
        "source_ref": source_ref, "source_sha": source, "base_sha": base,
        "lifecycle_revision": revision, "bump": bump, "state": "prepared",
        "candidate_sha": None, "proposed_version": None,
      }
      validate_preparation(value)
      record = store.create(preparation_key(guid), value, writer)
    value = record["value"]
    validate_preparation(value)
    if (value["guid"] != guid or value["issue"] != issue
        or value["source_ref"] != source_ref
        or value["destination"] != destination or value["bump"] != bump):
      raise PrelimError("GUID reused with changed candidate parameters")
    _trusted_inputs(root, remote, issue, source_ref, value["source_sha"],
                    value["base_sha"], value["lifecycle_revision"],
                    require_current_base=False)
    if value["state"] == "constructed":
      if _local_ref(root, preparation_ref(guid)) != value["candidate_sha"]:
        raise PrelimError("prepared local ref no longer identifies candidate")
      return prepared_snapshot(value)
    if value["state"] == "conflict":
      raise PrelimError("source conflicts require explicit resolution")
    _, proposed, clean = _merge_workspace(
      root, value["base_sha"], value["source_sha"], "v2-" + guid,
      config, bump, value["proposed_version"],
    )
    if value["proposed_version"] is None:
      new_value = {**value, "state": "versioned",
                   "proposed_version": proposed}
      validate_preparation(new_value)
      record = store.replace(record["key"], record["revision"],
                             new_value, writer)
    if not clean:
      value = {**record["value"], "state": "conflict"}
      store.replace(record["key"], record["revision"], value, writer)
      raise PrelimError("prepared source merge conflict requires resolution")
    return complete_prepared_candidate(root, store, record, config, writer)
