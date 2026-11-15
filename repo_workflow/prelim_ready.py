"""Publish immutable version-qualified READY PRELIM without queue markers."""
from dataclasses import dataclass
import re
from .prelim_queue import prelim_ref_for_version, parse_ready_prelim

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DEST = re.compile(r"[A-Za-z0-9._/-]+\Z")


class ReadyPublicationError(RuntimeError):
  """PRELIM publication or authoritative readback is incomplete."""


@dataclass(frozen=True)
class PublishedReady:
  ref: str
  sha: str
  request_id: str


def publish_ready_prelim(
    *, ticket: int, destination: str, version: str, candidate_sha: str,
    request_id: str, read_remote, create_if_absent,
    read_publication_record=None,
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
  if type(candidate_sha) is not str or _SHA.fullmatch(candidate_sha) is None:
    raise ReadyPublicationError("invalid exact candidate SHA")
  if type(request_id) is not str or not request_id.strip():
    raise ReadyPublicationError("idempotent publication key is required")
  try:
    ref = prelim_ref_for_version(version)
    if parse_ready_prelim(ref, candidate_sha).umbrella != "issue-" + str(ticket):
      raise ReadyPublicationError("version belongs to another issue")
  except ValueError as error:
    raise ReadyPublicationError("invalid PRELIM development version") from error
  def exact_replay():
    if read_publication_record is None:
      return False
    record = read_publication_record(request_id)
    return (type(record) is dict
            and record == {
              "ref": ref, "sha": candidate_sha,
              "request_id": request_id, "status": "published",
            })

  existing = read_remote(ref)
  if existing is not None:
    if existing == candidate_sha and exact_replay():
      return PublishedReady(ref, candidate_sha, request_id)
    raise ReadyPublicationError("published PRELIM ref already exists")
  try:
    confirmed = create_if_absent(ref, candidate_sha, request_id)
  except Exception as error:
    # A lost reply is recoverable only with independent exact request-ID
    # evidence, not by matching a branch SHA alone.
    if read_remote(ref) == candidate_sha and exact_replay():
      return PublishedReady(ref, candidate_sha, request_id)
    raise ReadyPublicationError("publication outcome UNKNOWN; reconcile") from error
  if confirmed is not True:
    raise ReadyPublicationError("provider did not certify initial ref creation")
  if read_remote(ref) != candidate_sha:
    raise ReadyPublicationError("published PRELIM identity readback differs")
  return PublishedReady(ref, candidate_sha, request_id)



def create_ready_ref_provider(backend, ref, sha, request_id):
  """Create an absent PRELIM ref with the provider's atomic POST /git/refs.

  A Git push with an empty expected ref is unsafe: a same-SHA no-op can
  succeed even if the ref already exists. Never use push as creation proof.
  """
  try:
    valid = parse_ready_prelim(ref, sha) is not None
  except (ValueError, TypeError):
    valid = False
  if (not valid or type(sha) is not str or _SHA.fullmatch(sha) is None
      or type(request_id) is not str or not request_id.strip()):
    raise ReadyPublicationError("invalid PRELIM create request")

  def read():
    try:
      record = backend.get("git/ref/" + ref.removeprefix("refs/"))
    except Exception as error:
      if getattr(error, "code", None) == "not_found":
        return None
      raise ReadyPublicationError("remote PRELIM read UNKNOWN") from error
    if (type(record) is not dict or record.get("ref") != ref
        or type(record.get("object")) is not dict):
      raise ReadyPublicationError("remote PRELIM ref malformed")
    head = record["object"].get("sha")
    if type(head) is not str or _SHA.fullmatch(head) is None:
      raise ReadyPublicationError("remote PRELIM SHA malformed")
    return head

  if read() is not None:
    raise ReadyPublicationError("PRELIM already published")
  try:
    backend.post("git/refs", {"ref": ref, "sha": sha})
  except Exception as error:
    # Even if ref now matches, the mutation outcome is not proven to be
    # ours. Only the external request-ID reservation can reconcile a retry.
    raise ReadyPublicationError("PRELIM creation outcome UNKNOWN") from error
  if read() != sha:
    raise ReadyPublicationError("published PRELIM readback differs")
  return True
