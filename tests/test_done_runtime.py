"""Composition of native #109 provider outcome, deferral and owner handoff."""
from dataclasses import replace
import unittest

from repo_workflow.done_completion import VerifiedCompletion
from repo_workflow.done_failure_handoff import (
  FailureHandoff,PersistedFailureHandoff,publish_failure_handoff,
)
from repo_workflow.done_planner import DonePlan
from repo_workflow.done_provider_pipeline import (
  DeferredProviderAttempt,FailedProviderAttempt,
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
    self.fixture=CompletionTests("test_done_only_after_prelim_retirement_and_provenance")
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
    )
    return execute_ready_done(**{**args,**changes})




  def test_real_composition_requires_completed_provenance(self):
    result=self.invoke()
    self.assertIsInstance(result,VerifiedNativeDone)
    self.assertIsInstance(result.completion,VerifiedCompletion)
    self.assertEqual(result.completion.operation_id,"op-1")
    self.assertEqual(result.completion.landed_sha,"d"*40)
    self.assertEqual(result.plan,self.plan)
    self.assertEqual(result.source.tested_source_sha,self.plan.candidate_sha)





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

  def test_release_failure_reaches_persisted_owner_handoff(self):
    failed=FailedProviderAttempt(
      self.ready,"release","release-stage-proof",2)
    handoff=FailureHandoff(
      G,123,"main",A,B,C,"release_FAIL","release-stage-proof",
      (123,),"release-run-artifact",(),"release-stage-failure",
      "release-operation-1")
    records={}
    def publish(issue,key,record):
      records[(issue,key)]={
        "issue_id":issue,"operation_id":key,
        "handoff":record,"comment_ref":"durable-"+key}
    def reread(issue,key):
      return records.get((issue,key))
    outcome=self.invoke(
      execute_provider_attempt=lambda *args:failed,
      publish_failure_handoff=lambda attempt:publish_failure_handoff(
        handoff,publish_comment=publish,read_comment=reread))
    self.assertIsInstance(outcome,VerifiedFailedDone)
    self.assertEqual(outcome.persisted_handoff.handoff.failure_kind,
                     "release_FAIL")
    self.assertEqual(len(records),1)

  def test_failed_owner_receipt_must_match_issue_parent_and_exact_owners(self):
    failed=FailedProviderAttempt(self.ready,"AIT","failed-stage-proof",2)
    handoff=FailureHandoff(
      G,123,"main",A,B,C,"AIT_FAIL","failed-stage-proof",
      (123,),"repro",(),"owner","operation")
    valid=PersistedFailureHandoff(handoff,((123,"comment-123"),))
    forged=[
      replace(valid,handoff=replace(handoff,issue=124)),
      replace(valid,handoff=replace(handoff,destination="other")),
      replace(valid,handoff=replace(handoff,expected_parent_sha=C)),
      replace(valid,handoff=replace(handoff,owner_issue_ids=(123,681))),
      replace(valid,per_issue_refs=((681,"comment-681"),)),
      replace(valid,per_issue_refs=((123,""),)),
    ]
    for receipt in forged:
      with self.subTest(receipt=receipt):
        with self.assertRaisesRegex(DoneRuntimeError,"durable owner handoff"):
          self.invoke(
            execute_provider_attempt=lambda *args:failed,
            publish_failure_handoff=lambda attempt:receipt)

  def test_mit_deferral_foreign_destination_or_reason_refused(self):
    outcome=DeferredProviderAttempt(self.ready,"timeout-proof",2)
    valid=MitDeferredEvent(G,"main",A,1,"timeout-proof","timeout")
    for event in (
      replace(valid,destination="other"),
      replace(valid,reason="failure"),
      replace(valid,reason="approved"),
    ):
      with self.subTest(event=event):
        with self.assertRaisesRegex(DoneRuntimeError,
                                    "missing exact provider evidence"):
          self.invoke(
            execute_provider_attempt=lambda *args:outcome,
            read_deferred_mit=lambda ready:event)

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
