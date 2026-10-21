"""Provider-scoped READY scheduling across competing umbrellas."""
import unittest

from repo_workflow.done_queue_scheduler import (
  QueueAdmissionError, choose_submission, inventory_destination,
)
from tests.test_done_host_coordinator import FakeHost, GUID, REF, A


B="b"*40
OTHER="22222222-2222-4222-8222-222222222222"
DIFFERENT="33333333-3333-4333-8333-333333333333"
ALT=f"refs/heads/PRELIM-issue-124/main-{OTHER}"
SIDE=f"refs/heads/PRELIM-issue-125/side-{DIFFERENT}"


class QueueHost(FakeHost):
  def __init__(self):
    super().__init__()
    self.refs={REF:A,ALT:B,SIDE:A}
    self.deferred={}
    self.terminals={}
    self.inventory_reads=0
    self.change_ref_after_first=False
  def request(self,operation,key,params):
    if operation=="refs.list":
      self.inventory_reads += 1
      result={"refs":dict(self.refs)}
      if self.change_ref_after_first and self.inventory_reads==1:
        self.refs[ALT]=A
      return result
    if operation=="attempt.read":
      return {"guid":params["guid"],
              "record":self.terminals.get(params["guid"])}
    if operation=="mit.deferred.read":
      return {"guid":params["guid"],"destination":params["destination"],
              "event":self.deferred.get(params["guid"])}
    return super().request(operation,key,params)


class QueueTests(unittest.TestCase):
  def setUp(self):
    self.host=QueueHost()

  def test_different_umbrellas_share_destination_and_no_guid_priority(self):
    state=inventory_destination(self.host,"main")
    self.assertEqual(len(state.pending),2)
    self.assertEqual({x.umbrella for x in state.pending},
                     {"issue-123","issue-124"})
    selected=choose_submission(
      host=self.host,destination="main",
      select_authorized=lambda snapshot:next(
        x for x in snapshot.pending if x.umbrella=="issue-124"))
    self.assertEqual(selected.umbrella,"issue-124")
    self.assertEqual(self.host.lease["generation"],0)

  def test_unrelated_destination_never_selected(self):
    state=inventory_destination(self.host,"side")
    self.assertEqual([x.umbrella for x in state.pending],["issue-125"])
    with self.assertRaisesRegex(QueueAdmissionError,"ineligible"):
      choose_submission(
        host=self.host,destination="main",
        select_authorized=lambda snapshot:state.pending[0])

  def test_destination_lease_serializes_independent_umbrellas(self):
    self.host.lease.update(
      generation=1,holder="other-coordinator",guid=GUID)
    called=[]
    result=choose_submission(
      host=self.host,destination="main",
      select_authorized=lambda snapshot:called.append(snapshot))
    self.assertIsNone(result)
    self.assertEqual(called,[])

  def test_deferred_and_terminal_not_runnable(self):
    self.host.deferred[OTHER]={
      "repository":"Org/Repo","guid":OTHER,"destination":"main",
      "prelim_sha":B,"lease_generation":1,
      "evidence_ref":"defer-proof","reason":"timeout"}
    state=inventory_destination(self.host,"main")
    self.assertEqual(len(state.pending),1)
    self.assertEqual(len(state.deferred),1)
    with self.assertRaisesRegex(QueueAdmissionError,"ineligible"):
      choose_submission(
        host=self.host,destination="main",
        select_authorized=lambda snapshot:state.deferred[0])

  def test_missing_or_foreign_selector_never_claims(self):
    with self.assertRaisesRegex(QueueAdmissionError,"scheduler"):
      choose_submission(
        host=self.host,destination="main",select_authorized=None)
    with self.assertRaisesRegex(QueueAdmissionError,"ineligible"):
      choose_submission(
        host=self.host,destination="main",
        select_authorized=lambda _: "not ready")
    self.assertEqual(self.host.lease["generation"],0)

  def test_changed_immutable_submission_ref_is_stale(self):
    self.host.change_ref_after_first=True
    with self.assertRaisesRegex(QueueAdmissionError,"changed"):
      choose_submission(
        host=self.host,destination="main",
        select_authorized=lambda snapshot:next(
          x for x in snapshot.pending if x.umbrella=="issue-124"))
    self.assertEqual(self.host.lease["generation"],0)

  def test_missing_all_submissions_returns_none(self):
    self.host.refs={SIDE:A}
    self.assertIsNone(choose_submission(
      host=self.host,destination="main",
      select_authorized=lambda snapshot:1))


if __name__=="__main__":
  unittest.main()
