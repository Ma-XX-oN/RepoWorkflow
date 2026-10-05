from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .dependency_comparison import (
  DependencyComparison,
  DependencyComparisonStatus,
  compare_dependencies,
)
from .relationship_registration import register_issue_relationships
from .relationship_store import RelationshipStore
from .relationships import IssueRelationships
from .state_store import WriterIdentity
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


def sync_from_tickets(
  root: Path,
  config: dict,
  issue: int,
  writer: WriterIdentity,
  *,
  replace: bool = False,
) -> DependencySyncResult:
  store = RelationshipStore(root)
  snapshot = store.read()
  relation = snapshot.graph.issue(issue)
  rwf = tuple(int(value) for value in relation.depends_on)
  ticket = read_ticket_dependencies(root, config, issue)
  comparison = compare_dependencies(ticket, rwf)

  if comparison.status == DependencyComparisonStatus.MATCH:
    return DependencySyncResult(
      issue, DependencySyncStatus.MATCH, comparison, rwf
    )

  destination_empty = not comparison.destination
  if not destination_empty and not replace:
    raise DependencySyncConflict(
      f"RWF dependencies conflict for issue #{issue}: "
      f"tickets={list(comparison.source)} RWF={list(comparison.destination)}"
    )

  replacement = IssueRelationships(
    umbrella=relation.umbrella,
    shared_umbrellas=relation.shared_umbrellas,
    depends_on=tuple(str(value) for value in comparison.source),
    umbrella_depends_on=relation.umbrella_depends_on,
    parent=relation.parent,
  )
  registered = register_issue_relationships(
    root,
    issue,
    replacement,
    writer,
    expected_revision=snapshot.revision,
  )
  confirmed = tuple(
    int(value) for value in registered.graph.issue(issue).depends_on
  )
  return DependencySyncResult(
    issue,
    DependencySyncStatus.SYNCHRONIZED,
    comparison,
    confirmed,
  )
