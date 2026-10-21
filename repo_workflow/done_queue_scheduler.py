"""Nonpersistent per-destination READY scheduling for #109.

A PRELIM ref is the queue item. Selection is supplied by an independently
authorized scheduling oracle, not lexical ref order, timestamps or GUIDs.
No control-plane branches/files are written. A destination lease is the
exclusive provider-backed writer boundary, acquired by the executor.
"""
from dataclasses import dataclass

from .done_host_coordinator import IntegrationHostCoordinator
from .integration_coordination import MitResumeAuthorization
from .prelim_queue import ReadyPrelim


class QueueAdmissionError(RuntimeError):
  """No authenticated destination schedule can be acted on."""


@dataclass(frozen=True)
class DestinationSnapshot:
  destination: str
  pending: tuple[ReadyPrelim, ...]
  deferred: tuple[ReadyPrelim, ...]
  terminal: tuple[ReadyPrelim, ...]
  current_generation: int
  busy: bool


def inventory_destination(host, destination):
  """Classify physical submissions using durable provider history."""
  if type(destination) is not str or not destination:
    raise QueueAdmissionError("destination identity required")
  provider=IntegrationHostCoordinator(host)
  submissions=tuple(
    entry for entry in provider.read_ready_prelims()
    if entry.destination==destination)
  lease=provider.read_destination_lease(destination)
  if lease.destination != destination:
    raise QueueAdmissionError("provider lease destination mismatch")
  pending,deferred,terminal=[],[],[]
  for item in submissions:
    try:
      result=provider.read_attempt_result(item.guid)
      event=provider.read_mit_deferred_event(item.guid,destination)
    except Exception as error:
      raise QueueAdmissionError("attempt status readback UNKNOWN") from error
    if result is not None:
      terminal.append(item)
    elif event is not None:
      try:
        approval=provider.read_mit_resume_authorization(
          item.guid,destination)
      except Exception as error:
        raise QueueAdmissionError("MIT approval readback UNKNOWN") from error
      resumable=(
        isinstance(approval,MitResumeAuthorization)
        and approval.approved is True
        and approval.guid == item.guid
        and approval.destination == destination
        and approval.prelim_sha == item.sha
        and approval.deferred_evidence_ref == event.evidence_ref
        and approval.expected_generation == lease.generation
        and approval.expected_generation > event.lease_generation)
      if resumable:
        pending.append(item)
      else:
        deferred.append(item)
    else:
      pending.append(item)
  return DestinationSnapshot(
    destination,tuple(pending),tuple(deferred),tuple(terminal),
    lease.generation,lease.active_guid is not None or lease.holder is not None)


def choose_submission(*, host, destination, select_authorized):
  """Choose eligible pending READY only, without claiming or mutating it.

  The coordinator's independent selector must return the exact current
  immutable ReadyPrelim object. It may use dependency/policy priority,
  but untrusted timestamps and GUIDs confer no priority.
  """
  if not callable(select_authorized):
    raise QueueAdmissionError("independent scheduler is required")
  snapshot=inventory_destination(host,destination)
  if snapshot.busy:
    return None
  if not snapshot.pending:
    return None
  try:
    chosen=select_authorized(snapshot)
  except Exception as error:
    raise QueueAdmissionError("scheduler decision UNKNOWN") from error
  if chosen is None:
    return None
  if not isinstance(chosen,ReadyPrelim) or chosen not in snapshot.pending:
    raise QueueAdmissionError("scheduler chose ineligible or foreign READY")
  # A ref disappearing/advancing between inventory and claim must be
  # treated as stale, never silently substituted with another attempt.
  fresh=inventory_destination(host,destination)
  if (fresh.busy or chosen not in fresh.pending
      or snapshot.current_generation != fresh.current_generation):
    raise QueueAdmissionError("READY inventory or lease changed during selection")
  return chosen
