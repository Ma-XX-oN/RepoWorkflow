"""First public READY event for independently validated destination candidates."""
from pathlib import Path
import re
import uuid

from .prelim_attempt import _remote_ref
from .prelim_publication import _restore
from .prelim_ready import (
  ReadyPublicationError, create_ready_ref_provider, publish_ready_prelim,
)
from .prelim_ready_provider_scope import verify_ready_provider_scope
from .prelim_ready_v2_validation import v2_identity_key, v2_identity_ref
from .prelim_ready_v2_tags import expected_v2_terminal_tags
from .state_store import durable_store
from .terminal_tag import _remote_target


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TAG = re.compile(r"v[A-Za-z0-9._+-]+\Z")
_FIELDS = {
  "kind", "attempt", "issue", "destination", "source_sha", "base_sha",
  "candidate_sha", "proposed_version", "test_version", "regression_tag",
  "integration_tag", "outcome",
}


def _verified_v2_identity(root, remote, guid, ticket, destination):
  ref = v2_identity_ref(guid)
  if _remote_ref(root, remote, ref) is None:
    raise ReadyPublicationError("independent v2 PASS identity absent")
  _restore(root, remote, ref, v2_identity_key(guid))
  record = durable_store(root).read(v2_identity_key(guid))
  if type(record) is not dict or type(record.get("value")) is not dict:
    raise ReadyPublicationError("provider v2 PASS identity malformed")
  value = record["value"]
  if (set(value) != _FIELDS or value["kind"] != "destination-qualified-v2"
      or value["outcome"] != "PASS"
      or value["attempt"] != guid or value["issue"] != str(ticket)
      or value["destination"] != destination):
    raise ReadyPublicationError("provider candidate destination identity differs")
  for name in ("source_sha", "base_sha", "candidate_sha"):
    sha = value[name]
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
      raise ReadyPublicationError("provider source/candidate SHA malformed")
  try:
    required_tags = expected_v2_terminal_tags(
      value["test_version"], str(ticket))
  except ValueError as error:
    raise ReadyPublicationError("provider PASS terminal version invalid") from error
  for phase in ("regression", "integration"):
    tag = value[phase + "_tag"]
    if (type(tag) is not str or _TAG.fullmatch(tag) is None
        or tag != required_tags[phase]
        or _remote_target(root, remote, tag) != value["candidate_sha"]):
      raise ReadyPublicationError("independent terminal tag identity changed")
  return value


def publish_destination_prelim(
    root: Path, config: dict, *, ticket: int, destination: str,
    guid: str, request_id: str, backend, resolve_parent,
    read_publication_record=None,
):
  """Publish exactly once; parent movement after PASS is not merge admission."""
  try:
    guid = str(uuid.UUID(guid))
  except (ValueError, TypeError, AttributeError) as error:
    raise ReadyPublicationError("invalid v2 preparation GUID") from error
  if (type(ticket) is not int or ticket < 1
      or not callable(resolve_parent)
      or resolve_parent(ticket) != destination):
    raise ReadyPublicationError("qualified candidate immediate parent differs")
  root = Path(root).resolve()
  remote = config["repository"]["authoritativeRemote"]
  verify_ready_provider_scope(root, remote, backend)
  value = _verified_v2_identity(root, remote, guid, ticket, destination)
  # The #572 terminal-tag publisher must have made the exact physical
  # candidate object available to the authenticated provider first.
  try:
    candidate_commit = backend.get("git/commits/" + value["candidate_sha"])
  except Exception as error:
    raise ReadyPublicationError("provider candidate object unavailable") from error
  if (type(candidate_commit) is not dict or
      candidate_commit.get("sha") != value["candidate_sha"]):
    raise ReadyPublicationError("provider candidate object identity differs")
  destination_ref = "refs/heads/" + destination
  if _remote_ref(root, remote, destination_ref) is None:
    raise ReadyPublicationError("authoritative destination no longer exists")

  def read(ref):
    try:
      response = backend.get("git/ref/" + ref.removeprefix("refs/"))
    except Exception as error:
      if getattr(error, "code", None) == "not_found":
        return None
      raise ReadyPublicationError("READY ref provider read UNKNOWN") from error
    if (type(response) is not dict or response.get("ref") != ref
        or type(response.get("object")) is not dict):
      raise ReadyPublicationError("provider READY ref identity malformed")
    sha = response["object"].get("sha")
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
      raise ReadyPublicationError("provider READY SHA malformed")
    return sha

  # Re-read immutable PASS after the provider write to catch any unexpected
  # state movement.  A write is never accepted as evidence of merge readiness.
  ready = publish_ready_prelim(
    ticket=ticket, destination=destination, guid=guid,
    candidate_sha=value["candidate_sha"], request_id=request_id,
    read_remote=read,
    create_if_absent=lambda ref, sha, identity:
      create_ready_ref_provider(backend, ref, sha, identity),
    read_publication_record=read_publication_record,
  )
  if _verified_v2_identity(root, remote, guid, ticket, destination) != value:
    raise ReadyPublicationError("v2 PASS identity changed during publication")
  return ready
