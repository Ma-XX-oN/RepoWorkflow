"""Guarded functional execution boundary for an already certified INT-ATTEMPT.

Provider integrations must implement atomic expected-old destination SHA
checking. This is not the complete #109 scheduler, publisher or CLI.
"""
from dataclasses import dataclass
import re

from .done_planner import DonePlan


class DoneExecutionError(RuntimeError):
  """Readiness, provenance or provider acceptance cannot be established."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class CertifiedAttempt:
  source_prelim_sha: str
  int_attempt_ref: str
  tested_candidate_sha: str
  expected_destination_sha: str
  evidence_ref: str
  authorization_ref: str


@dataclass(frozen=True)
class AcceptedIntegration:
  landed_sha: str
  verified: bool
  operation_id: str


def execute_certified_done(
    original: DonePlan,
    refresh_plan,
    prepare_and_certify,
    admission_check,
    integrate_conditional,
    verify_provider_result,
) -> AcceptedIntegration:
  """Execute only through a provider with an atomic destination condition.

  All callbacks are authenticated service boundaries, never untrusted
  developer-supplied PASS booleans. The provider owns idempotent reconciliation.
  """
  if not isinstance(original, DonePlan) or not original.allowed:
    raise DoneExecutionError("original completion plan is not allowed")
  fresh = refresh_plan()
  if not isinstance(fresh, DonePlan) or not fresh.allowed:
    raise DoneExecutionError("fresh completion plan is not allowed")
  compared = ("issue", "release", "target", "candidate_sha",
              "expected_parent_sha")
  if any(getattr(original, key) != getattr(fresh, key) for key in compared):
    raise DoneExecutionError("completion plan changed before mutation")
  if fresh.missing_gates:
    raise DoneExecutionError("fresh completion has missing gates")
  if fresh.disposition not in ("ALLOWED", "QUEUE_ELIGIBLE"):
    raise DoneExecutionError("completion plan is not executable")
  if admission_check(fresh) is not True:
    raise DoneExecutionError("destination admission policy denied integration")
  attempt = prepare_and_certify(fresh)
  if not isinstance(attempt, CertifiedAttempt):
    raise DoneExecutionError("INT-ATTEMPT certified result is absent")
  if (attempt.source_prelim_sha != fresh.candidate_sha
      or attempt.expected_destination_sha != fresh.expected_parent_sha
      or not isinstance(attempt.int_attempt_ref, str)
      or not attempt.int_attempt_ref.startswith("refs/heads/INT-ATTEMPT-")
      or not isinstance(attempt.evidence_ref, str) or not attempt.evidence_ref
      or not isinstance(attempt.authorization_ref, str)
      or not attempt.authorization_ref):
    raise DoneExecutionError("certification provenance differs")
  if (_SHA.fullmatch(attempt.tested_candidate_sha) is None
      or _SHA.fullmatch(fresh.expected_parent_sha) is None):
    raise DoneExecutionError("candidate identity is invalid")
  result = integrate_conditional(
    attempt.int_attempt_ref, attempt.tested_candidate_sha,
    fresh.target, fresh.expected_parent_sha,
    attempt.evidence_ref, attempt.authorization_ref,
  )
  if not isinstance(result, AcceptedIntegration):
    raise DoneExecutionError("remote integration outcome UNKNOWN; reconcile")
  if (_SHA.fullmatch(result.landed_sha) is None or not result.operation_id
      or result.verified is not True):
    raise DoneExecutionError("remote integration has no verified landing")
  if verify_provider_result(fresh, attempt, result) is not True:
    raise DoneExecutionError("provider landed identity readback failed")
  return result
