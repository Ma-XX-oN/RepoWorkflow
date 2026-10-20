"""#109 to #583 lifecycle acceptance, only after immutable provider landing.

Review acceptance must already be in the authoritative lifecycle store.
This adapter cannot create an acceptance or turn a simulated test into PASS.
"""
from .done_evidence_promotion import Promotion
from .done_terminal_v2 import IntegratedTerminal
from .lifecycle_store import LifecycleSnapshot, LifecycleStore
from typing import Protocol, runtime_checkable
from .state_store import WriterIdentity


@runtime_checkable
class RefRetirement(Protocol):
  ref: str
  previously_observed_sha: str
  absent_after: bool


class CompletionHandoffError(RuntimeError):
  """Provider landing cannot be safely committed to lifecycle history."""


def complete_after_provider(
    *, store: LifecycleStore, issue: int, expected_revision: int,
    relationship_revision: int, writer: WriterIdentity,
    terminal: IntegratedTerminal, promotions: Promotion,
    retirements: tuple[RefRetirement, RefRetirement],
    reread_terminal, reread_promotion,
):
  """Advance only accepted -> completed under durable lifecycle revision CAS."""
  if (type(issue) is not int or issue <= 0
      or type(expected_revision) is not int or expected_revision < 0
      or type(relationship_revision) is not int
      or relationship_revision < 0
      or not isinstance(writer, WriterIdentity)
      or not isinstance(terminal, IntegratedTerminal)
      or not isinstance(promotions, Promotion)
      or not isinstance(retirements, tuple) or len(retirements) != 2
      or not all(isinstance(r, RefRetirement) for r in retirements)
      or not callable(reread_terminal) or not callable(reread_promotion)
      or not callable(getattr(store, "transition", None))
      or not callable(getattr(store, "read", None))):
    raise CompletionHandoffError("complete review and provider proof required")
  if (terminal.accepted_sha != promotions.accepted_candidate_sha
      or terminal.landed_sha != promotions.landed_sha
      or promotions.operation_id != terminal.operation_id
      or terminal.record.get("status") != "integrated"
      or terminal.record.get("guid") != terminal.guid):
    raise CompletionHandoffError("provider landed and promoted SHA mismatch")
  expected={
    terminal.record.get("prelim_ref"):terminal.record.get("prelim_sha"),
    terminal.record.get("int_attempt_ref"):terminal.accepted_sha,
  }
  if (len(expected) != 2
      or {r.ref for r in retirements} != set(expected)
      or any(type(r.absent_after) is not bool or not r.absent_after
             or type(r.previously_observed_sha) is not str
             or r.previously_observed_sha != expected[r.ref]
             for r in retirements)):
    raise CompletionHandoffError("physical retirement not independently proven")
  before=store.read(issue)
  if (not isinstance(before, LifecycleSnapshot)
      or before.revision != expected_revision
      or before.lifecycle.state != "accepted"
      or before.lifecycle.issue != str(issue)
      or before.lifecycle.relationship_revision != relationship_revision
      or not before.lifecycle.history
      or before.lifecycle.history[-1].transition != "accept"
      or before.lifecycle.history[-1].candidate != terminal.accepted_sha):
    raise CompletionHandoffError("accepted lifecycle revision/candidate mismatch")
  try:
    observed_terminal=reread_terminal(terminal.guid)
    observed_promotion=reread_promotion(promotions.operation_id)
  except Exception as error:
    raise CompletionHandoffError("provider terminal/promotion readback UNKNOWN") from error
  if observed_terminal != terminal.record or observed_promotion != promotions:
    raise CompletionHandoffError("provider facts changed before lifecycle CAS")
  advanced=store.transition(
    issue,"complete",terminal.accepted_sha,
    relationship_revision,writer,expected_revision)
  if (not isinstance(advanced,LifecycleSnapshot)
      or advanced.lifecycle.state != "completed"
      or advanced.lifecycle.dependency_satisfied is not True
      or advanced.revision != expected_revision+1):
    raise CompletionHandoffError("authoritative completion readback differed")
  check=store.read(issue)
  if check != advanced:
    raise CompletionHandoffError("lifecycle completion readback UNKNOWN")
  return advanced
