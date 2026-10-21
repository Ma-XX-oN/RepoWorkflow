"""Bounded destination coordinator tick for provider-backed READY branches.

There is no queue-control ref, timestamp priority or automatic retry of an
UNKNOWN integration. Each durable outcome is verified before advancing.
"""
from dataclasses import dataclass

from .done_completion import VerifiedCompletion
from .done_host_coordinator import IntegrationHostCoordinator
from .done_provider_pipeline import DeferredProviderAttempt
from .done_queue_scheduler import choose_submission


class QueueCycleError(RuntimeError):
  """An unverified outcome must not permit the next integration."""


@dataclass(frozen=True)
class VerifiedFailure:
  guid: str
  terminal_status: str
  handoff_ref: str
  independently_recorded: bool


@dataclass(frozen=True)
class QueueCycle:
  destination: str
  processed_guids: tuple[str,...]
  outcomes: tuple[str,...]
  stopped: str


def process_destination_cycle(*, host, destination, select_authorized,
                              execute_and_complete, max_items=1):
  """Advance only after exact terminal/deferred evidence and lease release.

  The executor owns reconstruction, ART/AIT/MIT, CAS, retirement,
  evidence promotion, lifecycle publication and failed-item handoff.
  Never treat an accepted-but-not-retired attempt as complete.
  """
  if (not callable(execute_and_complete)
      or type(max_items) is not int
      or not 1 <= max_items <= 100):
    raise QueueCycleError("bounded authenticated executor required")
  provider=IntegrationHostCoordinator(host)
  done,results=[],[]
  for _ in range(max_items):
    selected=choose_submission(
      host=host,destination=destination,select_authorized=select_authorized)
    if selected is None:
      return QueueCycle(destination,tuple(done),tuple(results),"no-ready")
    if selected.guid in done:
      raise QueueCycleError("attempt selected more than once in a tick")
    try:
      outcome=execute_and_complete(selected)
    except Exception as error:
      raise QueueCycleError("attempt result UNKNOWN; reconcile") from error
    if isinstance(outcome,VerifiedCompletion):
      if (outcome.terminal.guid != selected.guid
          or outcome.terminal.landed_sha != outcome.landed_sha):
        raise QueueCycleError("completion identity differs from READY")
      expected="integrated"
      label="completed"
    elif isinstance(outcome,DeferredProviderAttempt):
      if (outcome.ready != selected
          or not isinstance(outcome.evidence_ref,str)
          or not outcome.evidence_ref.strip()):
        raise QueueCycleError("MIT deferred identity differs from READY")
      event=provider.read_mit_deferred_event(
        selected.guid,destination)
      if (event is None or event.guid != selected.guid
          or event.prelim_sha != selected.sha
          or event.evidence_ref != outcome.evidence_ref):
        raise QueueCycleError("MIT deferral not durably recorded")
      expected=None
      label="deferred-mit"
    elif isinstance(outcome,VerifiedFailure):
      if (outcome.guid != selected.guid
          or outcome.terminal_status not in {"failed","rejected"}
          or type(outcome.handoff_ref) is not str
          or not outcome.handoff_ref.strip()
          or outcome.independently_recorded is not True):
        raise QueueCycleError("failed attempt has no durable handoff")
      expected=outcome.terminal_status
      label="failed-handoff"
    else:
      raise QueueCycleError("unverified attempted outcome cannot drain READY")
    terminal=provider.read_attempt_result(selected.guid)
    if terminal != expected:
      raise QueueCycleError("provider terminal result differs from outcome")
    lease=provider.read_destination_lease(destination)
    if lease.active_guid is not None or lease.holder is not None:
      raise QueueCycleError("destination claim not released after outcome")
    done.append(selected.guid)
    results.append(label)
  return QueueCycle(destination,tuple(done),tuple(results),"limit")
