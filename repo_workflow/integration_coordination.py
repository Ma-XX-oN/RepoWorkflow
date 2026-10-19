"""Provider-neutral serialized coordinator for immutable READY PRELIM refs.

This protocol requires provider-authoritative CAS; a local file lock is
insufficient to serialize distributed workers. Terminal history is separate
from published branches, which themselves are the pending queue.
"""
from dataclasses import dataclass
from typing import Protocol

from .prelim_queue import ReadyPrelim


class CoordinationError(RuntimeError):
  """Provider authority or candidate claim cannot be established."""


@dataclass(frozen=True)
class DestinationLease:
  destination: str
  generation: int
  active_guid: str | None
  holder: str | None


@dataclass(frozen=True)
class MitResumeAuthorization:
  """Provider-read approval to retry one immutable deferred submission."""
  guid: str
  destination: str
  prelim_sha: str
  expected_generation: int
  evidence_ref: str
  approved: bool


class CoordinationProvider(Protocol):
  def read_destination_lease(self, destination: str) -> DestinationLease:
    ...

  def compare_and_set_destination_lease(
      self, before: DestinationLease, after: DestinationLease,
  ) -> bool:
    ...

  def read_attempt_result(self, guid: str) -> str | None:
    """None means pending; otherwise independently persisted disposition."""
    ...

  def read_mit_resume_authorization(
      self, guid: str, destination: str,
  ) -> MitResumeAuthorization | None:
    """Provider-backed approved resumption event; never a bare PASS Boolean."""
    ...


def _claimable(provider, submission: ReadyPrelim) -> MitResumeAuthorization | None:
  result = provider.read_attempt_result(submission.guid)
  if result is None:
    return None
  if result != "deferred-mit":
    raise CoordinationError("attempt already has a persisted terminal result")
  read_approval = getattr(provider, "read_mit_resume_authorization", None)
  if not callable(read_approval):
    raise CoordinationError("deferred MIT requires provider resume authority")
  try:
    approval = read_approval(submission.guid, submission.destination)
  except Exception as error:
    raise CoordinationError("deferred MIT resume authority UNKNOWN") from error
  if (not isinstance(approval, MitResumeAuthorization)
      or approval.guid != submission.guid
      or approval.destination != submission.destination
      or approval.prelim_sha != submission.sha
      or type(approval.expected_generation) is not int
      or approval.expected_generation < 0
      or approval.approved is not True
      or not isinstance(approval.evidence_ref, str)
      or not approval.evidence_ref.strip()):
    raise CoordinationError("deferred MIT resume is not authoritatively approved")
  return approval


def claim_prelim(
    provider: CoordinationProvider, submission: ReadyPrelim,
    holder: str,
) -> DestinationLease:
  """Claim a READY branch using provider CAS; not authorization to merge."""
  if not isinstance(submission, ReadyPrelim):
    raise CoordinationError("a validated READY submission is required")
  if not isinstance(holder, str) or not holder.strip():
    raise CoordinationError("an authenticated coordinator identity is required")
  approval = _claimable(provider, submission)
  before = provider.read_destination_lease(submission.destination)
  if (not isinstance(before, DestinationLease)
      or before.destination != submission.destination
      or type(before.generation) is not int or before.generation < 0):
    raise CoordinationError("invalid authoritative destination lease")
  if before.active_guid is not None or before.holder is not None:
    raise CoordinationError("another coordinator owns this destination")
  if (approval is not None
      and approval.expected_generation != before.generation):
    raise CoordinationError("deferred MIT approval is stale for destination lease")
  after = DestinationLease(
    submission.destination, before.generation + 1,
    submission.guid, holder,
  )
  if provider.compare_and_set_destination_lease(before, after) is not True:
    raise CoordinationError("destination claim lost to another coordinator")
  try:
    if _claimable(provider, submission) != approval:
      raise CoordinationError("attempt status or approval changed; reconcile")
  except CoordinationError:
    # The CAS claim may now be held; recovery must be reconciled through
    # the authoritative lease, never silently assumed rolled back.
    raise
  return after


def release_prelim(
    provider: CoordinationProvider, claim: DestinationLease, holder: str,
    *, terminal_result: str,
) -> DestinationLease:
  """Release only after authoritative terminal/deferred evidence readback."""
  if terminal_result not in {"integrated", "rejected", "failed", "deferred-mit"}:
    raise CoordinationError("invalid attempt disposition")
  if (not isinstance(claim, DestinationLease)
      or not isinstance(holder, str) or not holder
      or claim.holder != holder or claim.active_guid is None):
    raise CoordinationError("release requires exact coordinator claim")
  before = provider.read_destination_lease(claim.destination)
  if before != claim:
    raise CoordinationError("destination claim changed before release")
  if provider.read_attempt_result(claim.active_guid) != terminal_result:
    raise CoordinationError("terminal/deferred result has no authoritative readback")
  after = DestinationLease(claim.destination, claim.generation + 1, None, None)
  if provider.compare_and_set_destination_lease(before, after) is not True:
    raise CoordinationError("destination release lost CAS")
  return after
