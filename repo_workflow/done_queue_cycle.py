"""Bounded destination coordinator tick for provider-backed READY branches.

There is no queue-control ref, timestamp priority or automatic retry of an
UNKNOWN integration. Each durable outcome is verified before advancing.
"""
from dataclasses import dataclass

from .done_completion import VerifiedCompletion
from .done_terminal_v2 import IntegratedTerminal
from .done_evidence_promotion import Promotion
from .done_failure_handoff import PersistedFailureHandoff
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


def failure_outcome_from_handoff(ready, terminal_status, persisted):
  """Connect a verified issue/PR handoff to one terminal queue outcome."""
  if (not isinstance(persisted,PersistedFailureHandoff)
      or not hasattr(ready,"guid")
      or persisted.handoff.guid != ready.guid
      or persisted.handoff.prelim_sha != ready.sha
      or persisted.handoff.destination != ready.destination
      or terminal_status not in {"failed","rejected"}
      or len(persisted.per_issue_refs)
         != len(persisted.handoff.owner_issue_ids)
      or {issue for issue,_ in persisted.per_issue_refs}
         != set(persisted.handoff.owner_issue_ids)
      or any(type(ref) is not str or not ref.strip()
             for _,ref in persisted.per_issue_refs)):
    raise QueueCycleError("durable failed-item handoff differs from READY")
  return VerifiedFailure(
    ready.guid,terminal_status,
    persisted.handoff.operation_id,True)


@dataclass(frozen=True)
class QueueCycle:
  destination: str
  processed_guids: tuple[str,...]
  outcomes: tuple[str,...]
  stopped: str


def process_destination_cycle(*, host, destination, select_authorized,
                              execute_and_complete, verify_handoff,
                              max_items=1):
  """Advance only after exact terminal/deferred evidence and lease release.

  The executor owns reconstruction, ART/AIT/MIT, CAS, retirement,
  evidence promotion, lifecycle publication and failed-item handoff.
  Never treat an accepted-but-not-retired attempt as complete.
  """
  if (not callable(execute_and_complete)
      or not callable(verify_handoff)
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
      if (not isinstance(outcome.terminal,IntegratedTerminal)
          or not isinstance(outcome.promotion,Promotion)
          or outcome.terminal.guid != selected.guid
          or outcome.terminal.landed_sha != outcome.landed_sha
          or outcome.promotion.operation_id != outcome.operation_id
          or outcome.promotion.landed_sha != outcome.landed_sha
          or outcome.promotion.accepted_candidate_sha
             != outcome.terminal.accepted_sha
          or len(outcome.retired) != 2
          or any(getattr(r,"absent_after",None) is not True
                 for r in outcome.retired)
          or type(outcome.lifecycle) is not dict
          or outcome.lifecycle.get("result") != "done"
          or outcome.lifecycle.get("guid") != selected.guid
          or outcome.lifecycle.get("landed_sha") != outcome.landed_sha):
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
          or event.evidence_ref != outcome.evidence_ref
          or event.lease_generation + 1 != outcome.released_generation):
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
      try:
        verified=verify_handoff(outcome,selected)
      except Exception as error:
        raise QueueCycleError("durable handoff readback UNKNOWN") from error
      if verified is not True:
        raise QueueCycleError("failed-item handoff not independently verified")
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
