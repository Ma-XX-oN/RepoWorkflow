"""Bridge #69 durable observations to #95 required-unit coverage (#104).

The store and coverage evaluator MUST be the trusted #69/#95 implementations.
The caller MUST supply the complete authoritative requirements manifest.
Current workflow assumes trusted test-result publishers as specified in #548.
"""
from __future__ import annotations
from dataclasses import dataclass


class EvidenceGateError(ValueError):
  pass


@dataclass(frozen=True)
class EvidenceGate:
  tested: str
  complete: bool
  passed: bool
  inputs_current: bool
  required_checks_complete: bool
  applicable: bool
  authenticated: bool


def read_evidence_gate(
  store, requirement_manifest, record_ids, *, candidate, version, branch,
  coverage_evaluator,
) -> EvidenceGate:
  """Read persisted observations; never trust asserted PASS or completeness."""
  if (
    not isinstance(candidate, str) or not candidate
    or not isinstance(version, str) or not version
    or not isinstance(branch, str) or not branch
    or not isinstance(record_ids, (list, tuple)) or not record_ids
    or not isinstance(requirement_manifest, (list, tuple))
    or not requirement_manifest
    or not callable(coverage_evaluator)
  ):
    raise EvidenceGateError("missing authoritative validation inputs")
  ids = tuple(record_ids)
  if any(not isinstance(item, str) or not item for item in ids):
    raise EvidenceGateError("invalid observation identity")
  if len(set(ids)) != len(ids):
    raise EvidenceGateError("duplicate observation identity")
  units = tuple(getattr(r, "unit", None) for r in requirement_manifest)
  if any(not isinstance(unit, str) or not unit for unit in units):
    raise EvidenceGateError("invalid required-unit manifest")
  if len(set(units)) != len(units):
    raise EvidenceGateError("duplicate required unit")
  try:
    observations = [store.read(identifier) for identifier in ids]
    if any(
      observation.candidate_sha != candidate
      or observation.version != version
      or observation.branch != branch
      or observation.record_id != identifier
      for identifier, observation in zip(ids, observations)
    ):
      raise EvidenceGateError("inapplicable durable validation observation")
    coverage = coverage_evaluator(
      list(requirement_manifest),
      [observation.coverage() for observation in observations],
    )
    statuses = coverage.statuses
    if (
      not isinstance(statuses, tuple)
      or set(unit for unit, _ in statuses) != set(units)
      or len(statuses) != len(units)
    ):
      raise EvidenceGateError("incomplete coverage manifest")
    complete = all(status == "satisfied" for _, status in statuses)
  except EvidenceGateError:
    raise
  except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
    raise EvidenceGateError("validation evidence unavailable") from error
  return EvidenceGate(
    tested=candidate, complete=complete, passed=complete,
    inputs_current=complete, required_checks_complete=complete,
    applicable=complete, authenticated=True,
  )
