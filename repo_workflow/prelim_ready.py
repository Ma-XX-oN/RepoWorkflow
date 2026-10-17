"""Publish immutable destination-qualified READY PRELIM without queue markers."""
from dataclasses import dataclass
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GUID = re.compile(
  r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")


class ReadyPublicationError(RuntimeError):
  """PRELIM publication or authoritative readback is incomplete."""


@dataclass(frozen=True)
class PublishedReady:
  ref: str
  sha: str
  request_id: str


def publish_ready_prelim(
    *, ticket: int, destination: str, guid: str, candidate_sha: str,
    request_id: str, read_remote, create_if_absent,
) -> PublishedReady:
  """Publish a prepared exact source SHA; never update an existing PRELIM.

  create_if_absent must be provider-idempotent under request_id and prove
  initial creation. An existing ref must not be adopted by comparing SHA only.
  """
  if type(ticket) is not int or ticket <= 0:
    raise ReadyPublicationError("ticket must be a positive issue ID")
  if (type(destination) is not str or _DEST.fullmatch(destination) is None
      or any(part in ("", ".", "..") for part in destination.split("/"))):
    raise ReadyPublicationError("invalid destination branch")
  if type(guid) is not str or _GUID.fullmatch(guid) is None:
    raise ReadyPublicationError("invalid attempt GUID")
  if type(candidate_sha) is not str or _SHA.fullmatch(candidate_sha) is None:
    raise ReadyPublicationError("invalid exact candidate SHA")
  if type(request_id) is not str or not request_id.strip():
    raise ReadyPublicationError("idempotent publication key is required")
  ref = f"refs/heads/PRELIM-issue-{ticket}/{destination}-{guid}"
  existing = read_remote(ref)
  if existing is not None:
    raise ReadyPublicationError("published PRELIM ref already exists")
  try:
    confirmed = create_if_absent(ref, candidate_sha, request_id)
  except Exception as error:
    # Do not infer successful publication from an uncertain response.
    raise ReadyPublicationError("publication outcome UNKNOWN; reconcile") from error
  if confirmed is not True:
    raise ReadyPublicationError("provider did not certify initial ref creation")
  if read_remote(ref) != candidate_sha:
    raise ReadyPublicationError("published PRELIM identity readback differs")
  return PublishedReady(ref, candidate_sha, request_id)
