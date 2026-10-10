"""Fail-closed reusable local-to-hosted evidence import classification (#70)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .validation_coverage import Requirement
from .validation_store import ValidationEvidenceStore, ValidationObservation


ImportStatus = Literal["applicable", "stale", "missing", "unusable"]


@dataclass(frozen=True)
class ImportDecision:
  unit: str
  status: ImportStatus
  accepted_record_ids: tuple[str, ...]
  reason: str


def classify_import(
  requirements: list[Requirement],
  observations: list[ValidationObservation],
  target_candidate_sha: str,
  *,
  trusted_record_ids: frozenset[str],
  equivalent_candidate_shas: frozenset[str],
) -> tuple[ImportDecision, ...]:
  """Classify authenticated reusable evidence without changing its verdict.

  Trusted IDs must originate from independent durable provenance checks.
  Equivalent candidate SHAs must have been independently proven equivalent
  for the required unit input closure; equality of SHAs is always allowed.
  The #68 fingerprints include required runtime capability inputs.
  """
  if (
    not isinstance(target_candidate_sha, str)
    or len(target_candidate_sha) not in (40, 64)
    or any(ch not in "0123456789abcdef" for ch in target_candidate_sha)
  ):
    raise ValueError("invalid exact target candidate SHA")
  if not isinstance(trusted_record_ids, frozenset):
    raise ValueError("explicit trusted evidence IDs are required")
  if not isinstance(equivalent_candidate_shas, frozenset):
    raise ValueError("explicit equivalence proof set is required")
  if any(not isinstance(r, Requirement) for r in requirements):
    raise ValueError("invalid required validation unit")
  if any(not isinstance(o, ValidationObservation) for o in observations):
    raise ValueError("invalid stored validation observation")
  units: dict[str, Requirement] = {}
  for item in requirements:
    if item.unit in units:
      raise ValueError("duplicate required unit")
    units[item.unit] = item
  result = []
  for unit in sorted(units):
    requirement = units[unit]
    matching_unit = [o for o in observations if o.unit == unit]
    accepted = []
    reasons: set[str] = set()
    for record in matching_unit:
      if record.record_id not in trusted_record_ids:
        reasons.add("untrusted provenance")
        continue
      if record.verdict != "PASS":
        reasons.add("no reusable PASS")
        continue
      if requirement.mode == "manual" and record.mode != "manual":
        reasons.add("automated evidence cannot satisfy manual validation")
        continue
      if record.fingerprint != requirement.fingerprint:
        reasons.add("changed effective inputs or capabilities")
        continue
      if (
        record.candidate_sha != target_candidate_sha
        and record.candidate_sha not in equivalent_candidate_shas
      ):
        reasons.add("candidate equivalence not established")
        continue
      accepted.append(record.record_id)
    if accepted:
      decision = ImportDecision(unit, "applicable", tuple(sorted(accepted)),
                                "verified matching PASS")
    elif not matching_unit:
      decision = ImportDecision(unit, "missing", (), "no recorded unit evidence")
    elif reasons & {
      "candidate equivalence not established",
      "changed effective inputs or capabilities",
    }:
      decision = ImportDecision(unit, "stale", (), "; ".join(sorted(reasons)))
    else:
      decision = ImportDecision(unit, "unusable", (), "; ".join(sorted(reasons)))
    result.append(decision)
  return tuple(result)


def import_from_store(
  store: ValidationEvidenceStore,
  requirements: list[Requirement],
  target_candidate_sha: str,
  *,
  trusted_record_ids: frozenset[str],
  equivalent_candidate_shas: frozenset[str],
) -> tuple[ImportDecision, ...]:
  """Verify every durable record on read; corruption aborts the import."""
  observations = [store.read(record_id) for record_id in store.list_ids()]
  return classify_import(
    requirements, observations, target_candidate_sha,
    trusted_record_ids=trusted_record_ids,
    equivalent_candidate_shas=equivalent_candidate_shas,
  )
