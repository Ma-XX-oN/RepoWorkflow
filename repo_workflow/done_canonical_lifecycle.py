"""Connect #109 provider completion to the authoritative #583 lifecycle store.

This is a trusted composition adapter, not a source of provider PASS.
Review acceptance and its candidate must already exist in LifecycleStore.
"""
from .done_evidence_promotion import Promotion
from .done_lifecycle_binding import complete_after_provider
from .done_provider_pipeline import AcceptedProviderAttempt
from .done_terminal_v2 import IntegratedTerminal
from .lifecycle_store import LifecycleStore, LifecycleSnapshot
from .state_store import WriterIdentity, StateStoreError


class CanonicalLifecycleError(RuntimeError):
  """The provider outcome does not match durable lifecycle authority."""


class CanonicalLifecycleCompletion:
  """Bind a single issue/revision to provider completion and readback."""

  def __init__(self, *, store, issue, expected_revision,
               relationship_revision, writer,
               reread_terminal, reread_promotion):
    if (not isinstance(store, LifecycleStore)
        or type(issue) is not int or issue <= 0
        or type(expected_revision) is not int or expected_revision < 0
        or type(relationship_revision) is not int
        or relationship_revision < 0
        or not isinstance(writer, WriterIdentity)
        or not callable(reread_terminal)
        or not callable(reread_promotion)):
      raise CanonicalLifecycleError(
        "authoritative lifecycle store and provider readers required")
    self.store=store
    self.issue=issue
    self.expected_revision=expected_revision
    self.relationship_revision=relationship_revision
    self.writer=writer
    self.reread_terminal=reread_terminal
    self.reread_promotion=reread_promotion

  def _scope(self, accepted, proof, retirements):
    if (not isinstance(accepted, AcceptedProviderAttempt)
        or not isinstance(accepted.terminal, IntegratedTerminal)
        or not isinstance(proof, Promotion)
        or type(retirements) is not tuple or len(retirements)!=2):
      raise CanonicalLifecycleError("verified provider completion required")
    ready=accepted.ready
    terminal=accepted.terminal
    if (ready.umbrella!="issue-"+str(self.issue)
        or ready.guid!=terminal.guid
        or ready.destination!=terminal.destination
        or terminal.record.get("prelim_ref")!=ready.ref
        or terminal.record.get("prelim_sha")!=ready.sha
        or terminal.accepted_sha!=proof.accepted_candidate_sha
        or terminal.landed_sha!=proof.landed_sha
        or terminal.operation_id!=proof.operation_id
        or terminal.operation_id!=accepted.accepted.operation_id
        or terminal.landed_sha!=accepted.accepted.landed_sha):
      raise CanonicalLifecycleError("provider and lifecycle issue identity differ")
    expected={
      terminal.record.get("prelim_ref"):ready.sha,
      terminal.record.get("int_attempt_ref"):terminal.accepted_sha,
    }
    if (len(expected)!=2
        or {getattr(r,"ref",None) for r in retirements}!=set(expected)
        or any(getattr(r,"absent_after",None) is not True
               or getattr(r,"previously_observed_sha",None)
                  !=expected.get(getattr(r,"ref",None))
               for r in retirements)):
      raise CanonicalLifecycleError("both exact retirements required")
    return terminal

  def _intent_payload(self, accepted, terminal):
    """Record operation identity separately, without redefining lifecycle."""
    return {
      "schema_version":1,
      "issue":str(self.issue),
      "expected_revision":self.expected_revision,
      "relationship_revision":self.relationship_revision,
      "guid":terminal.guid,
      "operation_id":terminal.operation_id,
      "destination":accepted.ready.destination,
      "prelim_ref":accepted.ready.ref,
      "prelim_sha":accepted.ready.sha,
      "accepted_sha":terminal.accepted_sha,
      "landed_sha":terminal.landed_sha,
    }

  def _read_intent(self, expected, *, create):
    """The first completion owns the issue; a different operation is foreign."""
    key="issues/"+str(self.issue)+"/done-intent"
    try:
      record=self.store.records.read(key)
    except StateStoreError as error:
      if "record is missing:" not in str(error):
        raise CanonicalLifecycleError(
          "completion intent store UNKNOWN") from error
      if not create:
        raise CanonicalLifecycleError(
          "durable completion operation identity missing") from error
      try:
        self.store.records.create(key,expected,self.writer)
      except Exception:
        # Missing acknowledgment or a concurrent writer: read, never overwrite.
        pass
      try:
        record=self.store.records.read(key)
      except Exception as read_error:
        raise CanonicalLifecycleError(
          "completion intent append/readback UNKNOWN") from read_error
    if (type(record) is not dict or record.get("revision")!=0
        or record.get("value")!=expected):
      raise CanonicalLifecycleError(
        "foreign completion operation already owns lifecycle")
    return record

  def persist_lifecycle(self, accepted, proof, retirements):
    terminal=self._scope(accepted,proof,retirements)
    before=self.store.read(self.issue)
    state=before.lifecycle
    if (before.revision not in {
          self.expected_revision,self.expected_revision+1}
        or state.issue!=str(self.issue)
        or state.relationship_revision!=self.relationship_revision
        or state.state not in {"accepted","completed"}
        or not state.history
        or state.history[-1].candidate!=terminal.accepted_sha):
      raise CanonicalLifecycleError(
        "accepted lifecycle candidate/revision missing before intent")
    if (self.reread_terminal(terminal.guid)!=terminal.record
        or self.reread_promotion(proof.operation_id)!=proof):
      raise CanonicalLifecycleError(
        "provider completion differs before intent")
    self._read_intent(self._intent_payload(accepted,terminal),create=True)
    return complete_after_provider(
      store=self.store,issue=self.issue,
      expected_revision=self.expected_revision,
      relationship_revision=self.relationship_revision,
      writer=self.writer,terminal=terminal,promotions=proof,
      retirements=retirements,
      reread_terminal=self.reread_terminal,
      reread_promotion=self.reread_promotion)

  def read_lifecycle(self, accepted, proof, retirements):
    """Read only: never create a completed transition on failed publication."""
    terminal=self._scope(accepted,proof,retirements)
    self._read_intent(self._intent_payload(accepted,terminal),create=False)
    try:
      before=self.store.read(self.issue)
      history=before.lifecycle.history
      if (not isinstance(before,LifecycleSnapshot)
          or before.revision!=self.expected_revision+1
          or before.lifecycle.issue!=str(self.issue)
          or before.lifecycle.relationship_revision!=self.relationship_revision
          or before.lifecycle.state!="completed"
          or before.lifecycle.dependency_satisfied is not True
          or len(history)<2
          or history[-2].transition!="accept"
          or history[-2].candidate!=terminal.accepted_sha
          or history[-1].transition!="complete"
          or history[-1].candidate!=terminal.accepted_sha
          or history[-1].sequence!=history[-2].sequence+1):
        raise CanonicalLifecycleError(
          "authoritative completed revision/candidate absent")
      if (self.reread_terminal(terminal.guid)!=terminal.record
          or self.reread_promotion(proof.operation_id)!=proof):
        raise CanonicalLifecycleError(
          "provider completion provenance changed")
      if self.store.read(self.issue)!=before:
        raise CanonicalLifecycleError(
          "lifecycle changed during authoritative readback")
    except CanonicalLifecycleError:
      raise
    except Exception as error:
      raise CanonicalLifecycleError(
        "authoritative lifecycle readback UNKNOWN") from error
    return {
      "guid":terminal.guid,
      "operation_id":terminal.operation_id,
      "landed_sha":terminal.landed_sha,
      "result":"done",
      "revision":before.revision,
    }
