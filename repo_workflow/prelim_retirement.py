"""Fail-closed retirement planning for landed PRELIM integration attempts.

No refs are deleted here. The caller verifies provider readback and persists
a durable terminal record before separately authorized ref cleanup.
"""
from dataclasses import dataclass
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")


class PrelimRetirementError(ValueError):
  """Landing or durable completion proof is insufficient for retirement."""


@dataclass(frozen=True)
class LandedIntegration:
  prelim_ref: str
  prelim_sha: str
  int_attempt_ref: str
  accepted_sha: str
  destination_ref: str
  landed_sha: str
  integration_id: str
  terminal_evidence_ref: str


@dataclass(frozen=True)
class RetirementPlan:
  prelim_ref: str
  int_attempt_ref: str
  landed_sha: str
  terminal_evidence_ref: str
  eligible_for_ref_retirement: bool


def plan_retirement(
    submitted_ref: str,
    submitted_sha: str,
    expected_int_attempt_ref: str,
    destination_ref: str,
    landed: LandedIntegration,
    *,
    observed_prelim_sha: str | None,
    current_destination_sha: str,
    landed_is_ancestor: bool,
    terminal_record_readback: bool,
) -> RetirementPlan:
  """Require independently obtained provider and durable-history observations.

  `landed_is_ancestor` must be a provider-backed ancestry check against
  `current_destination_sha`, not an unverified local assertion.
  `terminal_record_readback` must be read from authoritative durable state.
  Neither input may be inferred from a GREEN test or an open pull request.
  """
  if not isinstance(landed, LandedIntegration):
    raise PrelimRetirementError("provider landing record is required")
  if any(not isinstance(ref, str) for ref in (
      submitted_ref, expected_int_attempt_ref, destination_ref)):
    raise PrelimRetirementError("integration refs are invalid")
  for name, value in (
      ("submitted SHA", submitted_sha),
      ("landed candidate", landed.accepted_sha),
      ("landed SHA", landed.landed_sha),
      ("destination tip", current_destination_sha),
  ):
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
      raise PrelimRetirementError(f"{name} is not a full Git SHA")
  if (not submitted_ref.startswith("refs/heads/PRELIM-")
      or not expected_int_attempt_ref.startswith("refs/heads/INT-ATTEMPT-")
      or not destination_ref.startswith("refs/heads/")):
    raise PrelimRetirementError("integration refs are invalid")
  if (landed.prelim_ref != submitted_ref
      or landed.prelim_sha != submitted_sha
      or landed.int_attempt_ref != expected_int_attempt_ref
      or landed.destination_ref != destination_ref):
    raise PrelimRetirementError("landing provenance differs from submission")
  if not landed.integration_id or not landed.terminal_evidence_ref:
    raise PrelimRetirementError("durable integration/evidence identity is missing")
  if observed_prelim_sha is not None and observed_prelim_sha != submitted_sha:
    raise PrelimRetirementError("published PRELIM ref was modified")
  if type(landed_is_ancestor) is not bool or not landed_is_ancestor:
    raise PrelimRetirementError("landed commit not proved on destination")
  if (type(terminal_record_readback) is not bool
      or not terminal_record_readback):
    raise PrelimRetirementError("terminal evidence not durably confirmed")
  return RetirementPlan(
    submitted_ref, expected_int_attempt_ref, landed.landed_sha,
    landed.terminal_evidence_ref, True,
  )
