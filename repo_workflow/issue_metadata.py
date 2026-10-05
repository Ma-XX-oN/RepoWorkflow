from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .relationship_store import RelationshipStore
from .repo_info_adapter import RepoInfoError, issue_info
from .state_store import StateStoreError, WriterIdentity, durable_store


METADATA_KEY = "issues/metadata"
SCHEMA_VERSION = 2


class IssueMetadataError(RuntimeError):
  """Raised when synchronized durable issue metadata is unavailable or invalid."""


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
  revision: int


class IssueMetadataStore:
  """Provider-neutral durable issue metadata snapshot and offline reader."""

  def __init__(self, repository_root: Path):
    self.root = Path(repository_root).resolve()
    self.records = durable_store(self.root)

  def read(self) -> IssueMetadataSnapshot:
    try:
      record = self.records.read(METADATA_KEY)
      issues = _parse_snapshot(record["value"])
    except (StateStoreError, ValueError) as error:
      raise IssueMetadataError(str(error)) from error
    return IssueMetadataSnapshot(issues=issues, revision=record["revision"])

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
        "refresh issue metadata before lane inspection"
      )
    return metadata

  def write(
    self,
    issues: dict[int, IssueMetadata],
    writer: WriterIdentity,
  ) -> IssueMetadataSnapshot:
    value = _snapshot_value(issues)
    path = self.root / ".repoworkflow" / "state" / "issues" / "metadata.json"
    try:
      if path.exists():
        current = self.records.read(METADATA_KEY)
        record = self.records.replace(
          METADATA_KEY,
          current["revision"],
          value,
          writer,
        )
      else:
        record = self.records.create(METADATA_KEY, value, writer)
    except StateStoreError as error:
      raise IssueMetadataError(str(error)) from error
    return IssueMetadataSnapshot(
      issues=_parse_snapshot(record["value"]),
      revision=record["revision"],
    )


def refresh_issue_metadata(
  repository_root: Path,
  config: dict,
  writer: WriterIdentity,
  issue_numbers: tuple[int, ...] | None = None,
  provider_call: Callable[[int, Callable[[], dict]], dict] | None = None,
) -> IssueMetadataSnapshot:
  """Refresh complete graph metadata or one declared issue scope atomically."""
  root = Path(repository_root).resolve()
  graph = RelationshipStore(root).read().graph

  if issue_numbers is None:
    scope = tuple(int(issue_id) for issue_id in sorted(graph.issues, key=int))
    base: dict[int, IssueMetadata] = {}
  else:
    scope = tuple(sorted({_positive_integer(value, "issue number") for value in issue_numbers}))
    unknown = [number for number in scope if str(number) not in graph.issues]
    if unknown:
      raise IssueMetadataError(
        "cannot refresh metadata outside canonical relationship graph: "
        + ", ".join(str(number) for number in unknown)
      )
    try:
      base = dict(IssueMetadataStore(root).read().issues)
    except IssueMetadataError as error:
      if "record is missing:" in str(error):
        base = {}
      else:
        raise

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

  base.update(refreshed)
  return IssueMetadataStore(root).write(base, writer)


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
  if state not in {"open", "closed"}:
    raise ValueError(f"provider issue {number} has invalid state")
  link = value.get("link")
  if not isinstance(link, str) or not link:
    raise ValueError(f"provider issue {number} has empty link")
  return IssueMetadata(number=number, title=title, state=state, link=link)


def _parse_snapshot(value: dict) -> dict[int, IssueMetadata]:
  if not isinstance(value, dict) or set(value) != {"schema_version", "issues"}:
    raise ValueError("issue metadata snapshot has unsupported fields")
  version = value["schema_version"]
  if version not in {1, SCHEMA_VERSION}:
    raise ValueError("unsupported issue metadata schema version")
  raw_issues = value["issues"]
  if not isinstance(raw_issues, dict):
    raise ValueError("issue metadata issues must be an object")

  issues: dict[int, IssueMetadata] = {}
  for raw_key, raw in raw_issues.items():
    if not isinstance(raw_key, str) or not raw_key.isdigit():
      raise ValueError("issue metadata key must be a positive decimal integer")
    number = _positive_integer(int(raw_key), "issue metadata key")
    if raw_key != str(number):
      raise ValueError("issue metadata key must be canonical decimal text")
    required = {"number", "title"} if version == 1 else {"number", "title", "state", "link"}
    if not isinstance(raw, dict) or set(raw) != required:
      raise ValueError(f"issue metadata record {number} has unsupported fields")
    returned = _positive_integer(raw["number"], "issue metadata number")
    if returned != number:
      raise ValueError(f"issue metadata record {number} has mismatched number")
    title = raw["title"]
    if not isinstance(title, str) or not title:
      raise ValueError(f"issue metadata record {number} has empty title")
    if version == 1:
      issues[number] = IssueMetadata(number=number, title=title)
      continue
    state = raw["state"]
    if state not in {"open", "closed"}:
      raise ValueError(f"issue metadata record {number} has invalid state")
    link = raw["link"]
    if not isinstance(link, str) or not link:
      raise ValueError(f"issue metadata record {number} has empty link")
    issues[number] = IssueMetadata(
      number=number,
      title=title,
      state=state,
      link=link,
    )
  return issues


def _snapshot_value(issues: dict[int, IssueMetadata]) -> dict:
  normalized: dict[int, IssueMetadata] = {}
  for key, metadata in issues.items():
    number = _positive_integer(key, "issue metadata key")
    if not isinstance(metadata, IssueMetadata) or metadata.number != number:
      raise IssueMetadataError(f"invalid issue metadata record for issue {number}")
    if not isinstance(metadata.title, str) or not metadata.title:
      raise IssueMetadataError(f"issue metadata title is empty for issue {number}")
    if metadata.state not in {"open", "closed"}:
      raise IssueMetadataError(f"issue metadata state is incomplete for issue {number}")
    if not isinstance(metadata.link, str) or not metadata.link:
      raise IssueMetadataError(f"issue metadata link is incomplete for issue {number}")
    normalized[number] = metadata
  return {
    "schema_version": SCHEMA_VERSION,
    "issues": {
      str(number): {
        "number": number,
        "title": normalized[number].title,
        "state": normalized[number].state,
        "link": normalized[number].link,
      }
      for number in sorted(normalized)
    },
  }


def _positive_integer(value, label: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise ValueError(f"{label} must be a positive integer")
  return value
