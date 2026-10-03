from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import git
from .lifecycle_store import LifecycleStore
from .relationship_store import RelationshipStore
from .state_store import JsonRecordStore, StateStoreError, WriterIdentity


SCHEMA_VERSION = 1
RECORD_KEY = "context"


class CurrentWorkError(RuntimeError):
  """Raised when worktree-local current-work state is invalid or stale."""


@dataclass(frozen=True)
class DurableReference:
  issue: str
  lifecycle_revision: int
  relationship_revision: int

  def to_json_value(self) -> dict:
    return {
      "issue": self.issue,
      "lifecycle_revision": self.lifecycle_revision,
      "relationship_revision": self.relationship_revision,
    }


@dataclass(frozen=True)
class CurrentWork:
  current: DurableReference | None
  resume: DurableReference | None
  selected_issue: str | None
  cache_lifecycle_revision: int | None
  cache_relationship_revision: int | None
  schema_version: int = SCHEMA_VERSION

  @classmethod
  def empty(cls) -> "CurrentWork":
    return cls(None, None, None, None, None)

  @classmethod
  def from_json_value(cls, value: dict) -> "CurrentWork":
    if not isinstance(value, dict):
      raise CurrentWorkError("current-work value must be an object")
    expected = {
      "schema_version",
      "current",
      "resume",
      "selected_issue",
      "cache_sources",
    }
    if set(value) != expected:
      raise CurrentWorkError("current-work value has missing/unsupported fields")
    if value["schema_version"] != SCHEMA_VERSION:
      raise CurrentWorkError(
        f"unsupported current-work schema version: {value['schema_version']!r}"
      )
    selected = value["selected_issue"]
    if selected is not None:
      selected = _issue_id(selected)
    cache = value["cache_sources"]
    if cache is None:
      cache_lifecycle = None
      cache_relationship = None
    else:
      if not isinstance(cache, dict) or set(cache) != {
        "lifecycle_revision",
        "relationship_revision",
      }:
        raise CurrentWorkError("cache_sources has missing/unsupported fields")
      cache_lifecycle = _revision(cache["lifecycle_revision"])
      cache_relationship = _revision(cache["relationship_revision"])
    return cls(
      current=_reference(value["current"]),
      resume=_reference(value["resume"]),
      selected_issue=selected,
      cache_lifecycle_revision=cache_lifecycle,
      cache_relationship_revision=cache_relationship,
    )

  def to_json_value(self) -> dict:
    cache = None
    if self.cache_lifecycle_revision is not None:
      if self.cache_relationship_revision is None:
        raise CurrentWorkError("cache source revisions must be complete")
      cache = {
        "lifecycle_revision": self.cache_lifecycle_revision,
        "relationship_revision": self.cache_relationship_revision,
      }
    elif self.cache_relationship_revision is not None:
      raise CurrentWorkError("cache source revisions must be complete")
    return {
      "schema_version": self.schema_version,
      "current": None if self.current is None else self.current.to_json_value(),
      "resume": None if self.resume is None else self.resume.to_json_value(),
      "selected_issue": self.selected_issue,
      "cache_sources": cache,
    }


@dataclass(frozen=True)
class CurrentWorkSnapshot:
  value: CurrentWork
  revision: int | None


class CurrentWorkStore:
  """Worktree-local current-work state with durable-reference validation."""

  def __init__(self, repository_root: Path):
    self.repository_root = Path(repository_root).resolve()
    git_dir = Path(
      git(self.repository_root, "rev-parse", "--git-dir").stdout.strip()
    )
    if not git_dir.is_absolute():
      git_dir = (self.repository_root / git_dir).resolve()
    self.records = JsonRecordStore(git_dir / "repoworkflow" / "current-work")

  def read(self, *, validate_durable: bool = False) -> CurrentWorkSnapshot:
    try:
      record = self.records.read(RECORD_KEY)
    except StateStoreError as error:
      if "record is missing:" in str(error):
        return CurrentWorkSnapshot(CurrentWork.empty(), None)
      raise CurrentWorkError(str(error)) from error
    try:
      value = CurrentWork.from_json_value(record["value"])
    except CurrentWorkError:
      raise
    snapshot = CurrentWorkSnapshot(value, record["revision"])
    if validate_durable:
      self._validate_durable(snapshot.value)
    return snapshot

  def replace(
    self,
    expected_revision: int | None,
    value: CurrentWork,
    writer: WriterIdentity,
  ) -> CurrentWorkSnapshot:
    value = CurrentWork.from_json_value(value.to_json_value())
    current = self.read()
    if current.revision != expected_revision:
      raise CurrentWorkError(
        f"stale current-work revision: expected {expected_revision!r}, "
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
      raise CurrentWorkError(str(error)) from error
    return CurrentWorkSnapshot(value, record["revision"])

  def project_start(
    self,
    issue: str | int,
    lifecycle_revision: int,
    relationship_revision: int,
    writer: WriterIdentity,
    expected_revision: int | None,
  ) -> CurrentWorkSnapshot:
    reference = DurableReference(
      _issue_id(issue),
      _revision(lifecycle_revision),
      _revision(relationship_revision),
    )
    value = CurrentWork(
      current=reference,
      resume=None,
      selected_issue=reference.issue,
      cache_lifecycle_revision=reference.lifecycle_revision,
      cache_relationship_revision=reference.relationship_revision,
    )
    return self.replace(expected_revision, value, writer)

  def project_abort(
    self,
    issue: str | int,
    lifecycle_revision: int,
    relationship_revision: int,
    writer: WriterIdentity,
    expected_revision: int,
  ) -> CurrentWorkSnapshot:
    current = self.read()
    issue_id = _issue_id(issue)
    if current.revision != expected_revision:
      raise CurrentWorkError(
        f"stale current-work revision: expected {expected_revision!r}, "
        f"current {current.revision!r}"
      )
    if current.value.current is None or current.value.current.issue != issue_id:
      raise CurrentWorkError(f"issue {issue_id} is not current in this worktree")
    reference = DurableReference(
      issue_id,
      _revision(lifecycle_revision),
      _revision(relationship_revision),
    )
    value = CurrentWork(
      current=None,
      resume=reference,
      selected_issue=issue_id,
      cache_lifecycle_revision=reference.lifecycle_revision,
      cache_relationship_revision=reference.relationship_revision,
    )
    return self.replace(expected_revision, value, writer)

  def _validate_durable(self, value: CurrentWork) -> None:
    relationship_revision = RelationshipStore(
      self.repository_root
    ).read().revision
    for name, reference in (
      ("current", value.current),
      ("resume", value.resume),
    ):
      if reference is None:
        continue
      lifecycle_revision = LifecycleStore(
        self.repository_root
      ).read(reference.issue).revision
      if lifecycle_revision != reference.lifecycle_revision:
        raise CurrentWorkError(
          f"stale {name} lifecycle revision for issue {reference.issue}: "
          f"expected {reference.lifecycle_revision}, "
          f"current {lifecycle_revision!r}"
        )
      if relationship_revision != reference.relationship_revision:
        raise CurrentWorkError(
          f"stale {name} relationship revision: "
          f"expected {reference.relationship_revision}, "
          f"current {relationship_revision}"
        )


def _reference(value) -> DurableReference | None:
  if value is None:
    return None
  if not isinstance(value, dict) or set(value) != {
    "issue",
    "lifecycle_revision",
    "relationship_revision",
  }:
    raise CurrentWorkError("durable reference has missing/unsupported fields")
  return DurableReference(
    _issue_id(value["issue"]),
    _revision(value["lifecycle_revision"]),
    _revision(value["relationship_revision"]),
  )


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise CurrentWorkError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1 or text != str(int(text)):
    raise CurrentWorkError(f"invalid issue id: {value!r}")
  return text


def _revision(value: int) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    raise CurrentWorkError("durable revision must be non-negative")
  return value
