"""One guarded READY -> INT -> CAS -> immutable provider terminal.

Post-terminal #103 retirement, evidence promotion, queue scheduling and
lifecycle completion are distinct required stages, not completed here.
"""
from dataclasses import dataclass

from .done_executor import (
  CertifiedAttempt, DoneExecutionError, execute_certified_done,
)
from .done_host_coordinator import IntegrationHostCoordinator
from .done_int_workspace import publish_int_workspace
from .done_provider_acceptance import (
  DestinationAcceptanceFacts, bind_v2_destination_accept,
)
from .done_terminal_v2 import publish_integrated_terminal
from .integration_coordination import claim_prelim, release_prelim
from .prelim_queue import ReadyPrelim


@dataclass(frozen=True)
class AcceptedProviderAttempt:
  ready: ReadyPrelim
  accepted: object
  terminal: object
  released_generation: int


def accept_one_ready_submission(
    *, host, ready, holder, original_plan,
    refresh_plan, prepare_and_certify, admission_check,
    provider_facts, verify_provider_result,
    create_id, update_id, integration_id,
    terminal_evidence_ref, terminal_request_id,
    reconcile_unknown=None,
):
  """Bind actual provider operations; no implicit PASS or remote retry."""
  if not isinstance(ready, ReadyPrelim):
    raise DoneExecutionError("immutable published READY required")
  provider = IntegrationHostCoordinator(host)
  if ready not in provider.read_ready_prelims():
    raise DoneExecutionError("READY physical SHA differs from submission")
  lease = claim_prelim(provider, ready, holder)
  if (not isinstance(provider_facts, DestinationAcceptanceFacts)
      or provider_facts.repository != host.repository
      or provider_facts.ticket != int(ready.umbrella.removeprefix("issue-"))
      or provider_facts.destination != ready.destination
      or provider_facts.guid != ready.guid
      or provider_facts.lease_generation != lease.generation
      or provider_facts.holder != holder):
    raise DoneExecutionError("acceptance facts mismatch authoritative lease")

  prepared = []

  def prepare(plan):
    attempt = prepare_and_certify(plan)
    if (not isinstance(attempt, CertifiedAttempt)
        or attempt.source_prelim_ref != ready.ref
        or attempt.source_prelim_sha != ready.sha):
      raise DoneExecutionError("certified source differs from immutable READY")
    workspace = publish_int_workspace(
      host=host, ready=ready,
      expected_parent_sha=plan.expected_parent_sha,
      accepted_sha=attempt.tested_candidate_sha,
      create_id=create_id, update_id=update_id)
    if (attempt.int_attempt_ref != workspace.int_ref
        or attempt.expected_destination_sha != workspace.expected_destination_sha):
      raise DoneExecutionError("published INT differs from certified attempt")
    prepared.append(attempt)
    return attempt

  accepted = execute_certified_done(
    original_plan, refresh_plan, prepare, admission_check,
    bind_v2_destination_accept(host, provider_facts),
    verify_provider_result, reconcile_unknown=reconcile_unknown)
  if len(prepared) != 1:
    raise DoneExecutionError("certified INT attempt is not unique")
  terminal = publish_integrated_terminal(
    host=host, ready=ready,
    int_attempt_ref=prepared[0].int_attempt_ref,
    accepted_sha=prepared[0].tested_candidate_sha,
    old_destination_sha=original_plan.expected_parent_sha,
    landed_sha=accepted.landed_sha,
    operation_id=accepted.operation_id,
    integration_id=integration_id,
    terminal_evidence_ref=terminal_evidence_ref,
    record_request_id=terminal_request_id,
    accepted_integration=accepted)
  released = release_prelim(
    provider, lease, holder, terminal_result="integrated")
  return AcceptedProviderAttempt(
    ready, accepted, terminal, released.generation)
