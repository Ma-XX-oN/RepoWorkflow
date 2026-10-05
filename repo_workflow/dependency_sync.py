from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .dependency_comparison import (
  DependencyComparison,
  DependencyComparisonStatus,
  compare_dependencies,
)
from .relationship_store import RelationshipStore
from .ticket_dependency_adapter import (
  read_ticket_dependencies,
  replace_ticket_dependencies,
)


class DependencySyncStatus(str, Enum):
  MATCH = "MATCH"
  SYNCHRONIZED = "SYNCHRONIZED"
  CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class DependencySyncResult:
  issue: int
  status: DependencySyncStatus
  comparison: DependencyComparison
  dependencies: tuple[int, ...]


class DependencySyncConflict(RuntimeError):
  pass


def sync_to_tickets(
  root: Path,
  config: dict,
  issue: int,
  *,
  replace: bool = False,
) -> DependencySyncResult:
  rwf = tuple(int(value) for value in RelationshipStore(root).direct_dependencies(issue))
  ticket = read_ticket_dependencies(root, config, issue)
  comparison = compare_dependencies(rwf, ticket)

  if comparison.status == DependencyComparisonStatus.MATCH:
    return DependencySyncResult(
      issue, DependencySyncStatus.MATCH, comparison, ticket
    )

  destination_empty = not comparison.destination
  if not destination_empty and not replace:
    raise DependencySyncConflict(
      f"ticket dependencies conflict for issue #{issue}: "
      f"RWF={list(comparison.source)} tickets={list(comparison.destination)}"
    )

  confirmed = replace_ticket_dependencies(
    root,
    config,
    issue,
    comparison.source,
  )
  return DependencySyncResult(
    issue,
    DependencySyncStatus.SYNCHRONIZED,
    comparison,
    confirmed,
  )
