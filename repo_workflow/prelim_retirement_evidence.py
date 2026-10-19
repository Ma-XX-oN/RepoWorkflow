"""Independently verify GitHub landing and immutable terminal evidence.

Read-only provider adapter. Untrusted green checks or PR status cannot
substitute for landed Git ancestry and exact durable integration provenance.
"""
from collections.abc import Callable
import re

from .prelim_retirement import (
  LandedIntegration, PrelimRetirementError, RetirementPlan,
  plan_retirement,
)


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_retirement_evidence(
    landed: LandedIntegration,
    *,
    read_ref: Callable[[str], str | None],
    compare_commits: Callable[[str, str], dict],
    read_terminal: Callable[[str], dict | None],
) -> RetirementPlan:
  """Return retirement eligibility only on exact independently read evidence.

  compare_commits(base_sha, head_sha) must return a validated provider
  response describing whether head descends from base. The caller supplies
  the authorized authenticated provider, never PRELIM-local evidence.
  """
  if not isinstance(landed, LandedIntegration):
    raise PrelimRetirementError("landing record is required")
  if any(type(value) is not str or not value for value in (
      landed.prelim_ref, landed.int_attempt_ref,
      landed.destination_ref, landed.terminal_evidence_ref,
  )):
    raise PrelimRetirementError("landing references are invalid")
  if any(type(sha) is not str or _SHA.fullmatch(sha) is None for sha in (
      landed.prelim_sha, landed.accepted_sha, landed.landed_sha)):
    raise PrelimRetirementError("landing SHA is malformed")

  tip = read_ref(landed.destination_ref)
  if type(tip) is not str or _SHA.fullmatch(tip) is None:
    raise PrelimRetirementError("destination tip unavailable")
  observed_prelim = read_ref(landed.prelim_ref)
  if observed_prelim is not None and (
      type(observed_prelim) is not str or observed_prelim != landed.prelim_sha):
    raise PrelimRetirementError("published PRELIM changed")
  # The accepted integration candidate must be on the landed history.
  # Merely finding a landed commit on the destination proves nothing about
  # whether the purported accepted candidate was actually integrated.
  observed_int = read_ref(landed.int_attempt_ref)
  if observed_int is not None and (
      type(observed_int) is not str
      or observed_int != landed.accepted_sha):
    raise PrelimRetirementError("INT-ATTEMPT changed after acceptance")

  def require_ancestor(base, head, label):
    comparison = compare_commits(base, head)
    if (type(comparison) is not dict
        or comparison.get("base_sha") != base
        or comparison.get("head_sha") != head
        or comparison.get("status") not in {"ahead", "identical"}
        or type(comparison.get("behind_by")) is not int
        or comparison["behind_by"] != 0):
      raise PrelimRetirementError(label + " ancestry not proved by provider")

  require_ancestor(landed.accepted_sha, landed.landed_sha, "accepted candidate")
  require_ancestor(landed.landed_sha, tip, "landed")
  terminal = read_terminal(landed.terminal_evidence_ref)
  expected = {
    "status": "integrated",
    "prelim_ref": landed.prelim_ref,
    "prelim_sha": landed.prelim_sha,
    "int_attempt_ref": landed.int_attempt_ref,
    "accepted_sha": landed.accepted_sha,
    "destination_ref": landed.destination_ref,
    "landed_sha": landed.landed_sha,
    "integration_id": landed.integration_id,
    "terminal_evidence_ref": landed.terminal_evidence_ref,
  }
  if type(terminal) is not dict or terminal != expected:
    raise PrelimRetirementError("terminal evidence identity mismatch")
  return plan_retirement(
    landed.prelim_ref, landed.prelim_sha, landed.int_attempt_ref,
    landed.destination_ref, landed,
    observed_prelim_sha=observed_prelim,
    current_destination_sha=tip,
    landed_is_ancestor=True,
    terminal_record_readback=True,
  )
