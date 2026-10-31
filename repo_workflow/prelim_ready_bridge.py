"""Conservative bridge from an existing verified #82 attempt to READY publication.

This does not mutate legacy source branches or declare old CI applicable
to a new destination. The caller's verifier must bind source, parent and
candidate to the current authoritative ticket contract.
"""
from collections.abc import Callable
from dataclasses import dataclass

from .prelim_attempt import PrelimAttempt
from .prelim_ready import (
  PublishedReady, ReadyPublicationError, publish_ready_prelim,
)


@dataclass(frozen=True)
class PreparedIdentity:
  ticket: int
  destination: str
  source_sha: str
  base_sha: str
  candidate_sha: str
  attempt_guid: str


def publish_verified_attempt(
    attempt: PrelimAttempt, *, ticket: int, destination: str,
    request_id: str,
    verify_authoritative: Callable[[PreparedIdentity], bool],
    read_remote, create_if_absent, read_publication_record=None,
) -> PublishedReady:
  """Bridge only a READY original candidate with independently verified facts.

  A published old-style branch is *not* itself queue admission. The new
  remote PRELIM ref becomes READY only after its exact SHA is verified.
  """
  if not isinstance(attempt, PrelimAttempt) or attempt.state != "ready":
    raise ReadyPublicationError("legacy candidate is not ready")
  if (type(attempt.candidate_sha) is not str
      or type(attempt.source_sha) is not str
      or type(attempt.base_sha) is not str
      or type(attempt.attempt) is not str
      or type(attempt.branch) is not str
      or attempt.branch != "prelim-main-" + attempt.attempt):
    raise ReadyPublicationError("legacy candidate identity is invalid")
  identity = PreparedIdentity(ticket, destination, attempt.source_sha,
    attempt.base_sha, attempt.candidate_sha, attempt.attempt)
  try:
    verified = verify_authoritative(identity)
  except Exception as error:
    raise ReadyPublicationError("candidate authority unavailable") from error
  if verified is not True:
    raise ReadyPublicationError("candidate/parent evidence not applicable")
  return publish_ready_prelim(
    ticket=ticket, destination=destination,
    guid=attempt.attempt, candidate_sha=attempt.candidate_sha,
    request_id=request_id, read_remote=read_remote,
    create_if_absent=create_if_absent,
    read_publication_record=read_publication_record,
  )
