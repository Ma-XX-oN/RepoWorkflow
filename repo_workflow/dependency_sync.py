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
from .repo_info_adapter import issue_info, resolve_info_config
from .state_store import WriterIdentity
from .ticket_dependency_adapter import (
  read_ticket_dependencies,
  replace_ticket_dependencies,
  resolve_dependency_config,
)


class DependencySyncStatus(str, Enum):
  MATCH = "MATCH"
  SYNCHRONIZED = "SYNCHRONIZED"
  PARTIAL = "PARTIAL"
  CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class DependencySyncResult:
  issue: int
  status: DependencySyncStatus
  comparison: DependencyComparison
  dependencies: tuple[int, ...]
  title: str | None = None
  title_match: bool = True


class DependencySyncConflict(RuntimeError):
  pass


def read_ticket_sync_state(
  root: Path,
  config: dict,
  issue: int,
) -> tuple[str, tuple[int, ...]]:
  info_config = resolve_info_config(root, config)
  dependency_config = resolve_dependency_config(root, config)
  info = issue_info(root, info_config, issue)
  dependencies = read_ticket_dependencies(
    root,
    dependency_config,
    issue,
  )
  return info["title"], dependencies


def sync_to_tickets(
  root: Path,
  config: dict,
  issue: int,
  *,
  replace: bool = False,
) -> DependencySyncResult:
  relation = RelationshipStore(root).issue(issue)
  local = tuple(int(value) for value in relation.depends_on)
  ticket_title, ticket = read_ticket_sync_state(root, config, issue)

  if ticket_title != relation.title:
    raise DependencySyncConflict(
      f"ticket title conflict for issue #{issue}: "
      f"RWF={relation.title!r} tickets={ticket_title!r}"
    )

  comparison = compare_dependencies(local, ticket)
  if comparison.status == DependencyComparisonStatus.MATCH:
    return DependencySyncResult(
      issue,
      DependencySyncStatus.MATCH,
      comparison,
      ticket,
      title=ticket_title,
      title_match=True,
    )

  if comparison.destination and not replace:
    raise DependencySyncConflict(
      f"ticket dependencies conflict for issue #{issue}: "
      f"RWF={list(comparison.source)} tickets={list(comparison.destination)}"
    )

  dependency_config = resolve_dependency_config(root, config)
  confirmed = replace_ticket_dependencies(
    root,
    dependency_config,
    issue,
    comparison.source,
  )
  confirmed_title, readback = read_ticket_sync_state(root, config, issue)
  if confirmed_title != relation.title or readback != confirmed:
    raise DependencySyncConflict(
      f"ticket readback changed while synchronizing issue #{issue}"
    )
  return DependencySyncResult(
    issue,
    DependencySyncStatus.SYNCHRONIZED,
    comparison,
    confirmed,
    title=confirmed_title,
    title_match=True,
  )


def sync_from_tickets(
  root: Path,
  config: dict,
  issue: int,
  writer: WriterIdentity,
  *,
  replace: bool = False,
  replace_title: bool = False,
  replace_dependencies: bool = False,
) -> DependencySyncResult:
  store = RelationshipStore(root)
  snapshot = store.read()
  relation = snapshot.graph.issue(issue)
  local = tuple(int(value) for value in relation.depends_on)
  ticket_title, ticket = read_ticket_sync_state(root, config, issue)
  comparison = compare_dependencies(ticket, local)
  title_match = ticket_title == relation.title

  dependency_conflict = (
    comparison.status != DependencyComparisonStatus.MATCH
    and bool(comparison.destination)
  )
  replace_deps = replace or replace_dependencies

  if dependency_conflict and not replace_deps:
    if not title_match and replace_title:
      replacement = IssueRelationships(
        title=ticket_title,
        depends_on=relation.depends_on,
      )
      register_issue_relationships(
        root,
        issue,
        replacement,
        writer,
        expected_revision=snapshot.revision,
      )
      return DependencySyncResult(
        issue,
        DependencySyncStatus.PARTIAL,
        comparison,
        local,
        title=ticket_title,
        title_match=False,
      )
    raise DependencySyncConflict(
      f"RWF dependencies conflict for issue #{issue}: "
      f"tickets={list(comparison.source)} RWF={list(comparison.destination)}"
    )

  dependencies = (
    ticket
    if replace_deps or not comparison.destination
    else local
  )
  replacement = IssueRelationships(
    title=ticket_title,
    depends_on=tuple(str(value) for value in dependencies),
  )

  if replacement == relation:
    return DependencySyncResult(
      issue,
      DependencySyncStatus.MATCH,
      comparison,
      local,
      title=ticket_title,
      title_match=True,
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
    title=ticket_title,
    title_match=title_match,
  )
