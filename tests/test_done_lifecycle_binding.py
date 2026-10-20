"""Lifecycle revision CAS waits for live integration and exact evidence."""
from dataclasses import replace
import unittest

from repo_workflow.done_lifecycle_binding import (
  CompletionHandoffError, complete_after_provider,
)
from repo_workflow.done_terminal_v2 import IntegratedTerminal
from repo_workflow.lifecycle_store import (
  IssueLifecycle, LifecycleEvent, LifecycleSnapshot,
)
from repo_workflow.prelim_retirement_remote import RefRetirement
from repo_workflow.state_store import WriterIdentity
from tests.test_done_evidence_promotion import PromotionTests, B, D


G="11111111-1111-4111-8111-111111111111"
P=f"refs/heads/PRELIM-issue-123/main-{G}"
I=P.replace("PRELIM-","INT-ATTEMPT-")
A="a"*40


class FakeStore:
  def __init__(self):
    history=(
      LifecycleEvent(0,"start","not_started","active",None),
      LifecycleEvent(1,"submit-review","active","in_review",B),
      LifecycleEvent(2,"accept","in_review","accepted",B),
    )
    self.record=LifecycleSnapshot(
      IssueLifecycle("123","accepted",False,3,history),5)
    self.transition_calls=0

  def read(self,issue):
    return self.record

  def transition(self,issue,action,candidate,revision,writer,expected):
    if self.record.revision != expected:
      raise ValueError("stale lifecycle")
    old=self.record.lifecycle
    assert action=="complete" and candidate==B
    event=LifecycleEvent(3,"complete","accepted","completed",candidate)
    self.record=LifecycleSnapshot(
      replace(old,state="completed",dependency_satisfied=True,
              history=old.history+(event,)),expected+1)
    self.transition_calls+=1
    return self.record


class LifecycleHandoffTests(unittest.TestCase):
  def setUp(self):
    self.store=FakeStore()
    p=PromotionTests()
    p.setUp()
    self.promotion=p.make()
    self.record={
      "guid":G,"status":"integrated",
      "prelim_ref":P,"prelim_sha":A,"int_attempt_ref":I,
    }
    self.terminal=IntegratedTerminal(
      G,"Org/Repo","main",B,D,"integration-1",
      "integrate-123","evidence-1",self.record)
    self.retires=(
      RefRetirement(P,A,True),RefRetirement(I,B,True))
    self.kwargs={
      "store":self.store,"issue":123,"expected_revision":5,
      "relationship_revision":3,"writer":WriterIdentity("rwf109","session1"),
      "terminal":self.terminal,"promotions":self.promotion,
      "retirements":self.retires,
      "reread_terminal":lambda guid:self.record,
      "reread_promotion":lambda operation:self.promotion,
    }

  def invoke(self,**kwargs):
    return complete_after_provider(**{**self.kwargs,**kwargs})

  def test_real_accepted_state_completes_after_provider_proof(self):
    result=self.invoke()
    self.assertEqual(result.revision,6)
    self.assertEqual(result.lifecycle.state,"completed")
    self.assertEqual(result.lifecycle.history[-1].candidate,B)
    self.assertEqual(self.store.transition_calls,1)

  def test_review_not_accepted_cannot_be_completed(self):
    before=self.store.record
    self.store.record=replace(
      before,lifecycle=replace(before.lifecycle,state="in_review"))
    with self.assertRaises(CompletionHandoffError):
      self.invoke()
    self.assertEqual(self.store.transition_calls,0)

  def test_changed_review_candidate_fails(self):
    before=self.store.record
    history=list(before.lifecycle.history)
    history[-1]=replace(history[-1],candidate=A)
    self.store.record=replace(
      before,lifecycle=replace(before.lifecycle,history=tuple(history)))
    with self.assertRaisesRegex(CompletionHandoffError,"candidate"):
      self.invoke()
    self.assertEqual(self.store.transition_calls,0)

  def test_stale_revision_does_not_mutate(self):
    with self.assertRaisesRegex(CompletionHandoffError,"revision"):
      self.invoke(expected_revision=4)
    self.assertEqual(self.store.transition_calls,0)

  def test_unretired_prelim_never_satisfies_lifecycle(self):
    altered=(
      RefRetirement(P,A,False),RefRetirement(I,B,True))
    with self.assertRaisesRegex(CompletionHandoffError,"retirement"):
      self.invoke(retirements=altered)
    self.assertEqual(self.store.transition_calls,0)

  def test_landed_record_changed_no_lifecycle_transition(self):
    with self.assertRaisesRegex(CompletionHandoffError,"changed"):
      self.invoke(reread_terminal=lambda guid:{"status":"failed"})
    self.assertEqual(self.store.transition_calls,0)

  def test_missing_promotion_readback_never_satisfies_dependency(self):
    with self.assertRaisesRegex(CompletionHandoffError,"changed"):
      self.invoke(reread_promotion=lambda operation:None)
    self.assertEqual(self.store.transition_calls,0)


if __name__=="__main__":
  unittest.main()
