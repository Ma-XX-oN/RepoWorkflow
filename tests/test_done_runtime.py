"""Composition of native #109 provider outcome, deferral and owner handoff."""
from dataclasses import replace
import unittest

from repo_workflow.done_completion import VerifiedCompletion
from repo_workflow.done_failure_handoff import (
  FailureHandoff,PersistedFailureHandoff,
)
from repo_workflow.done_planner import DonePlan
from repo_workflow.done_provider_pipeline import (
  DeferredProviderAttempt,FailedProviderAttempt,
)
from repo_workflow.done_shared_lifecycle import (
  SharedLifecycleEvidence,SharedAuthorityObservation,
)
from repo_workflow.done_runtime import (
  DoneRuntimeError, VerifiedNativeDone, VerifiedDeferredDone, VerifiedFailedDone,
  execute_ready_done,
)
from repo_workflow.done_source_identity import EffectiveSource
from repo_workflow.integration_coordination import MitDeferredEvent
from tests.test_done_completion import CompletionTests
from tests.test_done_provider_pipeline import A,B,C,G


class RuntimeTests(unittest.TestCase):
  def setUp(self):
    self.fixture=CompletionTests("test_done_only_after_both_refs_and_provenance")
    self.fixture.setUp()
    self.ready=self.fixture.accepted.ready
    self.plan=DonePlan(
      "123","patch","main",A,B,"ALLOWED",True,False,None,(),())
    self.attempt=self.fixture.accepted
    self.calls=[]

  def invoke(self,**changes):
    args=dict(
      release="patch",
      read_current_plan=lambda release:self.plan,
      select_ready=lambda plan:self.ready,
      execute_provider_attempt=lambda ready,plan:self.attempt,
      complete_accepted=lambda accepted:self.fixture.invoke(),
      read_deferred_mit=lambda ready:None,
      publish_failure_handoff=lambda attempt:None,
      verify_source_lineage=lambda plan,ready:EffectiveSource(
        plan.candidate_sha,plan.candidate_sha,()),
      verify_shared_lifecycle=lambda done,plan,ready:SharedLifecycleEvidence(
        "Org/Repo","authorized-state","a"*40,int(plan.issue),
        done.lifecycle["revision"],done.operation_id,
        done.terminal.accepted_sha,done.landed_sha,
        "b"*64,"c"*64,True),
      read_shared_authority=lambda plan,ready:SharedAuthorityObservation(
        "Org/Repo","authorized-state","a"*40,True),
    )
    return execute_ready_done(**{**args,**changes})

  def test_missing_shared_authority_registration_denies_command(self):
    with self.assertRaisesRegex(DoneRuntimeError,"bindings required"):
      self.invoke(read_shared_authority=None)

  def test_forged_or_foreign_state_scope_rejected(self):
    for forged in (
        None,True,
        SharedAuthorityObservation("Other/Repo","authorized-state","a"*40,True),
        SharedAuthorityObservation("Org/Repo","foreign-state","a"*40,True),
        SharedAuthorityObservation("Org/Repo","authorized-state","f"*40,True),
        SharedAuthorityObservation("Org/Repo","authorized-state","a"*40,False)):
      with self.subTest(forged=forged):
        with self.assertRaisesRegex(DoneRuntimeError,"no DONE"):
          self.invoke(read_shared_authority=lambda *args:forged)

  def test_state_ref_changed_during_shared_readback_refuses_done(self):
    seen=[]
    def moved(*args):
      seen.append(1)
      return SharedAuthorityObservation(
        "Org/Repo","authorized-state",
        "a"*40 if len(seen)==1 else "f"*40,True)
    with self.assertRaisesRegex(DoneRuntimeError,"moved"):
      self.invoke(read_shared_authority=moved)
    self.assertEqual(len(seen),2)

  def test_real_composition_requires_completed_provenance(self):
    result=self.invoke()
    self.assertIsInstance(result,VerifiedNativeDone)
    self.assertIsInstance(result.completion,VerifiedCompletion)
    self.assertEqual(result.completion.operation_id,"op-1")
    self.assertEqual(result.completion.landed_sha,"d"*40)
    self.assertEqual(result.shared.commit_sha,result.authority.commit_sha)
    self.assertTrue(result.shared.independently_authenticated)
    self.assertEqual(result.plan,self.plan)
    self.assertEqual(result.source.tested_source_sha,self.plan.candidate_sha)

  def test_unbound_shared_lifecycle_provider_cannot_publish_done(self):
    with self.assertRaisesRegex(DoneRuntimeError,"bindings required"):
      self.invoke(verify_shared_lifecycle=None)

  def test_false_shared_lifecycle_receipt_does_not_certify_done(self):
    for forged in (None,True,{"revision":1}):
      with self.subTest(forged=forged):
        with self.assertRaisesRegex(DoneRuntimeError,"no DONE"):
          self.invoke(verify_shared_lifecycle=lambda *args:forged)

  def test_foreign_operation_or_revision_shared_receipts_are_refused(self):
    import dataclasses
    completed=self.fixture.invoke()
    valid=SharedLifecycleEvidence(
      "Org/Repo","authorized-state","a"*40,123,
      completed.lifecycle["revision"],completed.operation_id,
      completed.terminal.accepted_sha,completed.landed_sha,
      "b"*64,"c"*64,True)
    for key,value in (
        ("issue",124),("operation_id","other-operation"),
        ("revision",valid.revision+1),
        ("accepted_sha","f"*40),("landed_sha","0"*40),
        ("independently_authenticated",False)):
      with self.subTest(key=key):
        altered=dataclasses.replace(valid,**{key:value})
        with self.assertRaisesRegex(DoneRuntimeError,"no DONE"):
          self.invoke(verify_shared_lifecycle=lambda *args:altered)

  def test_shared_remote_read_exception_is_unknown_not_success(self):
    def lost(*args):
      raise TimeoutError("remote canonical state unreadable")
    with self.assertRaisesRegex(DoneRuntimeError,"UNKNOWN; no DONE"):
      self.invoke(verify_shared_lifecycle=lost)

  def test_missing_provider_oracle_refuses_before_mutation(self):
    with self.assertRaisesRegex(DoneRuntimeError,"bindings required"):
      self.invoke(execute_provider_attempt=None)

  def test_stale_or_invalid_plan_denied_before_ready(self):
    for change in ({"allowed":False},{"candidate_sha":C},
                   {"release":"minor"}):
      p=replace(self.plan,**change)
      with self.subTest(change=change):
        with self.assertRaises(DoneRuntimeError):
          self.invoke(read_current_plan=lambda release:p,
                      select_ready=lambda _:self.ready)

  def test_selected_foreign_attempt_never_reaches_provider(self):
    called=[]
    with self.assertRaisesRegex(DoneRuntimeError,"READY identity"):
      self.invoke(select_ready=lambda _:replace(self.ready,sha=C),
                  execute_provider_attempt=lambda *a:called.append(a))
    self.assertEqual(called,[])

  def test_material_command_source_change_refuses_before_provider(self):
    called=[]
    with self.assertRaisesRegex(DoneRuntimeError,"tested SHA"):
      self.invoke(
        verify_source_lineage=lambda *args:False,
        execute_provider_attempt=lambda *args:called.append(args))
    self.assertEqual(called,[])

  def test_forged_boolean_source_authentication_is_not_enough(self):
    with self.assertRaisesRegex(DoneRuntimeError,"tested SHA"):
      self.invoke(verify_source_lineage=lambda *args:True)

  def test_missing_invocation_lineage_oracle_is_denied(self):
    with self.assertRaisesRegex(DoneRuntimeError,"bindings required"):
      self.invoke(verify_source_lineage=None)

  def test_provider_outcome_unknown_never_retried(self):
    count=[]
    def failed(*args):
      count.append(1)
      raise TimeoutError("lost acceptance ACK")
    with self.assertRaisesRegex(DoneRuntimeError,"UNKNOWN"):
      self.invoke(execute_provider_attempt=failed)
    self.assertEqual(count,[1])

  def test_accepted_but_no_retirement_or_lifecycle_never_DONE(self):
    with self.assertRaisesRegex(DoneRuntimeError,"completion UNKNOWN"):
      self.invoke(complete_accepted=lambda a:(_ for _ in ()).throw(
        TimeoutError("post-CAS lost ACK")))
    with self.assertRaisesRegex(DoneRuntimeError,"unverified DONE"):
      self.invoke(complete_accepted=lambda a:object())

  def test_durable_deferred_mit_requires_exact_provider_event(self):
    outcome=DeferredProviderAttempt(self.ready,"timeout-proof",2)
    evidence=MitDeferredEvent(
      G,"main",A,1,"timeout-proof","timeout")
    observed=self.invoke(
      execute_provider_attempt=lambda *args:outcome,
      read_deferred_mit=lambda ready:evidence)
    self.assertIsInstance(observed,VerifiedDeferredDone)
    self.assertEqual(observed.attempt,outcome)
    self.assertEqual(observed.provider_event,evidence)
    with self.assertRaisesRegex(DoneRuntimeError,"missing exact"):
      self.invoke(
        execute_provider_attempt=lambda *args:outcome,
        read_deferred_mit=lambda ready:None)

  def test_failed_stage_requires_durable_issue_handoff(self):
    failed=FailedProviderAttempt(
      self.ready,"AIT","failed-stage-proof",2)
    handoff=FailureHandoff(
      G,123,"main",A,B,C,"AIT_FAIL","failed-stage-proof",
      (123,),"repro","", "unrelated","operation-1")
    # Conflict paths must be a tuple, and this test deliberately supplies
    # a tuple via replacement as the independent handoff must be validated.
    handoff=replace(handoff,conflict_paths=())
    persisted=PersistedFailureHandoff(
      handoff,((123,"issue-comment-1"),))
    observed=self.invoke(
      execute_provider_attempt=lambda *args:failed,
      publish_failure_handoff=lambda attempt:persisted)
    self.assertIsInstance(observed,VerifiedFailedDone)
    self.assertEqual(observed.attempt,failed)
    self.assertEqual(observed.persisted_handoff,persisted)
    with self.assertRaisesRegex(DoneRuntimeError,"durable owner handoff"):
      self.invoke(
        execute_provider_attempt=lambda *args:failed,
        publish_failure_handoff=lambda attempt:None)


if __name__=="__main__":
  unittest.main()
