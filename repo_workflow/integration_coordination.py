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
class MitDeferredEvent:
  """Durable, resumable MIT handoff, separate from terminal results."""
  guid: str
  destination: str
  prelim_sha: str
  lease_generation: int
  evidence_ref: str
  reason: str


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

  def read_mit_deferred_event(
      self, guid: str, destination: str,
  ) -> MitDeferredEvent | None:
    """Read most recent separately persisted deferred-MIT event."""
    ...

  def read_mit_resume_authorization(
      self, guid: str, destination: str,
  ) -> MitResumeAuthorization | None:
    """Provider-backed approved resumption event; never a bare PASS Boolean."""
    ...


def _read_defer(provider, submission: ReadyPrelim) -> MitDeferredEvent | None:
  read_event = getattr(provider, "read_mit_deferred_event", None)
  if not callable(read_event):
    raise CoordinationError("provider lacks deferred MIT event readback")
  try:
    event = read_event(submission.guid, submission.destination)
  except Exception as error:
    raise CoordinationError("deferred MIT event read UNKNOWN") from error
  if event is None:
    return None
  if (not isinstance(event, MitDeferredEvent)
      or event.guid != submission.guid
      or event.destination != submission.destination
      or event.prelim_sha != submission.sha
      or type(event.lease_generation) is not int
      or event.lease_generation < 1
      or not isinstance(event.evidence_ref, str)
      or not event.evidence_ref.strip()
      or event.reason not in {"timeout", "awaiting-manual"}):
    raise CoordinationError("invalid durable deferred MIT event")
  return event


def _claimable(provider, submission: ReadyPrelim):
  terminal = provider.read_attempt_result(submission.guid)
  if terminal is not None:
    raise CoordinationError("attempt already has a persisted terminal result")
  deferred = _read_defer(provider, submission)
  if deferred is None:
    return None, None
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
      or approval.expected_generation <= deferred.lease_generation
      or approval.approved is not True
      or not isinstance(approval.evidence_ref, str)
      or not approval.evidence_ref.strip()):
    raise CoordinationError("deferred MIT resume is not authoritatively approved")
  return deferred, approval

def claim_prelim(
    provider: CoordinationProvider, submission: ReadyPrelim,
    holder: str,
) -> DestinationLease:
  """Claim a READY branch using provider CAS; not authorization to merge."""
  if not isinstance(submission, ReadyPrelim):
    raise CoordinationError("a validated READY submission is required")
  if not isinstance(holder, str) or not holder.strip():
    raise CoordinationError("an authenticated coordinator identity is required")
  deferred, approval = _claimable(provider, submission)
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
    if _claimable(provider, submission) != (deferred, approval):
      raise CoordinationError("attempt status or approval changed; reconcile")
  except CoordinationError:
    # The CAS claim may now be held; recovery must be reconciled through
    # the authoritative lease, never silently assumed rolled back.
    raise
  return after


def release_prelim(
    provider: CoordinationProvider, claim: DestinationLease, holder: str,
    *, terminal_result: str, submission: ReadyPrelim | None = None,
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
  if terminal_result == "deferred-mit":
    if (not isinstance(submission, ReadyPrelim)
        or submission.guid != claim.active_guid
        or submission.destination != claim.destination):
      raise CoordinationError("deferred MIT exact PRELIM identity required")
    if provider.read_attempt_result(claim.active_guid) is not None:
      raise CoordinationError("terminal result forbids deferred release")
    read_event = getattr(provider, "read_mit_deferred_event", None)
    if not callable(read_event):
      raise CoordinationError("provider lacks deferred MIT event readback")
    event = read_event(claim.active_guid, claim.destination)
    if (not isinstance(event, MitDeferredEvent)
        or event.guid != claim.active_guid
        or event.destination != claim.destination
        or event.lease_generation != claim.generation
        or event.prelim_sha != submission.sha
        or not isinstance(event.prelim_sha, str)
        or not isinstance(event.evidence_ref, str)
        or not event.evidence_ref.strip()
        or event.reason not in {"timeout", "awaiting-manual"}):
      raise CoordinationError("deferred MIT event has no exact readback")
  elif provider.read_attempt_result(claim.active_guid) != terminal_result:
    raise CoordinationError("terminal result has no authoritative readback")
  after = DestinationLease(claim.destination, claim.generation + 1, None, None)
  if provider.compare_and_set_destination_lease(before, after) is not True:
    raise CoordinationError("destination release lost CAS")
  return after
