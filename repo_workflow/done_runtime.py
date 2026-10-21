"""Trusted service composition for native rwf done exact READY execution.

This module is only the flow boundary. A real host runtime must supply the
authoritative planner, READY selector, verified provider executor, #103
retirement, canonical promotion, lifecycle and failed-item handoff.
"""
from dataclasses import dataclass

from .done_completion import VerifiedCompletion
from .done_shared_lifecycle import (
  SharedLifecycleEvidence,SharedAuthorityObservation,
)
from .done_planner import DonePlan
from .done_provider_pipeline import (
  AcceptedProviderAttempt,DeferredProviderAttempt,FailedProviderAttempt,
)
from .done_failure_handoff import PersistedFailureHandoff
from .prelim_queue import ReadyPrelim
from .done_source_identity import EffectiveSource


@dataclass(frozen=True)
class VerifiedDeferredDone:
  attempt: DeferredProviderAttempt
  provider_event: object


@dataclass(frozen=True)
class VerifiedFailedDone:
  attempt: FailedProviderAttempt
  persisted_handoff: PersistedFailureHandoff


class DoneRuntimeError(RuntimeError):
  """A native done request did not produce a verified final disposition."""


def execute_ready_done(*, release, read_current_plan, select_ready,
                       execute_provider_attempt, complete_accepted,
                       read_deferred_mit, publish_failure_handoff,
                       verify_source_lineage,verify_shared_lifecycle=None,
                       read_shared_authority=None):
  """Compose exact plan/READY/provider/outcome without fabricating PASS."""
  if (type(release) is not str
      or release not in {"patch","minor","major"}
      or any(not callable(fn) for fn in (
        read_current_plan,select_ready,execute_provider_attempt,
        complete_accepted,read_deferred_mit,publish_failure_handoff,
        verify_source_lineage,verify_shared_lifecycle,
        read_shared_authority))):
    raise DoneRuntimeError("authenticated native done bindings required")
  try:
    plan=read_current_plan(release)
  except Exception as error:
    raise DoneRuntimeError("authoritative current plan UNKNOWN") from error
  if (not isinstance(plan,DonePlan)
      or plan.release!=release or plan.allowed is not True
      or plan.disposition not in {"ALLOWED","QUEUE_ELIGIBLE"}
      or plan.missing_gates):
    raise DoneRuntimeError("current done plan is not executable")
  try:
    ready=select_ready(plan)
  except Exception as error:
    raise DoneRuntimeError("READY selection UNKNOWN") from error
  if (not isinstance(ready,ReadyPrelim)
      or ready.umbrella!="issue-"+plan.issue
      or ready.destination!=plan.target
      or ready.sha!=plan.candidate_sha):
    raise DoneRuntimeError("selected READY identity differs from plan")
  try:
    original_source_verified=verify_source_lineage(plan,ready)
  except Exception as error:
    raise DoneRuntimeError("invocation/source provenance UNKNOWN") from error
  if (not isinstance(original_source_verified,EffectiveSource)
      or original_source_verified.tested_source_sha != plan.candidate_sha):
    raise DoneRuntimeError("current original tested SHA was not verified")
  try:
    attempt=execute_provider_attempt(ready,plan)
  except Exception as error:
    # A remote mutation may have committed. Never replay blindly.
    raise DoneRuntimeError("provider attempt UNKNOWN; reconcile") from error
  if isinstance(attempt,AcceptedProviderAttempt):
    if attempt.ready!=ready:
      raise DoneRuntimeError("accepted attempt READY identity differs")
    try:
      completed=complete_accepted(attempt)
    except Exception as error:
      raise DoneRuntimeError("post-CAS completion UNKNOWN; reconcile") from error
    if (not isinstance(completed,VerifiedCompletion)
        or completed.operation_id!=attempt.accepted.operation_id
        or completed.landed_sha!=attempt.accepted.landed_sha
        or completed.terminal.guid!=ready.guid
        or completed.promotion.operation_id!=completed.operation_id):
      raise DoneRuntimeError("accepted but unverified DONE lifecycle")
    try:
      authority_before=read_shared_authority(plan,ready)
      shared=verify_shared_lifecycle(completed,plan,ready)
      authority_after=read_shared_authority(plan,ready)
    except Exception as error:
      raise DoneRuntimeError(
        "shared provider lifecycle readback UNKNOWN; no DONE") from error
    if (not isinstance(authority_before,SharedAuthorityObservation)
        or authority_before.independently_authenticated is not True
        or authority_before!=authority_after
        or authority_before.repository!=shared.repository
        or authority_before.branch!=shared.branch
        or authority_before.commit_sha!=shared.commit_sha):
      raise DoneRuntimeError(
        "canonical state authority moved or is unregistered; no DONE")
    if (not isinstance(shared,SharedLifecycleEvidence)
        or shared.independently_authenticated is not True
        or shared.issue!=int(plan.issue)
        or shared.operation_id!=completed.operation_id
        or shared.accepted_sha!=completed.terminal.accepted_sha
        or shared.landed_sha!=completed.landed_sha
        or shared.revision!=completed.lifecycle.get("revision")
        or type(shared.commit_sha) is not str
        or len(shared.commit_sha)!=40
        or type(shared.lifecycle_digest) is not str
        or len(shared.lifecycle_digest)!=64
        or type(shared.intent_digest) is not str
        or len(shared.intent_digest)!=64):
      raise DoneRuntimeError(
        "shared authoritative lifecycle missing or foreign; no DONE")
    return completed
  if isinstance(attempt,DeferredProviderAttempt):
    if attempt.ready!=ready:
      raise DoneRuntimeError("foreign MIT deferral")
    try:
      event=read_deferred_mit(ready)
    except Exception as error:
      raise DoneRuntimeError("MIT deferred provider read UNKNOWN") from error
    if (getattr(event,"guid",None)!=ready.guid
        or getattr(event,"prelim_sha",None)!=ready.sha
        or getattr(event,"evidence_ref",None)!=attempt.evidence_ref
        or type(getattr(event,"lease_generation",None)) is not int
        or event.lease_generation+1!=attempt.released_generation):
      raise DoneRuntimeError("MIT deferral missing exact provider evidence")
    return VerifiedDeferredDone(attempt,event)
  if isinstance(attempt,FailedProviderAttempt):
    if attempt.ready!=ready:
      raise DoneRuntimeError("foreign ART/AIT/MIT failed attempt")
    try:
      persisted=publish_failure_handoff(attempt)
    except Exception as error:
      raise DoneRuntimeError("failed-owner handoff UNKNOWN") from error
    if (not isinstance(persisted,PersistedFailureHandoff)
        or persisted.handoff.guid!=ready.guid
        or persisted.handoff.prelim_sha!=ready.sha
        or persisted.handoff.failure_kind!=attempt.failed_stage+"_FAIL"
        or len(persisted.per_issue_refs)==0):
      raise DoneRuntimeError("failed attempt lacks durable owner handoff")
    return VerifiedFailedDone(attempt,persisted)
  raise DoneRuntimeError("provider attempt disposition unverified")
