from __future__ import annotations

from pathlib import Path

from .relationship_store import (
  RelationshipSnapshot,
  RelationshipStore,
  RelationshipStoreError,
)
from .relationships import IssueRelationships, RelationshipGraph
from .state_store import WriterIdentity
from .ticket_dependency_adapter import (
  read_ticket_dependencies,
  resolve_dependency_config,
)


def ensure_relationship_graph(
  root: Path,
  roots: tuple[str | int, ...],
  writer: WriterIdentity,
) -> None:
  """Ensure canonical graph coverage for the requested roots and dependencies."""
  store = RelationshipStore(root)
  snapshot = _read_optional(store)
  existing = {} if snapshot is None else dict(snapshot.graph.issues)
  requested = tuple(sorted({str(int(value)) for value in roots}, key=int))

  missing = [issue for issue in requested if issue not in existing]
  if not missing:
    return

  config = resolve_dependency_config(root)
  issues = dict(existing)
  pending = list(missing)

  while pending:
    issue = pending.pop(0)
    if issue in issues:
      continue
    dependencies = tuple(
      str(value)
      for value in read_ticket_dependencies(root, config, int(issue))
    )
    issues[issue] = IssueRelationships(
      umbrella=None,
      shared_umbrellas=(),
      depends_on=dependencies,
      umbrella_depends_on=(),
      parent=None,
    )
    for dependency in dependencies:
      if dependency not in issues and dependency not in pending:
        pending.append(dependency)

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
