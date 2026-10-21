"""Bounded provider queue A-success/B-failed/C-success with no phantom DONE."""
from collections import namedtuple
import unittest

from repo_workflow.done_completion import VerifiedCompletion
from repo_workflow.done_evidence_promotion import Promotion
from repo_workflow.done_provider_pipeline import DeferredProviderAttempt
from repo_workflow.done_queue_cycle import (
  QueueCycleError, VerifiedFailure, process_destination_cycle,
)
from repo_workflow.done_terminal_v2 import IntegratedTerminal
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_queue_scheduler import QueueHost, ALT, REF, A, B


C="c"*40
GUID3="33333333-3333-4333-8333-333333333333"
THIRD=f"refs/heads/PRELIM-issue-126/main-{GUID3}"
Retired=namedtuple("Retired","absent_after")
BASE="d"*40


class QueueCycleTests(unittest.TestCase):
  def setUp(self):
    self.host=QueueHost()
    self.host.refs[THIRD]=C
    self.orders=[]
    self.handoffs=[]
  def selector(self,snapshot):
    rank={"issue-123":0,"issue-124":1,"issue-126":2}
    return min(snapshot.pending,key=lambda x:rank[x.umbrella])
  def result(self,ready,kind):
    self.orders.append((ready.umbrella,kind))
    if kind=="success":
      sha="e"*40
      op="operation-"+ready.guid
      self.host.terminals[ready.guid]={
        "repository":"Org/Repo","guid":ready.guid,"status":"integrated"}
      terminal=IntegratedTerminal(
        ready.guid,"Org/Repo","main",ready.sha,sha,
        "integration-"+ready.guid,op,"terminal-proof",
        self.host.terminals[ready.guid])
      promotion=Promotion(
        op,ready.sha,ready.sha,BASE,sha,sha,sha,
        "context",())
      return VerifiedCompletion(
        op,sha,terminal,(Retired(True),Retired(True)),
        promotion,{"result":"done","guid":ready.guid,
                   "landed_sha":sha,"revision":1})
    if kind=="failure":
      self.host.terminals[ready.guid]={
        "repository":"Org/Repo","guid":ready.guid,"status":"failed"}
      return VerifiedFailure(
        ready.guid,"failed","issue-handoff-"+ready.guid,True)
    if kind=="deferred":
      self.host.deferred[ready.guid]={
        "repository":"Org/Repo","guid":ready.guid,
        "destination":"main","prelim_sha":ready.sha,
        "lease_generation":1,"evidence_ref":"mit-timeout",
        "reason":"timeout"}
      self.host.lease["generation"]=2
      return DeferredProviderAttempt(ready,"mit-timeout",2)
    raise AssertionError(kind)
  def invoke(self,execute,**options):
    return process_destination_cycle(
      host=self.host,destination="main",
      select_authorized=self.selector,
      execute_and_complete=execute,
      verify_handoff=lambda outcome,ready:(
        self.handoffs.append(ready.guid) or True),
      **options)

  def test_a_success_b_failure_handoff_c_success_all_progress(self):
    def execute(ready):
      mode={"issue-123":"success","issue-124":"failure",
            "issue-126":"success"}[ready.umbrella]
      return self.result(ready,mode)
    completed=self.invoke(execute,max_items=3)
    self.assertEqual(completed.stopped,"limit")
    self.assertEqual(completed.outcomes,
                     ("completed","failed-handoff","completed"))
    self.assertEqual([x[0] for x in self.orders],
                     ["issue-123","issue-124","issue-126"])
    self.assertEqual(len(self.handoffs),1)
    self.assertEqual(self.host.lease["generation"],0)
    self.assertEqual(len(self.host.refs),4)

  def test_failed_item_without_handoff_cannot_advance(self):
    with self.assertRaisesRegex(QueueCycleError,"not independently"):
      process_destination_cycle(
        host=self.host,destination="main",
        select_authorized=self.selector,
        execute_and_complete=lambda ready:self.result(ready,"failure"),
        verify_handoff=lambda outcome,ready:False,max_items=3)
    self.assertEqual(len(self.orders),1)

  def test_unverified_accepted_attempt_is_not_completion(self):
    with self.assertRaisesRegex(QueueCycleError,"unverified attempted"):
      self.invoke(lambda ready:object(),max_items=3)
    self.assertEqual(self.host.lease["generation"],0)

  def test_deferred_mit_event_must_be_remote_and_claim_released(self):
    result=self.invoke(
      lambda ready:self.result(ready,"deferred"),max_items=1)
    self.assertEqual(result.outcomes,("deferred-mit",))
    self.assertEqual(result.stopped,"limit")
    self.assertEqual(self.host.lease["generation"],2)

  def test_ambiguous_callback_stops_without_retry(self):
    attempts=[]
    def broken(ready):
      attempts.append(ready.guid)
      raise TimeoutError("provider ACK lost")
    with self.assertRaisesRegex(QueueCycleError,"UNKNOWN"):
      self.invoke(broken,max_items=3)
    self.assertEqual(len(attempts),1)

  def test_invalid_max_items_refused(self):
    for value in (0,101,True,-2):
      with self.subTest(value=value):
        with self.assertRaisesRegex(QueueCycleError,"bounded"):
          self.invoke(lambda ready:None,max_items=value)

  def test_completed_but_missing_retirement_never_advances(self):
    def incomplete(ready):
      valid=self.result(ready,"success")
      from dataclasses import replace
      return replace(valid,retired=(Retired(True),))
    with self.assertRaisesRegex(QueueCycleError,"completion identity"):
      self.invoke(incomplete,max_items=3)
    self.assertEqual(len(self.orders),1)


if __name__=="__main__":
  unittest.main()
