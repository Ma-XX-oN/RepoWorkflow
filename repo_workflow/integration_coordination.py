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


def claim_prelim(
    provider: CoordinationProvider, submission: ReadyPrelim,
    holder: str,
) -> DestinationLease:
  """Claim a READY branch using provider CAS; not authorization to merge."""
  if not isinstance(submission, ReadyPrelim):
    raise CoordinationError("a validated READY submission is required")
  if not isinstance(holder, str) or not holder.strip():
    raise CoordinationError("an authenticated coordinator identity is required")
  if provider.read_attempt_result(submission.guid) is not None:
    raise CoordinationError("attempt already has a persisted terminal result")
  before = provider.read_destination_lease(submission.destination)
  if (not isinstance(before, DestinationLease)
      or before.destination != submission.destination
      or type(before.generation) is not int or before.generation < 0):
    raise CoordinationError("invalid authoritative destination lease")
  if before.active_guid is not None or before.holder is not None:
    raise CoordinationError("another coordinator owns this destination")
  after = DestinationLease(
    submission.destination, before.generation + 1,
    submission.guid, holder,
  )
  if provider.compare_and_set_destination_lease(before, after) is not True:
    raise CoordinationError("destination claim lost to another coordinator")
  if provider.read_attempt_result(submission.guid) is not None:
    raise CoordinationError("attempt became terminal during claim; reconcile")
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
