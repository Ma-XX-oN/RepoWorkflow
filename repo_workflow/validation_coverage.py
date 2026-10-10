"""Pure per-unit validation coverage applicability and invalidation (#95)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .evidence_identity import _name

Status = Literal["satisfied", "missing", "stale", "pending"]
Mode = Literal["automated", "manual"]
Verdict = Literal["PASS", "FAIL", "INCOMPLETE", "PENDING"]


@dataclass(frozen=True)
class Requirement:
  unit: str
  fingerprint: str
  mode: Mode = "automated"

  def __post_init__(self) -> None:
    _name(self.unit, "unit")
    _fingerprint(self.fingerprint)
    if self.mode not in ("automated", "manual"):
      raise ValueError("invalid requirement mode")


@dataclass(frozen=True)
class Evidence:
  unit: str
  fingerprint: str
  verdict: Verdict
  mode: Mode
  provenance: str

  def __post_init__(self) -> None:
    _name(self.unit, "unit")
    _fingerprint(self.fingerprint)
    if self.verdict not in ("PASS", "FAIL", "INCOMPLETE", "PENDING"):
      raise ValueError("invalid evidence verdict")
    if self.mode not in ("automated", "manual"):
      raise ValueError("invalid evidence mode")
    _name(self.provenance, "provenance")


@dataclass(frozen=True)
class Coverage:
  statuses: tuple[tuple[str, Status], ...]

  @property
  def complete(self) -> bool:
    return all(value == "satisfied" for _, value in self.statuses)

  def status(self, unit: str) -> Status:
    return dict(self.statuses)[unit]


def _fingerprint(value: str) -> None:
  if (
    not isinstance(value, str) or len(value) != 64
    or any(character not in "0123456789abcdef" for character in value)
  ):
    raise ValueError("fingerprint must be a lowercase SHA-256 digest")


def evaluate(requirements: list[Requirement],
             evidence: list[Evidence]) -> Coverage:
  """Determine required-unit coverage without using command/run history.

  Callers MUST independently authenticate evidence provenance and the
  completeness of per-unit manifests before invoking this pure evaluator.
  Never infer manual validation from automated evidence.
  """
  if any(not isinstance(item, Requirement) for item in requirements):
    raise ValueError("invalid requirement")
  if any(not isinstance(item, Evidence) for item in evidence):
    raise ValueError("invalid evidence")
  expected: dict[str, Requirement] = {}
  for requirement in requirements:
    if requirement.unit in expected:
      raise ValueError("duplicate requirement unit")
    expected[requirement.unit] = requirement

  result: list[tuple[str, Status]] = []
  for unit in sorted(expected):
    requirement = expected[unit]
    related = [item for item in evidence if item.unit == unit]
    current = [
      item for item in related
      if item.fingerprint == requirement.fingerprint
      and (requirement.mode != "manual" or item.mode == "manual")
    ]
    if any(item.verdict == "PASS" for item in current):
      status: Status = "satisfied"
    elif any(item.verdict == "PENDING" for item in current):
      status = "pending"
    elif related and not current:
      status = "stale"
    else:
      status = "missing"
    result.append((unit, status))
  return Coverage(tuple(result))
