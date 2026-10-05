from __future__ import annotations

from pathlib import Path

from .dependency_migration_certification import (
  DependencyMigrationCertificationError,
  require_dependency_migration_certified,
)
from .relationship_store import (
  RelationshipSnapshot,
  RelationshipStore,
  RelationshipStoreError,
)
from .relationships import IssueRelationships, RelationshipGraph
from .state_store import WriterIdentity
from .ticket_dependency_adapter import (
  TicketDependencyError,
  read_ticket_dependencies,
  resolve_dependency_config,
)


def ensure_relationship_graph(
  root: Path,
  roots: tuple[str | int, ...],
  writer: WriterIdentity,
) -> None:
  """Ensure/reconcile canonical graph coverage for requested ticket roots."""
  try:
    require_dependency_migration_certified(root)
  except DependencyMigrationCertificationError as error:
    raise TicketDependencyError(str(error)) from error

  store = RelationshipStore(root)
  snapshot = _read_optional(store)
  issues = {} if snapshot is None else dict(snapshot.graph.issues)
  requested = tuple(sorted({str(int(value)) for value in roots}, key=int))
  config = resolve_dependency_config(root)
  pending = list(requested)
  visited: set[str] = set()
  changed = snapshot is None

  while pending:
    issue = pending.pop(0)
    if issue in visited:
      continue
    visited.add(issue)

    provider = tuple(
      str(value)
      for value in read_ticket_dependencies(root, config, int(issue))
    )
    current = issues.get(issue)

    if current is None:
      issues[issue] = IssueRelationships(
        umbrella=None,
        shared_umbrellas=(),
        depends_on=provider,
        umbrella_depends_on=(),
        parent=None,
      )
      changed = True
    elif not current.depends_on:
      if provider:
        issues[issue] = IssueRelationships(
          umbrella=current.umbrella,
          shared_umbrellas=current.shared_umbrellas,
          depends_on=provider,
          umbrella_depends_on=current.umbrella_depends_on,
          parent=current.parent,
        )
        changed = True
    elif current.depends_on != provider:
      raise TicketDependencyError(
        "canonical relationship dependencies conflict with native ticket "
        f"dependencies for #{issue}: "
        f"canonical={list(current.depends_on)!r}, provider={list(provider)!r}; "
        "reconcile explicitly before lane selection"
      )

    for dependency in provider:
      if dependency not in visited and dependency not in pending:
        pending.append(dependency)

  if not changed:
    return

  graph = RelationshipGraph.from_json_value({
    "schema_version": 2,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in issues.items()
    },
  })

  if snapshot is None:
    store.create(graph, writer)
  else:
    store.replace(snapshot.revision, graph, writer)


def _read_optional(store: RelationshipStore) -> RelationshipSnapshot | None:
  try:
    return store.read()
  except RelationshipStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise
