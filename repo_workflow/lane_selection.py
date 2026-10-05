from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import git
from .lane_decomposition import LanePlan, decompose_lanes
from .relationship_store import RelationshipStore, RelationshipStoreError
from .state_store import JsonRecordStore, StateStoreError, WriterIdentity


RECORD_KEY = "selection"
SCHEMA_VERSION = 1


class LaneSelectionError(RuntimeError):
  pass


@dataclass(frozen=True)
class LaneSelection:
  roots: tuple[str, ...]
  closure: tuple[str, ...]
  graph_revision: int
  assignment: dict[str, str]
  schema_version: int = SCHEMA_VERSION

  def to_json_value(self) -> dict:
    return {
      "schema_version": self.schema_version,
      "roots": list(self.roots),
      "closure": list(self.closure),
      "graph_revision": self.graph_revision,
      "assignment": {
        issue: self.assignment[issue]
        for issue in sorted(self.assignment, key=int)
      },
    }


@dataclass(frozen=True)
class LaneSelectionSnapshot:
  value: LaneSelection | None
  revision: int | None


class LaneSelectionStore:
  def __init__(self, root: Path):
    self.root = Path(root).resolve()
    git_dir = Path(git(self.root, "rev-parse", "--git-dir").stdout.strip())
    if not git_dir.is_absolute():
      git_dir = (self.root / git_dir).resolve()
    self.records = JsonRecordStore(git_dir / "repoworkflow" / "lane-selection")

  def read(self) -> LaneSelectionSnapshot:
    try:
      record = self.records.read(RECORD_KEY)
    except StateStoreError as error:
      if "record is missing:" in str(error):
        return LaneSelectionSnapshot(None, None)
      raise LaneSelectionError(str(error)) from error
    parsed = _selection(record["value"])
    return LaneSelectionSnapshot(
      None if not parsed.roots else parsed,
      record["revision"],
    )

  def select(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int | None = None,
  ) -> LaneSelectionSnapshot:
    normalized = _ids(roots)
    if not normalized:
      raise LaneSelectionError("lane selection requires at least one root")
    return self._write(normalized, writer, expected_revision)

  def add(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    return self._write(
      tuple(sorted(set(current.value.roots) | set(_ids(roots)), key=int)),
      writer,
      expected_revision,
    )

  def remove(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    remaining = tuple(
      value for value in current.value.roots if value not in set(_ids(roots))
    )
    if not remaining:
      raise LaneSelectionError("remove would leave an empty selection; use clear")
    return self._write(remaining, writer, expected_revision)

  def clear(
    self,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    empty = {
      "schema_version": SCHEMA_VERSION,
      "roots": [],
      "closure": [],
      "graph_revision": self._graph_revision(),
      "assignment": {},
    }
    try:
      record = self.records.replace(
        RECORD_KEY,
        expected_revision,
        empty,
        WriterIdentity("rwf", "clear"),
      )
    except StateStoreError as error:
      raise LaneSelectionError(str(error)) from error
    return LaneSelectionSnapshot(None, record["revision"])

  def _graph_revision(self) -> int:
    try:
      return RelationshipStore(self.root).read().revision
    except RelationshipStoreError as error:
      if "record is missing:" in str(error):
        raise LaneSelectionError(
          "canonical relationship graph is not initialized"
        ) from error
      raise LaneSelectionError(str(error)) from error

  def _expected(self, expected_revision: int) -> LaneSelectionSnapshot:
    current = self.read()
    if current.value is None:
      raise LaneSelectionError("lane selection is missing")
    if current.revision != expected_revision:
      raise LaneSelectionError(
        f"stale lane selection revision: expected {expected_revision}, "
        f"current {current.revision}"
      )
    return current

  def _write(
    self,
    roots: tuple[str, ...],
    writer: WriterIdentity,
    expected_revision: int | None,
  ) -> LaneSelectionSnapshot:
    try:
      graph = RelationshipStore(self.root).read()
    except RelationshipStoreError as error:
      if "record is missing:" in str(error):
        raise LaneSelectionError(
          "canonical relationship graph is not initialized"
        ) from error
      raise LaneSelectionError(str(error)) from error
    plan = decompose_lanes(graph.graph, roots)
    value = _from_plan(plan, graph.revision)
    current = self.read()
    if current.revision != expected_revision:
      raise LaneSelectionError(
        f"stale lane selection revision: expected {expected_revision!r}, "
        f"current {current.revision!r}"
      )
    try:
      if expected_revision is None:
        record = self.records.create(RECORD_KEY, value.to_json_value(), writer)
      else:
        record = self.records.replace(
          RECORD_KEY,
          expected_revision,
          value.to_json_value(),
          writer,
        )
    except StateStoreError as error:
      raise LaneSelectionError(str(error)) from error
    return LaneSelectionSnapshot(value, record["revision"])


def _from_plan(plan: LanePlan, graph_revision: int) -> LaneSelection:
  assignment = {
    issue: lane.name
    for lane in plan.lanes
    for issue in lane.issues
  }
  return LaneSelection(
    roots=plan.selected,
    closure=plan.closure,
    graph_revision=graph_revision,
    assignment=assignment,
  )


def _selection(value: dict) -> LaneSelection:
  if not isinstance(value, dict) or set(value) != {
    "schema_version", "roots", "closure", "graph_revision", "assignment"
  }:
    raise LaneSelectionError("lane selection has missing/unsupported fields")
  if value["schema_version"] != SCHEMA_VERSION:
    raise LaneSelectionError("unsupported lane selection schema version")
  roots = _ids(tuple(value["roots"]))
  closure = _ids(tuple(value["closure"]))
  revision = value["graph_revision"]
  if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
    raise LaneSelectionError("invalid relationship graph revision")
  assignment = value["assignment"]
  if not isinstance(assignment, dict) or set(assignment) != set(closure):
    raise LaneSelectionError("lane assignment must cover the complete closure")
  normalized: dict[str, str] = {}
  for issue, lane in assignment.items():
    if not isinstance(lane, str) or not lane:
      raise LaneSelectionError("lane name must be non-empty text")
    normalized[issue] = lane
  return LaneSelection(roots, closure, revision, normalized)


def _ids(values: tuple[str | int, ...]) -> tuple[str, ...]:
  result: set[str] = set()
  for value in values:
    if isinstance(value, bool):
      raise LaneSelectionError(f"invalid issue id: {value!r}")
    text = str(value)
    if not text.isdigit() or int(text) <= 0:
      raise LaneSelectionError(f"invalid issue id: {value!r}")
    result.add(str(int(text)))
  return tuple(sorted(result, key=int))
