from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .relationship_store import RelationshipStore
from .relationships import IssueRelationships, RelationshipGraph
from .repo_info_adapter import RepoInfoError, issue_info
from .state_store import StateStoreError, WriterIdentity, durable_store


METADATA_KEY = "issues/metadata"
SCHEMA_VERSION = 3


class IssueMetadataError(RuntimeError):
  """Raised when synchronized issue display metadata is invalid."""


@dataclass(frozen=True)
class IssueMetadata:
  number: int
  title: str
  state: str | None = None
  link: str | None = None

  @property
  def display_complete(self) -> bool:
    return self.state in {"open", "closed"} and bool(self.link)


@dataclass(frozen=True)
class IssueMetadataSnapshot:
  issues: dict[int, IssueMetadata]
  revision: int | None


class IssueMetadataStore:
  """Display metadata layered over canonical title/dependency ticket state."""

  def __init__(self, repository_root: Path):
    self.root = Path(repository_root).resolve()
    self.records = durable_store(self.root)

  def read(self) -> IssueMetadataSnapshot:
    graph = RelationshipStore(self.root).read().graph
    try:
      record = self.records.read(METADATA_KEY)
      display = _parse_display_snapshot(record["value"])
      revision = record["revision"]
    except StateStoreError as error:
      if "record is missing:" not in str(error):
        raise IssueMetadataError(str(error)) from error
      display = {}
      revision = None
    except ValueError as error:
      raise IssueMetadataError(str(error)) from error

    issues = {
      int(issue): IssueMetadata(
        number=int(issue),
        title=relation.title,
        state=display.get(int(issue), (None, None))[0],
        link=display.get(int(issue), (None, None))[1],
      )
      for issue, relation in graph.issues.items()
    }
    return IssueMetadataSnapshot(issues=issues, revision=revision)

  def issue(self, issue_number: int) -> IssueMetadata:
    number = _positive_integer(issue_number, "issue number")
    snapshot = self.read()
    try:
      return snapshot.issues[number]
    except KeyError as error:
      raise IssueMetadataError(
        f"synchronized issue metadata is missing for issue {number}"
      ) from error

  def display_issue(self, issue_number: int) -> IssueMetadata:
    metadata = self.issue(issue_number)
    if not metadata.display_complete:
      raise IssueMetadataError(
        f"synchronized display metadata is incomplete for issue {metadata.number}; "
        "refresh issue metadata before requesting links/state"
      )
    return metadata

  def write(
    self,
    issues: dict[int, IssueMetadata],
    writer: WriterIdentity,
  ) -> IssueMetadataSnapshot:
    store = RelationshipStore(self.root)
    snapshot = store.read()
    relations = dict(snapshot.graph.issues)
    display: dict[int, tuple[str | None, str | None]] = {}
    for number, metadata in issues.items():
      number = _positive_integer(number, "issue metadata key")
      relation = relations.get(str(number))
      if relation is None:
        raise IssueMetadataError(
          f"cannot store display metadata outside canonical ticket state: {number}"
        )
      if not isinstance(metadata.title, str) or not metadata.title:
        raise IssueMetadataError(
          f"issue metadata title is empty for issue {number}"
        )
      _validate_display(metadata.state, metadata.link, number)
      relations[str(number)] = IssueRelationships(
        title=metadata.title,
        depends_on=relation.depends_on,
      )
      display[number] = (metadata.state, metadata.link)

    graph = RelationshipGraph.from_json_value({
      "schema_version": 3,
      "issues": {
        issue: relation.to_json_value()
        for issue, relation in relations.items()
      },
    })
    if graph != snapshot.graph:
      store.replace(snapshot.revision, graph, writer)
    self._write_display(display, writer)
    return self.read()

  def _write_display(
    self,
    display: dict[int, tuple[str | None, str | None]],
    writer: WriterIdentity,
  ) -> dict:
    value = {
      "schema_version": SCHEMA_VERSION,
      "issues": {
        str(number): {
          "number": number,
          "state": display[number][0],
          "link": display[number][1],
        }
        for number in sorted(display)
      },
    }
    try:
      try:
        current = self.records.read(METADATA_KEY)
      except StateStoreError as error:
        if "record is missing:" not in str(error):
          raise
        return self.records.create(METADATA_KEY, value, writer)
      return self.records.replace(
        METADATA_KEY,
        current["revision"],
        value,
        writer,
      )
    except StateStoreError as error:
      raise IssueMetadataError(str(error)) from error


def refresh_issue_metadata(
  repository_root: Path,
  config: dict,
  writer: WriterIdentity,
  issue_numbers: tuple[int, ...] | None = None,
  provider_call: Callable[[int, Callable[[], dict]], dict] | None = None,
) -> IssueMetadataSnapshot:
  """Refresh server-authoritative titles plus optional display state/link."""
  root = Path(repository_root).resolve()
  relationship_store = RelationshipStore(root)
  snapshot = relationship_store.read()
  graph = snapshot.graph

  if issue_numbers is None:
    scope = tuple(int(issue_id) for issue_id in sorted(graph.issues, key=int))
  else:
    scope = tuple(sorted({
      _positive_integer(value, "issue number")
      for value in issue_numbers
    }))
    unknown = [number for number in scope if str(number) not in graph.issues]
    if unknown:
      raise IssueMetadataError(
        "cannot refresh metadata outside canonical ticket state: "
        + ", ".join(str(number) for number in unknown)
      )

  refreshed: dict[int, IssueMetadata] = {}
  try:
    for number in scope:
      call = lambda number=number: issue_info(root, config, number)
      value = call() if provider_call is None else provider_call(number, call)
      refreshed[number] = _metadata_from_provider(number, value)
  except (RepoInfoError, ValueError) as error:
    raise IssueMetadataError(
      f"issue metadata refresh failed: {error}"
    ) from error

  current_metadata = IssueMetadataStore(root).read()
  updated_relations = dict(graph.issues)
  for number, metadata in refreshed.items():
    current = updated_relations[str(number)]
    updated_relations[str(number)] = IssueRelationships(
      title=metadata.title,
      depends_on=current.depends_on,
    )

  replacement = RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in updated_relations.items()
    },
  })

  changed_titles = replacement != graph
  if changed_titles:
    updated_relationships = relationship_store.replace(
      snapshot.revision,
      replacement,
      writer,
    )
  else:
    updated_relationships = snapshot

  display = {
    number: (metadata.state, metadata.link)
    for number, metadata in current_metadata.issues.items()
    if metadata.display_complete
  }
  display.update({
    number: (metadata.state, metadata.link)
    for number, metadata in refreshed.items()
  })

  try:
    IssueMetadataStore(root)._write_display(display, writer)
  except Exception:
    if changed_titles:
      try:
        relationship_store.replace(
          updated_relationships.revision,
          graph,
          writer,
        )
      except Exception as rollback:
        raise IssueMetadataError(
          "display metadata refresh failed and canonical title rollback failed: "
          f"{rollback}"
        )
    raise

  return IssueMetadataStore(root).read()


def _metadata_from_provider(number: int, value: dict) -> IssueMetadata:
  returned = _positive_integer(value.get("number"), "provider issue number")
  if returned != number:
    raise ValueError(
      f"provider issue number mismatch: requested {number}, returned {returned}"
    )
  title = value.get("title")
  if not isinstance(title, str) or not title:
    raise ValueError(f"provider issue {number} has empty title")
  state = value.get("state")
  link = value.get("link")
  _validate_display(state, link, number)
  return IssueMetadata(number=number, title=title, state=state, link=link)


def _parse_display_snapshot(
  value: dict,
) -> dict[int, tuple[str | None, str | None]]:
  if not isinstance(value, dict):
    raise ValueError("issue metadata snapshot must be an object")
  version = value.get("schema_version")
  if version not in {1, 2, SCHEMA_VERSION}:
    raise ValueError("unsupported issue metadata schema version")
  raw_issues = value.get("issues")
  if not isinstance(raw_issues, dict):
    raise ValueError("issue metadata issues must be an object")

  result: dict[int, tuple[str | None, str | None]] = {}
  for raw_key, raw in raw_issues.items():
    if not isinstance(raw_key, str) or not raw_key.isdigit():
      raise ValueError("issue metadata key must be a positive decimal integer")
    number = _positive_integer(int(raw_key), "issue metadata key")
    if raw_key != str(number) or not isinstance(raw, dict):
      raise ValueError(f"issue metadata record {number} is invalid")
    if version == 1:
      result[number] = (None, None)
      continue
    state = raw.get("state")
    link = raw.get("link")
    _validate_display(state, link, number)
    result[number] = (state, link)
  return result


def _validate_display(
  state: str | None,
  link: str | None,
  number: int,
) -> None:
  if state is None and link is None:
    return
  if state not in {"open", "closed"}:
    raise ValueError(f"provider issue {number} has invalid state")
  if not isinstance(link, str) or not link:
    raise ValueError(f"provider issue {number} has empty link")


def _positive_integer(value, label: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise ValueError(f"{label} must be a positive integer")
  return value
