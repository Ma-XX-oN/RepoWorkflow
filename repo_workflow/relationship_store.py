from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time

from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
  project_legacy_graph,
)
from .state_store import WriterIdentity
from .lifecycle_store import LifecycleStore, STATES


TICKET_STATE_PATH = Path(".repoworkflow") / "tickets.csv"
LEGACY_GRAPH_PATH = (
  Path(".repoworkflow") / "state" / "relationships" / "graph.json"
)
LEGACY_METADATA_PATH = (
  Path(".repoworkflow") / "state" / "issues" / "metadata.json"
)


class RelationshipStoreError(RuntimeError):
  """Raised when canonical synchronized ticket state is invalid/conflicted."""


@dataclass(frozen=True)
class RelationshipSnapshot:
  graph: RelationshipGraph
  revision: int
  states: dict[str, 'TicketState'] | None = None


@dataclass(frozen=True)
class TicketState:
  state: str
  lifecycle_revision: int | None

  def __post_init__(self) -> None:
    if self.state not in STATES:
      raise RelationshipSchemaError(f'invalid ticket state: {self.state!r}')
    revision = self.lifecycle_revision
    if revision is not None and (
      isinstance(revision, bool) or not isinstance(revision, int) or revision < 0
    ):
      raise RelationshipSchemaError('invalid ticket lifecycle revision')
    if (self.state == 'not_started') != (revision is None):
      raise RelationshipSchemaError('ticket state and revision disagree')


class RelationshipStore:
  """Durable synchronized ticket store backed by one canonical CSV file."""

  def __init__(self, repository_root: Path):
    self.root = Path(repository_root).resolve()
    self.path = self.root / TICKET_STATE_PATH

  def read(self) -> RelationshipSnapshot:
    if self.path.exists():
      try:
        text = self.path.read_text(encoding="utf-8")
        graph, states = _parse_ticket_csv(text)
      except (OSError, UnicodeError, RelationshipSchemaError) as error:
        raise RelationshipStoreError(str(error)) from error
      return RelationshipSnapshot(graph, _revision(text), states)

    return self._read_legacy()

  def migrate_legacy(
    self,
    writer: WriterIdentity,
    work_branches: dict[str, str] | None = None,
  ) -> RelationshipSnapshot:
    del work_branches
    if self.path.exists():
      return self.read()
    snapshot = self._read_legacy()
    return self._write_new(snapshot.graph, writer)

  def create(
    self,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    graph = _validated_graph(graph)
    if self.path.exists() or (self.root / LEGACY_GRAPH_PATH).exists():
      raise RelationshipStoreError("canonical ticket state already exists")
    return self._write_new(graph, writer)

  def replace(
    self,
    expected_revision: int,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    graph = _validated_graph(graph)
    _writer(writer)
    current = self.read()
    if current.revision != expected_revision:
      raise RelationshipStoreError(
        "stale ticket-state revision: "
        f"expected {expected_revision}, current {current.revision}"
      )
    return self._write(graph, expected_revision, current.states)

  def issue(self, issue: str | int) -> IssueRelationships:
    try:
      return self.read().graph.issue(issue)
    except RelationshipSchemaError as error:
      raise RelationshipStoreError(str(error)) from error

  def direct_dependencies(self, issue: str | int) -> tuple[str, ...]:
    return self.issue(issue).depends_on

  def refresh_states(self, writer: WriterIdentity) -> RelationshipSnapshot:
    _writer(writer)
    current = self.read()
    lifecycle = LifecycleStore(self.root)
    states = {}
    for issue in sorted(current.graph.issues, key=int):
      record = lifecycle.read(issue)
      states[issue] = TicketState(record.lifecycle.state, record.revision)
    return self._write(current.graph, current.revision, states)

  def _write_new(
    self,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    _writer(writer)
    lock = _lock_path(self.path)
    _acquire_lock(lock)
    try:
      if self.path.exists():
        raise RelationshipStoreError("canonical ticket state already exists")
      text = _render_csv(graph)
      _write_text_atomic(self.path, text)
      return RelationshipSnapshot(graph, _revision(text))
    finally:
      _release_lock(lock)

  def _write(
    self,
    graph: RelationshipGraph,
    expected_revision: int,
    states: dict[str, TicketState] | None = None,
  ) -> RelationshipSnapshot:
    lock = _lock_path(self.path)
    _acquire_lock(lock)
    try:
      if self.path.exists():
        current_text = self.path.read_text(encoding="utf-8")
        current_revision = _revision(current_text)
      else:
        current_revision = self._read_legacy().revision
      if current_revision != expected_revision:
        raise RelationshipStoreError(
          "stale ticket-state revision: "
          f"expected {expected_revision}, current {current_revision}"
        )
      if states is not None:
        states = dict(states)
        lifecycle = LifecycleStore(self.root)
        for issue in sorted(set(graph.issues) - set(states), key=int):
          record = lifecycle.read(issue)
          states[issue] = TicketState(record.lifecycle.state, record.revision)
        states = {issue: states[issue] for issue in graph.issues}
      text = _render_csv(graph, states)
      _write_text_atomic(self.path, text)
      return RelationshipSnapshot(graph, _revision(text), states)
    finally:
      _release_lock(lock)

  def _read_legacy(self) -> RelationshipSnapshot:
    graph_path = self.root / LEGACY_GRAPH_PATH
    try:
      graph_record = json.loads(graph_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
      raise RelationshipStoreError(
        f"record is missing: {self.path}"
      ) from error
    except (json.JSONDecodeError, OSError) as error:
      raise RelationshipStoreError(
        f"legacy relationship state is invalid: {graph_path}"
      ) from error

    try:
      if not isinstance(graph_record, dict):
        raise ValueError("legacy relationship record must be an object")
      value = graph_record["value"]
      revision = graph_record["revision"]
      if isinstance(revision, bool) or not isinstance(revision, int):
        raise ValueError("legacy relationship revision is invalid")
      titles = _legacy_titles(self.root)
      graph = project_legacy_graph(value, titles)
    except (KeyError, ValueError, RelationshipSchemaError) as error:
      raise RelationshipStoreError(str(error)) from error
    return RelationshipSnapshot(graph, revision)


def _legacy_titles(root: Path) -> dict[str, str]:
  path = root / LEGACY_METADATA_PATH
  try:
    record = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as error:
    raise RelationshipStoreError(
      "legacy synchronized titles are missing; refresh ticket metadata "
      "before migrating canonical ticket state"
    ) from error
  except (json.JSONDecodeError, OSError) as error:
    raise RelationshipStoreError(
      f"legacy issue metadata is invalid: {path}"
    ) from error

  try:
    value = record["value"]
    raw = value["issues"]
  except (KeyError, TypeError) as error:
    raise RelationshipStoreError(
      "legacy issue metadata has an invalid shape"
    ) from error
  if not isinstance(raw, dict):
    raise RelationshipStoreError("legacy issue metadata issues must be an object")

  titles: dict[str, str] = {}
  for key, item in raw.items():
    if not isinstance(item, dict):
      raise RelationshipStoreError(
        f"legacy issue metadata record {key} is invalid"
      )
    title = item.get("title")
    if not isinstance(title, str) or not title:
      raise RelationshipStoreError(
        f"legacy issue metadata title is missing for issue {key}"
      )
    titles[str(int(key))] = title
  return titles


def _validated_graph(graph: RelationshipGraph) -> RelationshipGraph:
  if not isinstance(graph, RelationshipGraph):
    raise RelationshipStoreError("graph must be a RelationshipGraph")
  try:
    return RelationshipGraph.from_json_value(graph.to_json_value())
  except RelationshipSchemaError as error:
    raise RelationshipStoreError(str(error)) from error


def _render_csv(graph: RelationshipGraph) -> str:
  graph = _validated_graph(graph)
  output = io.StringIO(newline="")
  writer = csv.writer(output, lineterminator="\n")
  writer.writerow(("issue", "title", "dependencies"))
  for issue in sorted(graph.issues, key=int):
    relation = graph.issues[issue]
    writer.writerow((
      issue,
      relation.title,
      ";".join(relation.depends_on),
    ))
  return output.getvalue()


def _parse_csv(text: str) -> RelationshipGraph:
  try:
    rows = list(csv.reader(io.StringIO(text, newline="")))
  except csv.Error as error:
    raise RelationshipSchemaError(f"invalid ticket CSV: {error}") from error
  if not rows or rows[0] != ["issue", "title", "dependencies"]:
    raise RelationshipSchemaError(
      "ticket CSV header must be issue,title,dependencies"
    )

  issues: dict[str, IssueRelationships] = {}
  prior = 0
  for index, row in enumerate(rows[1:], start=2):
    if len(row) != 3:
      raise RelationshipSchemaError(
        f"ticket CSV row {index} must contain exactly three fields"
      )
    raw_issue, title, raw_dependencies = row
    if not raw_issue.isdigit() or int(raw_issue) < 1:
      raise RelationshipSchemaError(
        f"ticket CSV row {index} has invalid issue number"
      )
    issue = str(int(raw_issue))
    if issue != raw_issue or int(issue) <= prior:
      raise RelationshipSchemaError(
        "ticket CSV issue numbers must be unique and strictly increasing"
      )
    prior = int(issue)
    if not title:
      raise RelationshipSchemaError(
        f"ticket CSV issue {issue} has an empty title"
      )
    dependencies = (
      []
      if raw_dependencies == ""
      else raw_dependencies.split(";")
    )
    issues[issue] = IssueRelationships(
      title=title,
      depends_on=tuple(dependencies),
    )

  return RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in issues.items()
    },
  })


def _revision(text: str) -> int:
  digest = hashlib.sha256(text.encode("utf-8")).digest()
  return int.from_bytes(digest[:8], "big")


def _writer(writer: WriterIdentity) -> None:
  if not isinstance(writer, WriterIdentity):
    raise RelationshipStoreError("writer must be a WriterIdentity")


def _lock_path(path: Path) -> Path:
  return path.with_name(f".{path.name}.lock")


def _acquire_lock(path: Path, timeout: float = 5.0) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  deadline = time.monotonic() + timeout
  while True:
    try:
      path.mkdir()
      return
    except FileExistsError:
      if time.monotonic() >= deadline:
        raise RelationshipStoreError(f"ticket-state lock is busy: {path}")
      time.sleep(0.01)


def _release_lock(path: Path) -> None:
  try:
    path.rmdir()
  except FileNotFoundError:
    pass


def _write_text_atomic(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary = tempfile.mkstemp(
    prefix=f".{path.name}.",
    suffix=".tmp",
    dir=path.parent,
  )
  temporary_path = Path(temporary)
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
      handle.write(text)
      handle.flush()
      os.fsync(handle.fileno())
    os.replace(temporary_path, path)
  finally:
    try:
      temporary_path.unlink()
    except FileNotFoundError:
      pass
