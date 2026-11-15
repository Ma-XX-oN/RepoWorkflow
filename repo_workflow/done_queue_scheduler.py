"""Nonpersistent per-destination READY scheduling for #109.

A PRELIM ref is the queue item. Selection is supplied by an independently
authorized scheduling oracle, not lexical ref order, timestamps or GUIDs.
No control-plane branches/files are written. A destination lease is the
exclusive provider-backed writer boundary, acquired by the executor.
"""
from dataclasses import dataclass

from .done_host_coordinator import IntegrationHostCoordinator
from .integration_coordination import MitResumeAuthorization
from .prelim_queue import ReadyPrelim, classify_prelims


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
  stale: tuple[ReadyPrelim, ...] = ()
  superseded: tuple[ReadyPrelim, ...] = ()
  parent_sha: str | None = None


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
  try:
    parent = provider._read("destination.read", {"destination": destination})
    if (type(parent) is not dict or parent.get("ref") != "refs/heads/" + destination
        or parent.get("destination") != destination):
      raise QueueAdmissionError("destination parent identity differs")
    history, records = provider.read_submission_history(submissions)
    positions = classify_prelims(
      history, current_parent_sha=parent.get("sha"),
      bases={ref: value["parent_sha"] for ref, value in records.items()},
      predecessors={ref: value["predecessor_ref"] for ref, value in records.items()})
  except Exception as error:
    raise QueueAdmissionError("PRELIM inventory/provenance changed or UNKNOWN") from error
  by_ref = {item.submission.ref: item.position for item in positions}
  superseded = tuple(item for item in submissions if by_ref[item.ref] == "superseded")
  stale = tuple(item for item in submissions if by_ref[item.ref] == "stale")
  pending,deferred,terminal=[],[],[]
  for item in submissions:
    if by_ref[item.ref] == "superseded":
      continue
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
    lease.generation,lease.active_guid is not None or lease.holder is not None,
    stale, superseded, parent["sha"])


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
      or snapshot.current_generation != fresh.current_generation
      or snapshot.parent_sha != fresh.parent_sha):
    raise QueueAdmissionError("READY inventory or lease changed during selection")
  return chosen
