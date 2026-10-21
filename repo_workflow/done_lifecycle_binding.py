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


def _matching_completed_revision(snapshot, issue, expected_revision,
                                 relationship_revision, candidate):
  """Recognize only the exact completed revision after an ambiguous ACK."""
  if not isinstance(snapshot, LifecycleSnapshot):
    return False
  history=snapshot.lifecycle.history
  return (
    snapshot.revision == expected_revision+1
    and snapshot.lifecycle.issue == str(issue)
    and snapshot.lifecycle.state == "completed"
    and snapshot.lifecycle.dependency_satisfied is True
    and snapshot.lifecycle.relationship_revision == relationship_revision
    and len(history)>=2
    and history[-2].transition == "accept"
    and history[-2].candidate == candidate
    and history[-1].transition == "complete"
    and history[-1].candidate == candidate
    and history[-1].sequence == history[-2].sequence+1
  )


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
  accepted=(
    isinstance(before, LifecycleSnapshot)
    and before.revision == expected_revision
    and before.lifecycle.state == "accepted"
    and before.lifecycle.issue == str(issue)
    and before.lifecycle.relationship_revision == relationship_revision
    and bool(before.lifecycle.history)
    and before.lifecycle.history[-1].transition == "accept"
    and before.lifecycle.history[-1].candidate == terminal.accepted_sha
  )
  recovered=_matching_completed_revision(
    before,issue,expected_revision,relationship_revision,
    terminal.accepted_sha)
  if not accepted and not recovered:
    raise CompletionHandoffError("accepted lifecycle revision/candidate mismatch")
  try:
    observed_terminal=reread_terminal(terminal.guid)
    observed_promotion=reread_promotion(promotions.operation_id)
  except Exception as error:
    raise CompletionHandoffError("provider terminal/promotion readback UNKNOWN") from error
  if observed_terminal != terminal.record or observed_promotion != promotions:
    raise CompletionHandoffError("provider facts changed before lifecycle CAS")
  if recovered:
    check=store.read(issue)
    if check != before:
      raise CompletionHandoffError("lifecycle retry readback UNKNOWN")
    return before
  try:
    advanced=store.transition(
      issue,"complete",terminal.accepted_sha,
      relationship_revision,writer,expected_revision)
  except Exception as error:
    # The CAS write can commit even when its acknowledgment is lost.
    # Do not replay it; re-read the one permitted successor revision.
    try:
      advanced=store.read(issue)
    except Exception as read_error:
      raise CompletionHandoffError(
        "lifecycle completion readback UNKNOWN") from read_error
    if not _matching_completed_revision(
        advanced,issue,expected_revision,relationship_revision,
        terminal.accepted_sha):
      raise CompletionHandoffError(
        "lifecycle completion outcome UNKNOWN") from error
  if (not _matching_completed_revision(
      advanced,issue,expected_revision,relationship_revision,
      terminal.accepted_sha)):
    raise CompletionHandoffError("authoritative completion readback differed")
  check=store.read(issue)
  if check != advanced:
    raise CompletionHandoffError("lifecycle completion readback UNKNOWN")
  return advanced
