from __future__ import annotations

from pathlib import Path

from .relationship_store import (
  RelationshipSnapshot,
  RelationshipStore,
  RelationshipStoreError,
)
from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
)
from .state_store import WriterIdentity


class RelationshipRegistrationError(RuntimeError):
  """Raised when canonical ticket registration cannot proceed safely."""


def register_issue_relationships(
  repository_root: Path,
  issue: str | int,
  relationships: IssueRelationships,
  writer: WriterIdentity,
  *,
  expected_revision: int | None = None,
) -> RelationshipSnapshot:
  issue_id = _issue_id(issue)
  if not isinstance(relationships, IssueRelationships):
    raise RelationshipRegistrationError(
      "relationships must be an IssueRelationships value"
    )
  store = RelationshipStore(repository_root)

  try:
    current = store.read()
  except RelationshipStoreError as error:
    if "record is missing:" not in str(error):
      raise RelationshipRegistrationError(str(error)) from error
    if expected_revision is not None:
      raise RelationshipRegistrationError(
        "ticket state is missing; expected revision cannot be supplied"
      ) from error
    graph = _graph_with({}, issue_id, relationships)
    try:
      return store.create(graph, writer)
    except RelationshipStoreError as create_error:
      raise RelationshipRegistrationError(str(create_error)) from create_error

  existing = current.graph.issues.get(issue_id)
  if existing == relationships:
    return current

  if expected_revision is None:
    raise RelationshipRegistrationError(
      "conflicting ticket replacement requires expected revision"
    )
  if expected_revision != current.revision:
    raise RelationshipRegistrationError(
      "stale ticket-state revision: "
      f"expected {expected_revision}, current {current.revision}"
    )

  graph = _graph_with(current.graph.issues, issue_id, relationships)
  try:
    return store.replace(current.revision, graph, writer)
  except RelationshipStoreError as error:
    raise RelationshipRegistrationError(str(error)) from error


def _graph_with(
  current: dict[str, IssueRelationships],
  issue_id: str,
  relationships: IssueRelationships,
) -> RelationshipGraph:
  issues = dict(current)
  issues[issue_id] = relationships
  try:
    return RelationshipGraph.from_json_value({
      "schema_version": 3,
      "issues": {
        key: value.to_json_value()
        for key, value in issues.items()
      },
    })
  except RelationshipSchemaError as error:
    raise RelationshipRegistrationError(str(error)) from error


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise RelationshipRegistrationError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1:
    raise RelationshipRegistrationError(f"invalid issue id: {value!r}")
  return str(int(text))
