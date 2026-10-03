from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
)
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
    self.records = durable_store(Path(repository_root).resolve())

  def read(self) -> RelationshipSnapshot:
    try:
      record = self.records.read(GRAPH_KEY)
      graph = RelationshipGraph.from_json_value(record["value"])
    except (StateStoreError, RelationshipSchemaError) as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=record["revision"])

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
