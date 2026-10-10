"""Provider-neutral exact-candidate acceptance facts and verdict."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Facts:
  candidate: str
  tested: str
  head: str
  recorded_base: str
  current_base: str
  authenticated: bool
  complete: bool
  passed: bool
  inputs_current: bool
  required_checks_complete: bool
  applicable: bool
  candidate_exists: bool
  base_is_ancestor: bool


def decide(facts: Facts) -> tuple[bool, tuple[str, ...]]:
  if not isinstance(facts, Facts):
    return False, ("invalid-facts",)
  reasons = []
  for field in ("candidate", "tested", "head", "recorded_base", "current_base"):
    value = getattr(facts, field)
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
      reasons.append("invalid-" + field)
  if reasons:
    return False, tuple(reasons)
  if len({len(getattr(facts, field)) for field in (
    "candidate", "tested", "head", "recorded_base", "current_base",
  )}) != 1:
    reasons.append("mixed-hash-length")
  if facts.candidate != facts.tested:
    reasons.append("tested-candidate-mismatch")
  if facts.candidate != facts.head:
    reasons.append("head-changed")
  if facts.recorded_base != facts.current_base:
    reasons.append("stale-base")
  for field in ("authenticated", "complete", "passed", "inputs_current",
                "required_checks_complete", "applicable",
                "candidate_exists", "base_is_ancestor"):
    if getattr(facts, field) is not True:
      reasons.append("missing-" + field)
  return not reasons, tuple(reasons)
