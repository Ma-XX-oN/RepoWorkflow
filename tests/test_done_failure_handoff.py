"""Immutable #109 owner-handoff readback, retry and multi-issue contracts."""
from dataclasses import replace
import unittest

from repo_workflow.done_failure_handoff import (
  FailureHandoff, HandoffError, publish_failure_handoff,
)

GUID="11111111-1111-4111-8111-111111111111"
A="a"*40
B="b"*40
C="c"*40


class HandoffTests(unittest.TestCase):
  def setUp(self):
    self.handoff=FailureHandoff(
      GUID,109,"main",A,B,C,"AIT_FAIL","hosted-failed-run",
      (109,681),"run-artifact-1",(),"not-a-conflict",
      "integration-op-1")
    self.comments={}
    self.posts=[]
    self.lost_ack=False
    self.skip_issue=None
    self.forge=False

  def persist(self,issue,key,handoff):
    self.posts.append((issue,key))
    if issue!=self.skip_issue:
      self.comments[(issue,key)]={
        "issue_id":issue,"operation_id":key,
        "handoff":handoff,"comment_ref":"comment-"+str(issue)}
    if self.lost_ack:
      raise TimeoutError("persisted then lost reply")

  def read(self,issue,key):
    value=self.comments.get((issue,key))
    if self.forge and value is not None:
      return {**value,"handoff":replace(
        self.handoff,prelim_sha=B)}
    return value

  def invoke(self,**changes):
    args={"handoff":self.handoff,
          "publish_comment":self.persist,"read_comment":self.read}
    return publish_failure_handoff(**{**args,**changes})

  def test_exact_multi_owner_handoff_and_readback(self):
    result=self.invoke()
    self.assertEqual(result.per_issue_refs,
                     ((109,"comment-109"),(681,"comment-681")))
    self.assertEqual(len(self.posts),2)

  def test_lost_ack_reconciles_without_duplicate_write(self):
    self.lost_ack=True
    result=self.invoke()
    self.assertEqual(len(result.per_issue_refs),2)
    self.assertEqual(len(self.posts),2)

  def test_missing_second_owner_does_not_claim_handoff_done(self):
    self.skip_issue=681
    with self.assertRaisesRegex(HandoffError,"missing or changed"):
      self.invoke()
    self.assertEqual(len(self.posts),2)

  def test_forged_provider_handoff_refused(self):
    self.forge=True
    with self.assertRaisesRegex(HandoffError,"missing or changed"):
      self.invoke()

  def test_missing_original_issue_in_recipient_list_refused(self):
    with self.assertRaisesRegex(HandoffError,"identity"):
      self.invoke(handoff=replace(
        self.handoff,owner_issue_ids=(681,)))
    self.assertEqual(self.posts,[])

  def test_unverified_issue_ref_and_duplicate_owners_denied(self):
    for values in ((109,109),(109,0),(109,"681"),()):
      with self.subTest(values=values):
        with self.assertRaises(HandoffError):
          self.invoke(handoff=replace(
            self.handoff,owner_issue_ids=values))
    self.assertEqual(self.posts,[])

  def test_unknown_readback_stops_advancement(self):
    def unavailable(issue,key):
      raise ConnectionError("provider down")
    with self.assertRaisesRegex(HandoffError,"UNKNOWN"):
      self.invoke(read_comment=unavailable)


if __name__=="__main__":
  unittest.main()
