from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import git
from .lane_projection import (
  ProjectionRule,
  decompose_rules,
  normalize_rules,
)
from .relationship_store import RelationshipStore, RelationshipStoreError
from .state_store import JsonRecordStore, StateStoreError, WriterIdentity


RECORD_KEY = "selection"
SCHEMA_VERSION = 4


class LaneSelectionError(RuntimeError):
  pass


@dataclass(frozen=True)
class LaneSelection:
  roots: tuple[str, ...]
  closure: tuple[str, ...]
  graph_revision: int
  assignment: dict[str, str]
  includes: tuple[ProjectionRule, ...] = ()
  excludes: tuple[ProjectionRule, ...] = ()
  schema_version: int = SCHEMA_VERSION

  def to_json_value(self) -> dict:
    return {
      "schema_version": self.schema_version,
      "roots": list(self.roots),
      "includes": [rule.to_json_value() for rule in self.includes],
      "excludes": [rule.to_json_value() for rule in self.excludes],
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
      None if not parsed.includes else parsed,
      record["revision"],
    )

  def project(
    self,
    roots: tuple[str | int, ...],
  ) -> LaneSelection:
    return self.project_rules(_rules(roots, "both"))

  def project_rules(
    self,
    includes: tuple[ProjectionRule, ...],
    excludes: tuple[ProjectionRule, ...] = (),
  ) -> LaneSelection:
    include_rules = normalize_rules(includes)
    exclude_rules = normalize_rules(excludes)
    if not include_rules:
      raise LaneSelectionError("lane selection requires at least one include rule")
    try:
      graph = RelationshipStore(self.root).read()
    except RelationshipStoreError as error:
      if "record is missing:" in str(error):
        raise LaneSelectionError(
          "canonical relationship graph is not initialized"
        ) from error
      raise LaneSelectionError(str(error)) from error

    plan = decompose_rules(graph.graph, include_rules, exclude_rules)
    assignment = {
      issue: lane.name
      for lane in plan.lanes
      for issue in lane.issues
    }
    roots = tuple(sorted({rule.seed for rule in include_rules}, key=int))
    return LaneSelection(
      roots=roots,
      closure=plan.closure,
      graph_revision=graph.revision,
      assignment=assignment,
      includes=include_rules,
      excludes=exclude_rules,
    )

  def select(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int | None = None,
  ) -> LaneSelectionSnapshot:
    return self.select_rules(
      _rules(roots, "both"),
      writer,
      expected_revision=expected_revision,
    )

  def select_rules(
    self,
    includes: tuple[ProjectionRule, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int | None = None,
    excludes: tuple[ProjectionRule, ...] = (),
  ) -> LaneSelectionSnapshot:
    value = self.project_rules(includes, excludes)
    return self._write_value(value, writer, expected_revision)

  def add(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    return self.add_rules(
      _rules(roots, "both"),
      writer,
      expected_revision=expected_revision,
    )

  def add_rules(
    self,
    additions: tuple[ProjectionRule, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    includes = normalize_rules((*current.value.includes, *additions))
    value = self.project_rules(includes, current.value.excludes)
    return self._write_value(value, writer, expected_revision)

  def remove(
    self,
    roots: tuple[str | int, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    return self.remove_rules(
      _rules(roots, "both"),
      writer,
      expected_revision=expected_revision,
    )

  def remove_rules(
    self,
    removals: tuple[ProjectionRule, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    remove_set = set(normalize_rules(removals))
    includes = tuple(
      rule
      for rule in current.value.includes
      if rule not in remove_set
    )
    if not includes:
      raise LaneSelectionError(
        "remove would leave an empty selection; use clear"
      )
    value = self.project_rules(includes, current.value.excludes)
    return self._write_value(value, writer, expected_revision)

  def exclude_rules(
    self,
    additions: tuple[ProjectionRule, ...],
    writer: WriterIdentity,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    current = self._expected(expected_revision)
    excludes = normalize_rules((*current.value.excludes, *additions))
    value = self.project_rules(current.value.includes, excludes)
    return self._write_value(value, writer, expected_revision)

  def clear(
    self,
    *,
    expected_revision: int,
  ) -> LaneSelectionSnapshot:
    self._expected(expected_revision)
    empty = {
      "schema_version": SCHEMA_VERSION,
      "roots": [],
      "includes": [],
      "excludes": [],
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

  def _write_value(
    self,
    value: LaneSelection,
    writer: WriterIdentity,
    expected_revision: int | None,
  ) -> LaneSelectionSnapshot:
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


def _selection(value: dict) -> LaneSelection:
  if not isinstance(value, dict):
    raise LaneSelectionError("lane selection must be an object")

  version = value.get("schema_version")
  legacy_expected = {
    "schema_version",
    "roots",
    "closure",
    "graph_revision",
    "assignment",
  }
  if version == 1:
    expected = legacy_expected
  elif version == 2:
    expected = legacy_expected | {"follow"}
  elif version == 3:
    expected = legacy_expected | {"follow", "show_children"}
  elif version == SCHEMA_VERSION:
    expected = legacy_expected | {"includes", "excludes"}
  else:
    raise LaneSelectionError("unsupported lane selection schema version")
  if set(value) != expected:
    raise LaneSelectionError("lane selection has missing/unsupported fields")

  roots = _ids(tuple(value["roots"]))
  closure = _ids(tuple(value["closure"]))
  revision = value["graph_revision"]
  if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
    raise LaneSelectionError("invalid relationship graph revision")

  if version == SCHEMA_VERSION:
    includes = _rule_values(value["includes"], "includes")
    excludes = _rule_values(value["excludes"], "excludes")
    include_roots = tuple(sorted({rule.seed for rule in includes}, key=int))
    if roots != include_roots:
      raise LaneSelectionError("roots must match include-rule seeds")
  else:
    includes = _rules(roots, "both")
    excludes = ()

  assignment = value["assignment"]
  if not isinstance(assignment, dict) or set(assignment) != set(closure):
    raise LaneSelectionError("lane assignment must cover the complete closure")
  normalized: dict[str, str] = {}
  for issue, lane in assignment.items():
    if not isinstance(lane, str) or not lane:
      raise LaneSelectionError("lane name must be non-empty text")
    normalized[issue] = lane

  return LaneSelection(
    roots=roots,
    closure=closure,
    graph_revision=revision,
    assignment=normalized,
    includes=includes,
    excludes=excludes,
  )


def _rule_values(
  values: object,
  field: str,
) -> tuple[ProjectionRule, ...]:
  if not isinstance(values, list):
    raise LaneSelectionError(f"{field} must be an array")
  try:
    rules = tuple(ProjectionRule.from_json_value(value) for value in values)
    normalized = normalize_rules(rules)
  except ValueError as error:
    raise LaneSelectionError(str(error)) from error
  if tuple(rules) != normalized:
    raise LaneSelectionError(f"{field} must be unique and deterministic")
  return normalized


def _rules(
  roots: tuple[str | int, ...],
  mode: str,
) -> tuple[ProjectionRule, ...]:
  normalized = _ids(roots)
  if not normalized:
    raise LaneSelectionError("lane selection requires at least one root")
  return tuple(ProjectionRule(issue, mode) for issue in normalized)


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
