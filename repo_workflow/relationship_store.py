from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .parent_branch import ParentRecoveryError, recover_parent
from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
  legacy_relationships,
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
    self.repository_root = Path(repository_root).resolve()
    self.records = durable_store(self.repository_root)

  def read(self) -> RelationshipSnapshot:
    try:
      record = self.records.read(GRAPH_KEY)
      graph = RelationshipGraph.from_json_value(record["value"])
    except (StateStoreError, RelationshipSchemaError) as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=record["revision"])


  def migrate_legacy(
    self,
    work_branches: dict[str | int, str],
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    """Atomically migrate schema v1 to v2."""
    try:
      record = self.records.read(GRAPH_KEY)
    except StateStoreError as error:
      raise RelationshipStoreError(str(error)) from error
    value = record["value"]
    if isinstance(value, dict) and value.get("schema_version") == 2:
      return self.read()
    try:
      legacy = legacy_relationships(value)
      normalized_branches = {
        _issue_id(issue): branch for issue, branch in work_branches.items()
      }
      issues: dict[str, IssueRelationships] = {}
      for issue_id, raw in legacy.items():
        branch_base = raw["branch_base"]
        integration_target = raw["integration_target"]
        if branch_base == integration_target:
          parent = branch_base
        else:
          branch = normalized_branches.get(issue_id)
          if branch is None:
            raise RelationshipStoreError(
              f"issue {issue_id}: conflicting legacy parent fields require "
              "explicit work-branch identity"
            )
          try:
            parent = recover_parent(self.repository_root, branch)
          except ParentRecoveryError as error:
            raise RelationshipStoreError(
              f"issue {issue_id}: parent recovery failed: {error}"
            ) from error
        issues[issue_id] = IssueRelationships(
          umbrella=raw["umbrella"],
          shared_umbrellas=tuple(raw["shared_umbrellas"]),
          depends_on=tuple(raw["depends_on"]),
          umbrella_depends_on=tuple(raw["umbrella_depends_on"]),
          parent=parent,
        )
      graph = RelationshipGraph.from_json_value({
        "schema_version": 2,
        "issues": {
          issue_id: relation.to_json_value()
          for issue_id, relation in issues.items()
        },
      })
    except RelationshipSchemaError as error:
      raise RelationshipStoreError(str(error)) from error

    try:
      migrated = self.records.replace(
        GRAPH_KEY,
        record["revision"],
        graph.to_json_value(),
        writer,
      )
    except StateStoreError as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph=graph, revision=migrated["revision"])

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


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise RelationshipStoreError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1:
    raise RelationshipStoreError(f"invalid issue id: {value!r}")
  return str(int(text))
