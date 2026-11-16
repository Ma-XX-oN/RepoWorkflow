"""Worktree-local issue selection; ticket state lives in tickets.csv."""
from dataclasses import dataclass
from pathlib import Path

from .git import git
from .relationship_store import RelationshipStore
from .state_store import JsonRecordStore, StateStoreError, WriterIdentity


RECORD_KEY = "context"


class CurrentWorkError(RuntimeError):
  pass


@dataclass(frozen=True)
class DurableReference:
  issue: str

  def to_json_value(self):
    return {"issue": self.issue}


@dataclass(frozen=True)
class CurrentWork:
  current: DurableReference | None
  resume: DurableReference | None
  selected_issue: str | None

  @classmethod
  def empty(cls):
    return cls(None, None, None)

  @classmethod
  def from_json_value(cls, value):
    if not isinstance(value, dict):
      raise CurrentWorkError("current-work value must be an object")
    return cls(_reference(value["current"]), _reference(value["resume"]),
               None if value["selected_issue"] is None else _issue_id(value["selected_issue"]))

  def to_json_value(self):
    return {"current": None if self.current is None else self.current.to_json_value(),
            "resume": None if self.resume is None else self.resume.to_json_value(),
            "selected_issue": self.selected_issue}


@dataclass(frozen=True)
class CurrentWorkSnapshot:
  value: CurrentWork
  revision: int | None


class CurrentWorkStore:
  def __init__(self, repository_root: Path):
    self.repository_root = Path(repository_root).resolve()
    git_dir = Path(git(self.repository_root, "rev-parse", "--git-dir").stdout.strip())
    if not git_dir.is_absolute():
      git_dir = self.repository_root / git_dir
    self.records = JsonRecordStore(git_dir / "repoworkflow" / "current-work")

  def read(self, *, validate_durable=False):
    try:
      record = self.records.read(RECORD_KEY)
    except StateStoreError as error:
      if "record is missing:" in str(error):
        return CurrentWorkSnapshot(CurrentWork.empty(), None)
      raise CurrentWorkError(str(error)) from error
    value = CurrentWork.from_json_value(record["value"])
    if validate_durable:
      tickets = RelationshipStore(self.repository_root).read()
      for reference in (value.current, value.resume):
        if reference is not None:
          tickets.graph.issue(reference.issue)
    return CurrentWorkSnapshot(value, record["revision"])

  def replace(self, expected_revision, value, writer):
    try:
      if expected_revision is None:
        record = self.records.create(RECORD_KEY, value.to_json_value(), writer)
      else:
        record = self.records.replace(RECORD_KEY, expected_revision,
                                      value.to_json_value(), writer)
    except StateStoreError as error:
      raise CurrentWorkError(str(error)) from error
    return CurrentWorkSnapshot(value, record["revision"])

  def project_start(self, issue, writer, expected_revision):
    reference = DurableReference(_issue_id(issue))
    return self.replace(expected_revision,
                        CurrentWork(reference, None, reference.issue), writer)

  def project_abort(self, issue, writer, expected_revision):
    current = self.read()
    reference = DurableReference(_issue_id(issue))
    if current.value.current != reference:
      raise CurrentWorkError(f"issue {issue} is not current in this worktree")
    return self.replace(expected_revision,
                        CurrentWork(None, reference, reference.issue), writer)


def _reference(value):
  return None if value is None else DurableReference(_issue_id(value["issue"]))


def _issue_id(value):
  text = str(value)
  if isinstance(value, bool) or not text.isdigit() or int(text) < 1:
    raise CurrentWorkError(f"invalid issue id: {value!r}")
  return str(int(text))
