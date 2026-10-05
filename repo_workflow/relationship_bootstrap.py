from __future__ import annotations

from pathlib import Path

from .relationship_store import RelationshipStore, RelationshipStoreError
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
  """Create the missing canonical dependency graph from ticket-native facts."""
  store = RelationshipStore(root)
  try:
    store.read()
    return
  except RelationshipStoreError as error:
    if "record is missing:" not in str(error):
      raise

  pending = [str(int(value)) for value in roots]
  config = resolve_dependency_config(root)
  issues: dict[str, IssueRelationships] = {}

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
  store.create(graph, writer)
