"""Publish a recorded #82 candidate only after remote state/source readback."""
from pathlib import Path
import uuid

from .prelim_attempt import (
  PrelimError, _key, _record, _remote_ref, _restore_remote_record,
  _snapshot, _trusted_inputs,
)
from .prelim_ready import (
  ReadyPublicationError, create_ready_ref_provider,
)
from .prelim_ready_bridge import publish_verified_attempt
from .state_store import durable_store


def publish_recorded_ready(root: Path, config: dict, *, ticket: int,
    destination: str, guid: str, request_id: str, backend,
    verify_parent_and_evidence,
    read_publication_record=None):
  """Bridge the exact recorded READY commit without modifying old refs.

  This is compatibility migration, not the final replacement for #82's
  legacy publisher. Source validation remains #82; the callback verifies
  current parent, destination and test-evidence applicability.
  """
  try:
    guid = str(uuid.UUID(guid))
  except (ValueError, TypeError, AttributeError) as error:
    raise ReadyPublicationError("invalid attempt GUID") from error
  root = Path(root).resolve()
  remote = config["repository"]["authoritativeRemote"]
  store = durable_store(root)
  try:
    record = _record(store, guid)
    if record is None:
      record = _restore_remote_record(root, remote, store, guid)
    if record is None:
      raise ReadyPublicationError("recorded PRELIM attempt is missing")
    value = record["value"]
    if (value["issue"] != str(ticket)
        or value["branch"] != "prelim-main-" + guid
        or value["state"] != "ready"):
      raise ReadyPublicationError("recorded PRELIM owner or state differs")
    candidate = _snapshot(record)
    if _remote_ref(root, remote, "refs/heads/" + candidate.branch) != (
        candidate.candidate_sha):
      raise ReadyPublicationError("legacy remote candidate SHA moved")
    _trusted_inputs(
      root, remote, str(ticket), value["source_ref"],
      value["source_sha"], value["base_sha"],
      value["lifecycle_revision"], require_current_base=False,
    )
  except (PrelimError, KeyError, TypeError, ValueError) as error:
    raise ReadyPublicationError("recorded candidate authority unavailable") from error

  def read(ref):
    try:
      item = backend.get("git/ref/" + ref.removeprefix("refs/"))
    except Exception as error:
      if getattr(error, "code", None) == "not_found":
        return None
      raise ReadyPublicationError("remote READY read unavailable") from error
    if (type(item) is not dict or item.get("ref") != ref
        or type(item.get("object")) is not dict):
      raise ReadyPublicationError("remote READY identity invalid")
    return item["object"].get("sha")

  return publish_verified_attempt(
    candidate, ticket=ticket, destination=destination,
    request_id=request_id,
    verify_authoritative=verify_parent_and_evidence,
    read_remote=read,
    create_if_absent=lambda ref, sha, key:
      create_ready_ref_provider(backend, ref, sha, key),
    read_publication_record=read_publication_record,
  )


def publish_recorded_ready_certified(
    root: Path, config: dict, *, ticket: int, destination: str,
    guid: str, request_id: str, backend, resolve_parent,
    read_publication_record=None,
):
  """Public recorded READY publisher using the real #102 PASS authority.

  An untrusted caller cannot substitute a Boolean success. Both terminal
  tags, exact remote candidate/base identity and immediate parent are
  verified before provider-atomic PRELIM ref creation.
  """
  from .prelim_ready_authority import verify_ready_authority

  def verify(identity):
    return verify_ready_authority(
      Path(root).resolve(),
      config["repository"]["authoritativeRemote"], identity,
      resolve_parent=resolve_parent,
    )

  return publish_recorded_ready(
    root, config, ticket=ticket, destination=destination, guid=guid,
    request_id=request_id, backend=backend,
    verify_parent_and_evidence=verify,
    read_publication_record=read_publication_record,
  )
