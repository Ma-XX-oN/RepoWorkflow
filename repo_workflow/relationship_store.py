from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
  migrate_legacy_graph,
)
from .parent_branch import ParentBranchError, recover_parent_branch
from .state_store import StateStoreError, WriterIdentity, durable_store


GRAPH_KEY = "relationships/graph"


class RelationshipStoreError(RuntimeError):
  """Raised when canonical durable relationship state is invalid/conflicted."""


@dataclass(frozen=True)
class RelationshipSnapshot:
  graph: RelationshipGraph
  revision: int


class RelationshipStore:
  """Canonical durable direct relationship graph store and normalized reader."""

  def __init__(self, repository_root: Path):
    self.root = Path(repository_root).resolve()
    self.records = durable_store(self.root)

  def read(self) -> RelationshipSnapshot:
    try:
      record = self.records.read(GRAPH_KEY)
      graph = RelationshipGraph.from_json_value(record["value"])
    except (StateStoreError, RelationshipSchemaError) as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=record["revision"])

  def migrate_legacy(
    self,
    writer: WriterIdentity,
    work_branches: dict[str, str] | None = None,
  ) -> RelationshipSnapshot:
    """Atomically replace one legacy v1 graph with canonical v2 parent state."""
    try:
      record = self.records.read(GRAPH_KEY)
      if record["value"].get("schema_version") != 1:
        return self.read()
      mapping = {} if work_branches is None else work_branches
      def recover(issue: str) -> str:
        try:
          branch = mapping[issue]
        except KeyError as error:
          raise RelationshipStoreError(
            f"legacy issue {issue} requires explicit work-branch identity"
          ) from error
        return recover_parent_branch(self.root, branch)
      graph = migrate_legacy_graph(record["value"], recover)
      replaced = self.records.replace(
        GRAPH_KEY,
        record["revision"],
        graph.to_json_value(),
        writer,
      )
    except (StateStoreError, RelationshipSchemaError, ParentBranchError) as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=replaced["revision"])

  def create(
    self,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    graph = _validated_graph(graph)
    try:
      record = self.records.create(
        GRAPH_KEY,
        graph.to_json_value(),
        writer,
      )
    except StateStoreError as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=record["revision"])

  def replace(
    self,
    expected_revision: int,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    graph = _validated_graph(graph)
    try:
      record = self.records.replace(
        GRAPH_KEY,
        expected_revision,
        graph.to_json_value(),
        writer,
      )
    except StateStoreError as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=record["revision"])

  def issue(self, issue: str | int) -> IssueRelationships:
    try:
      return self.read().graph.issue(issue)
    except RelationshipSchemaError as error:
      raise RelationshipStoreError(str(error)) from error

  def direct_dependencies(self, issue: str | int) -> tuple[str, ...]:
    return self.issue(issue).depends_on


def _validated_graph(graph: RelationshipGraph) -> RelationshipGraph:
  if not isinstance(graph, RelationshipGraph):
    raise RelationshipStoreError("graph must be a RelationshipGraph")
  try:
    return RelationshipGraph.from_json_value(graph.to_json_value())
  except RelationshipSchemaError as error:
    raise RelationshipStoreError(str(error)) from error
