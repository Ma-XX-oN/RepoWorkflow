from __future__ import annotations

from pathlib import Path

from .relationship_store import RelationshipStore, RelationshipStoreError, RelationshipSnapshot
from .relationships import IssueRelationships, RelationshipGraph
from .state_store import WriterIdentity


def register_issue_relationships(
  repository_root: Path,
  issue: str | int,
  relationships: IssueRelationships,
  writer: WriterIdentity,
  *,
  expected_revision: int | None,
) -> RelationshipSnapshot:
  """Record explicit normalized relationship facts with revisioned CAS."""
  issue_id = _issue_id(issue)
  if not isinstance(relationships, IssueRelationships):
    raise RelationshipStoreError(
      "relationships must be normalized IssueRelationships"
    )

  store = RelationshipStore(repository_root)
  try:
    current = store.read()
  except RelationshipStoreError as error:
    if "record is missing:" not in str(error):
      raise
    if expected_revision is not None:
      raise RelationshipStoreError(
        "relationship graph is missing; expected_revision must be None"
      ) from error
    return store.create(
      RelationshipGraph(issues={issue_id: relationships}),
      writer,
    )

  if expected_revision != current.revision:
    raise RelationshipStoreError(
      "stale relationship graph revision: "
      f"expected {expected_revision!r}, current {current.revision!r}"
    )

  if current.graph.issues.get(issue_id) == relationships:
    return current

  issues = dict(current.graph.issues)
  issues[issue_id] = relationships
  return store.replace(
    current.revision,
    RelationshipGraph(issues=issues),
    writer,
  )


def _issue_id(issue: str | int) -> str:
  if isinstance(issue, bool):
    raise RelationshipStoreError(f"invalid issue id: {issue!r}")
  text = str(issue)
  if not text.isdigit() or int(text) < 1:
    raise RelationshipStoreError(f"invalid issue id: {issue!r}")
  return str(int(text))
