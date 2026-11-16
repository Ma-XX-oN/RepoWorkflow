from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import tempfile
import time

from .relationships import (
  IssueRelationships,
  RelationshipGraph,
  RelationshipSchemaError,
)
from .state_store import WriterIdentity


STATES = {"not_started", "active", "in_review", "accepted", "completed", "aborted"}


TICKET_STATE_PATH = Path(".repoworkflow") / "tickets.csv"


class RelationshipStoreError(RuntimeError):
  """Raised when canonical synchronized ticket state is invalid/conflicted."""


@dataclass(frozen=True)
class RelationshipSnapshot:
  graph: RelationshipGraph
  revision: int
  states: dict[str, 'TicketState']


@dataclass(frozen=True)
class TicketState:
  state: str

  def __post_init__(self) -> None:
    if self.state not in STATES:
      raise RelationshipSchemaError(f'invalid ticket state: {self.state!r}')


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

    raise RelationshipStoreError(f"record is missing: {self.path}")

  def create(
    self,
    graph: RelationshipGraph,
    writer: WriterIdentity,
  ) -> RelationshipSnapshot:
    graph = _validated_graph(graph)
    if self.path.exists():
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

  def set_state(self, issue: str | int, state: str,
                expected_revision: int) -> RelationshipSnapshot:
    """Update a ticket in the CSV, rejecting intervening CSV changes."""
    current = self.read()
    issue = str(int(issue))
    current.graph.issue(issue)
    states = dict(current.states or {})
    states[issue] = TicketState(state)
    return self._write(current.graph, expected_revision, states)

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
      return RelationshipSnapshot(graph, _revision(text), _parse_ticket_csv(text)[1])
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
        raise RelationshipStoreError(f"record is missing: {self.path}")
      if current_revision != expected_revision:
        raise RelationshipStoreError(
          "stale ticket-state revision: "
          f"expected {expected_revision}, current {current_revision}"
        )
      states = dict(states or {})
      states = {issue: states.get(issue, TicketState("not_started"))
                for issue in graph.issues}
      text = _render_csv(graph, states)
      _write_text_atomic(self.path, text)
      return RelationshipSnapshot(graph, _revision(text), states)
    finally:
      _release_lock(lock)


def _validated_graph(graph: RelationshipGraph) -> RelationshipGraph:
  if not isinstance(graph, RelationshipGraph):
    raise RelationshipStoreError("graph must be a RelationshipGraph")
  try:
    return RelationshipGraph.from_json_value(graph.to_json_value())
  except RelationshipSchemaError as error:
    raise RelationshipStoreError(str(error)) from error


def _render_csv(
  graph: RelationshipGraph,
  states: dict[str, TicketState] | None = None,
) -> str:
  graph = _validated_graph(graph)
  states = states or {}
  output = io.StringIO(newline="")
  writer = csv.writer(output, lineterminator="\n")
  writer.writerow(("issue", "title", "dependencies", "state"))
  for issue in sorted(graph.issues, key=int):
    relation = graph.issues[issue]
    row = [issue, relation.title, ";".join(relation.depends_on)]
    row.append(states.get(issue, TicketState("not_started")).state)
    writer.writerow(row)
  return output.getvalue()


def _parse_csv(text: str) -> RelationshipGraph:
  return _parse_ticket_csv(text)[0]


def _parse_ticket_csv(
  text: str,
) -> tuple[RelationshipGraph, dict[str, TicketState] | None]:
  try:
    rows = list(csv.reader(io.StringIO(text, newline="")))
  except csv.Error as error:
    raise RelationshipSchemaError(f"invalid ticket CSV: {error}") from error
  legacy = ["issue", "title", "dependencies"]
  current = legacy + ["state"]
  old_projection = current + ["state_revision"]
  if not rows or rows[0] not in (legacy, current, old_projection):
    raise RelationshipSchemaError("invalid ticket CSV header")
  has_states = rows[0] != legacy
  issues: dict[str, IssueRelationships] = {}
  states: dict[str, TicketState] = {}
  prior = 0
  for index, row in enumerate(rows[1:], start=2):
    if len(row) != len(rows[0]):
      raise RelationshipSchemaError(
        f"ticket CSV row {index} has an invalid field count"
      )
    raw_issue, title, raw_dependencies = row[:3]
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
    dependencies = [] if not raw_dependencies else raw_dependencies.split(";")
    issues[issue] = IssueRelationships(
      title=title,
      depends_on=tuple(dependencies),
    )
    if has_states:
      states[issue] = TicketState(row[3])
    else:
      states[issue] = TicketState("not_started")
  graph = RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in issues.items()
    },
  })
  return graph, states


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
