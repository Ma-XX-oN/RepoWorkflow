from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class DependencyComparisonStatus(str, Enum):
  MATCH = "MATCH"
  SOURCE_ONLY = "SOURCE_ONLY"
  DESTINATION_ONLY = "DESTINATION_ONLY"
  CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class DependencyComparison:
  source: tuple[int, ...]
  destination: tuple[int, ...]
  additions: tuple[int, ...]
  removals: tuple[int, ...]
  status: DependencyComparisonStatus


def _normalize(values: Iterable[int], label: str) -> tuple[int, ...]:
  normalized: set[int] = set()
  for value in values:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
      raise ValueError(f"{label} dependency IDs must be positive integers")
    normalized.add(value)
  return tuple(sorted(normalized))


def compare_dependencies(
  source: Iterable[int],
  destination: Iterable[int],
) -> DependencyComparison:
  source_set = _normalize(source, "source")
  destination_set = _normalize(destination, "destination")
  source_values = set(source_set)
  destination_values = set(destination_set)
  additions = tuple(sorted(source_values - destination_values))
  removals = tuple(sorted(destination_values - source_values))

  if not additions and not removals:
    status = DependencyComparisonStatus.MATCH
  elif source_set and not destination_set:
    status = DependencyComparisonStatus.SOURCE_ONLY
  elif destination_set and not source_set:
    status = DependencyComparisonStatus.DESTINATION_ONLY
  else:
    status = DependencyComparisonStatus.CONFLICT

  return DependencyComparison(
    source=source_set,
    destination=destination_set,
    additions=additions,
    removals=removals,
    status=status,
  )
