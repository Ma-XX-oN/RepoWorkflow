from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import git
from .state_store import (
  JsonRecordStore,
  StateStoreError,
  WriterIdentity,
  durable_store,
)


SCHEMA_VERSION = 2
STATES = {"unstarted", "active", "aborted", "accepted", "completed"}
TRANSITIONS = {
  ("unstarted", "start"): "active",
  ("active", "abort"): "aborted",
  ("aborted", "re-enter"): "active",
  ("active", "accept"): "accepted",
  ("accepted", "reject/reopen"): "active",
  ("accepted", "complete"): "completed",
}


class LifecycleError(RuntimeError):
  """Raised when durable issue lifecycle state is invalid or conflicted."""


@dataclass(frozen=True)
class LifecycleEvent:
  sequence: int
  transition: str
  from_state: str
  to_state: str
  candidate: str | None

  def to_json_value(self) -> dict:
    return {
      "sequence": self.sequence,
      "transition": self.transition,
      "from": self.from_state,
      "to": self.to_state,
      "candidate": self.candidate,
    }


@dataclass(frozen=True)
class IssueLifecycle:
  issue: str
  state: str
  dependency_satisfied: bool
  relationship_revision: int | None
  history: tuple[LifecycleEvent, ...]
  high_risk_aliases: tuple[str, ...] = ()
  schema_version: int = SCHEMA_VERSION

  @classmethod
  def unstarted(cls, issue: str | int) -> "IssueLifecycle":
    return cls(
      issue=_issue_id(issue),
      state="unstarted",
      dependency_satisfied=False,
      relationship_revision=None,
      history=(),
      high_risk_aliases=(),
    )

  @classmethod
  def from_json_value(cls, value: dict) -> "IssueLifecycle":
    if not isinstance(value, dict):
      raise LifecycleError("lifecycle value must be an object")
    version = value.get("schema_version")
    if version not in {1, SCHEMA_VERSION}:
      raise LifecycleError(
        f"unsupported lifecycle schema version: {version!r}"
      )
    expected = {
      "schema_version",
      "issue",
      "state",
      "dependency_satisfied",
      "relationship_revision",
      "history",
    }
    if version == SCHEMA_VERSION:
      expected.add("high_risk_aliases")
    if set(value) != expected:
      raise LifecycleError("lifecycle value has missing or unsupported fields")
    issue = _issue_id(value["issue"])
    state = value["state"]
    if state not in STATES:
      raise LifecycleError(f"unsupported lifecycle state: {state!r}")
    satisfied = value["dependency_satisfied"]
    if not isinstance(satisfied, bool):
      raise LifecycleError("dependency_satisfied must be Boolean")
    if satisfied != (state == "completed"):
      raise LifecycleError(
        "dependency_satisfied must be true exactly for completed state"
      )
    relationship_revision = _optional_revision(value["relationship_revision"])
    raw_history = value["history"]
    if not isinstance(raw_history, list):
      raise LifecycleError("history must be an array")
    history = tuple(
      _event(raw, sequence)
      for sequence, raw in enumerate(raw_history)
    )
    _validate_history(state, history)
    aliases = () if version == 1 else _aliases(value["high_risk_aliases"])
    return cls(
      issue=issue,
      state=state,
      dependency_satisfied=satisfied,
      relationship_revision=relationship_revision,
      history=history,
      high_risk_aliases=aliases,
    )

  def to_json_value(self) -> dict:
    return {
      "schema_version": self.schema_version,
      "issue": self.issue,
      "state": self.state,
      "dependency_satisfied": self.dependency_satisfied,
      "relationship_revision": self.relationship_revision,
      "history": [event.to_json_value() for event in self.history],
      "high_risk_aliases": list(self.high_risk_aliases),
    }


@dataclass(frozen=True)
class LifecycleSnapshot:
  lifecycle: IssueLifecycle
  revision: int | None


class LifecycleStore:
  """Canonical durable issue lifecycle storage and normalized reader."""

  def __init__(self, repository_root: Path):
    self.repository_root = Path(repository_root).resolve()
    self.records = durable_store(self.repository_root)

  def read(self, issue: str | int) -> LifecycleSnapshot:
    issue_id = _issue_id(issue)
    key = _key(issue_id)
    try:
      record = self.records.read(key)
    except StateStoreError as error:
      if "record is missing:" not in str(error):
        raise LifecycleError(str(error)) from error
      if self._existed_in_history(key):
        raise LifecycleError(
          f"lifecycle record for issue {issue_id} is missing but exists in "
          "repository history"
        ) from error
      return LifecycleSnapshot(IssueLifecycle.unstarted(issue_id), None)

    try:
      lifecycle = IssueLifecycle.from_json_value(record["value"])
    except LifecycleError:
      raise
    if lifecycle.issue != issue_id:
      raise LifecycleError(
        f"lifecycle record issue mismatch: expected {issue_id}, "
        f"found {lifecycle.issue}"
      )
    return LifecycleSnapshot(lifecycle, record["revision"])

  def transition(
    self,
    issue: str | int,
    transition: str,
    candidate: str | None,
    relationship_revision: int | None,
    writer: WriterIdentity,
    expected_revision: int | None,
  ) -> LifecycleSnapshot:
    current = self.read(issue)
    if current.revision != expected_revision:
      raise LifecycleError(
        f"stale lifecycle revision for issue {current.lifecycle.issue}: "
        f"expected {expected_revision!r}, current {current.revision!r}"
      )
    key = (current.lifecycle.state, transition)
    try:
      next_state = TRANSITIONS[key]
    except KeyError as error:
      raise LifecycleError(
        f"illegal lifecycle transition: {current.lifecycle.state} "
        f"--{transition}--> ?"
      ) from error

    relationship_revision = _optional_revision(relationship_revision)
    candidate = _optional_text(candidate, "candidate")
    event = LifecycleEvent(
      sequence=len(current.lifecycle.history),
      transition=transition,
      from_state=current.lifecycle.state,
      to_state=next_state,
      candidate=candidate,
    )
    successor = IssueLifecycle(
      issue=current.lifecycle.issue,
      state=next_state,
      dependency_satisfied=next_state == "completed",
      relationship_revision=relationship_revision,
      history=current.lifecycle.history + (event,),
      high_risk_aliases=current.lifecycle.high_risk_aliases,
    )
    try:
      if current.revision is None:
        record = self.records.create(
          _key(current.lifecycle.issue),
          successor.to_json_value(),
          writer,
        )
      else:
        record = self.records.replace(
          _key(current.lifecycle.issue),
          current.revision,
          successor.to_json_value(),
          writer,
        )
    except StateStoreError as error:
      raise LifecycleError(str(error)) from error
    return LifecycleSnapshot(successor, record["revision"])

  def set_high_risk_aliases(
    self,
    issue: str | int,
    aliases: tuple[str, ...] | list[str],
    writer: WriterIdentity,
    expected_revision: int | None,
  ) -> LifecycleSnapshot:
    current = self.read(issue)
    if current.revision != expected_revision:
      raise LifecycleError(
        f"stale lifecycle revision for issue {current.lifecycle.issue}: "
        f"expected {expected_revision!r}, current {current.revision!r}"
      )
    normalized = _aliases(aliases)
    successor = IssueLifecycle(
      issue=current.lifecycle.issue,
      state=current.lifecycle.state,
      dependency_satisfied=current.lifecycle.dependency_satisfied,
      relationship_revision=current.lifecycle.relationship_revision,
      history=current.lifecycle.history,
      high_risk_aliases=normalized,
    )
    try:
      if current.revision is None:
        record = self.records.create(
          _key(current.lifecycle.issue),
          successor.to_json_value(),
          writer,
        )
      else:
        record = self.records.replace(
          _key(current.lifecycle.issue),
          current.revision,
          successor.to_json_value(),
          writer,
        )
    except StateStoreError as error:
      raise LifecycleError(str(error)) from error
    return LifecycleSnapshot(successor, record["revision"])

  def _existed_in_history(self, key: str) -> bool:
    relative = f".repoworkflow/state/{key}.json"
    result = git(
      self.repository_root,
      "log",
      "--all",
      "--format=%H",
      "--",
      relative,
      check=False,
    )
    if result.returncode:
      raise LifecycleError(
        f"cannot establish lifecycle history for {relative}: "
        f"{(result.stderr or result.stdout).strip()}"
      )
    return bool(result.stdout.strip())


def _key(issue: str) -> str:
  return f"issues/{issue}/lifecycle"


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise LifecycleError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1 or text != str(int(text)):
    raise LifecycleError(f"invalid issue id: {value!r}")
  return text


def _aliases(value) -> tuple[str, ...]:
  if not isinstance(value, (list, tuple)):
    raise LifecycleError("high_risk_aliases must be an array")
  result: list[str] = []
  seen: set[str] = set()
  for item in value:
    if not isinstance(item, str) or not item.strip() or item != item.strip():
      raise LifecycleError("high_risk_aliases must contain non-empty names")
    if item not in seen:
      seen.add(item)
      result.append(item)
  return tuple(sorted(result))


def _optional_revision(value: int | None) -> int | None:
  if value is None:
    return None
  if isinstance(value, bool) or not isinstance(value, int) or value < 0:
    raise LifecycleError("relationship_revision must be non-negative or null")
  return value


def _optional_text(value: str | None, field: str) -> str | None:
  if value is None:
    return None
  if not isinstance(value, str) or not value.strip():
    raise LifecycleError(f"{field} must be non-empty text or null")
  return value


def _event(value: dict, expected_sequence: int) -> LifecycleEvent:
  if not isinstance(value, dict):
    raise LifecycleError("history event must be an object")
  if set(value) != {"sequence", "transition", "from", "to", "candidate"}:
    raise LifecycleError("history event has missing or unsupported fields")
  if value["sequence"] != expected_sequence:
    raise LifecycleError("history sequence is not contiguous")
  transition = value["transition"]
  from_state = value["from"]
  to_state = value["to"]
  if not isinstance(transition, str):
    raise LifecycleError("history transition must be text")
  if TRANSITIONS.get((from_state, transition)) != to_state:
    raise LifecycleError("history contains an illegal lifecycle transition")
  return LifecycleEvent(
    sequence=expected_sequence,
    transition=transition,
    from_state=from_state,
    to_state=to_state,
    candidate=_optional_text(value["candidate"], "candidate"),
  )


def _validate_history(
  state: str,
  history: tuple[LifecycleEvent, ...],
) -> None:
  current = "unstarted"
  for event in history:
    if event.from_state != current:
      raise LifecycleError("history state chain is not contiguous")
    current = event.to_state
  if current != state:
    raise LifecycleError(
      f"history ends in {current!r}, lifecycle state is {state!r}"
    )
