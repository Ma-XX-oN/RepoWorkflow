"""Ticket transitions stored directly in tickets.csv.

Git and the ticket provider retain history. Candidate/test evidence belongs
to the existing testing and integration records, not ticket state.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .relationship_store import RelationshipStore, RelationshipStoreError, STATES


TRANSITIONS = {
  ("not_started", "start"): "active",
  ("active", "submit-review"): "in_review",
  ("in_review", "accept"): "accepted",
  ("in_review", "reject/reopen"): "active",
  ("accepted", "reject/reopen"): "active",
  ("completed", "reject/reopen"): "active",
  ("active", "abort"): "aborted",
  ("aborted", "re-enter"): "active",
  ("accepted", "complete"): "completed",
}


class LifecycleError(RuntimeError):
  """Invalid ticket transition or conflicting CSV update."""


@dataclass(frozen=True)
class IssueLifecycle:
  issue: str
  state: str


@dataclass(frozen=True)
class LifecycleSnapshot:
  lifecycle: IssueLifecycle
  revision: int


class LifecycleStore:
  """Read/update ticket state in the existing CSV; no separate persistence."""

  def __init__(self, repository_root: Path):
    self.repository_root = Path(repository_root).resolve()
    self.tickets = RelationshipStore(self.repository_root)

  def read(self, issue: str | int) -> LifecycleSnapshot:
    issue = _issue_id(issue)
    snapshot = self.tickets.read()
    snapshot.graph.issue(issue)
    return LifecycleSnapshot(
      IssueLifecycle(issue, snapshot.states[issue].state), snapshot.revision,
    )

  def transition(self, issue: str | int, transition: str,
                 expected_revision: int) -> LifecycleSnapshot:
    current = self.read(issue)
    try:
      state = TRANSITIONS[(current.lifecycle.state, transition)]
    except KeyError as error:
      raise LifecycleError(
        f"illegal ticket transition: {current.lifecycle.state} --{transition}--> ?"
      ) from error
    try:
      updated = self.tickets.set_state(issue, state, expected_revision)
    except RelationshipStoreError as error:
      raise LifecycleError(str(error)) from error
    return LifecycleSnapshot(IssueLifecycle(str(issue), state), updated.revision)


def _issue_id(value: str | int) -> str:
  text = str(value)
  if isinstance(value, bool) or not text.isdigit() or int(text) < 1:
    raise LifecycleError(f"invalid issue id: {value!r}")
  return str(int(text))
