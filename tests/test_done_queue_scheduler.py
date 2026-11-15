"""Provider-scoped READY scheduling across competing umbrellas."""
import unittest

from repo_workflow.done_queue_scheduler import (
  QueueAdmissionError, choose_submission, inventory_destination,
)
from tests.test_done_host_coordinator import FakeHost, GUID, REF, A
from repo_workflow.prelim_queue import parse_ready_prelim


B="b"*40
ALT="refs/heads/PRELIM-issue-124.0.1"
SIDE="refs/heads/PRELIM-issue-125.0.1"
OTHER=parse_ready_prelim(ALT, B).guid
DIFFERENT=parse_ready_prelim(SIDE, A).guid


class QueueHost(FakeHost):
  def __init__(self):
    super().__init__()
    self.refs={REF:A,ALT:B,SIDE:A}
    self.submissions={parse_ready_prelim(ref, sha).guid:self.receipt(ref, sha)
                      for ref, sha in self.refs.items()}
    self.deferred={}
    self.terminals={}
    self.approvals={}
    self.inventory_reads=0
    self.change_ref_after_first=False
  def receipt(self, ref, sha):
    """Construct an explicit provider-provenance fixture, not test evidence."""
    return {"repository":self.repository, "guid":parse_ready_prelim(ref, sha).guid,
            "prelim_ref":ref, "source_sha":sha, "candidate_sha":sha,
            "parent_sha":"f"*40, "destination":"side" if ref == SIDE else "main",
            "version":"1.2.3-" + ref.removeprefix("refs/heads/PRELIM-").replace("issue-", "issue.", 1),
            "inputs_sha256":"f"*64, "release":"patch"}
  def request(self,operation,key,params):
    if operation=="refs.list":
      self.inventory_reads += 1
      result={"refs":dict(self.refs)}
      if self.change_ref_after_first and self.inventory_reads==1:
        self.refs[ALT]=A
      return result
    if operation=="submission.read":
      return {"guid":params["guid"],"record":self.submissions.get(params["guid"])}
    if operation=="destination.read":
      return {"destination":params["destination"],
              "ref":"refs/heads/"+params["destination"],"sha":"f"*40}
    if operation=="lease.read" and params["destination"]=="side":
      return {"destination":"side","generation":0,
              "guid":None,"holder":None}
    if operation=="attempt.read":
      return {"guid":params["guid"],
              "record":self.terminals.get(params["guid"])}
    if operation=="mit.deferred.read":
      return {"guid":params["guid"],"destination":params["destination"],
              "event":self.deferred.get(params["guid"])}
    if operation=="mit.resume.read":
      return {"guid":params["guid"],"destination":params["destination"],
              "authorization":self.approvals.get(params["guid"])}
    return super().request(operation,key,params)


class QueueTests(unittest.TestCase):
  def setUp(self):
    self.host=QueueHost()

  def test_superseded_submission_never_reappears_after_latest_failure(self):
    """The latest generation, including its failure, governs this issue."""
    latest = "refs/heads/PRELIM-issue-123.0.10"
    guid = parse_ready_prelim(latest, B).guid
    self.host.refs = {REF:A, latest:B}
    self.host.submissions[guid] = self.host.receipt(latest, B)
    self.host.submissions.pop(GUID)
    self.host.terminals[guid] = {"repository":self.host.repository,
                                 "guid":guid,"status":"failed"}
    state = inventory_destination(self.host, "main")
    self.assertEqual(state.pending, ())
    self.assertEqual(state.superseded, ())
    self.assertEqual([item.ref for item in state.terminal], [latest])

  def test_missing_latest_receipt_blocks_execution(self):
    """Version orders refs, but execution still requires exact provenance."""
    self.host.submissions.pop(GUID)
    with self.assertRaisesRegex(QueueAdmissionError, "metadata|provenance"):
      inventory_destination(self.host, "main")

  def test_stale_latest_does_not_require_old_receipts(self):
    """Only selected version metadata participates in stale classification."""
    latest = "refs/heads/PRELIM-issue-123.0.10"
    guid = parse_ready_prelim(latest, B).guid
    self.host.refs = {latest:B}
    self.host.submissions = {guid: self.host.receipt(latest, B)}
    self.host.submissions[guid]["parent_sha"] = "e"*40
    state = inventory_destination(self.host, "main")
    self.assertEqual([item.ref for item in state.pending], [latest])
    self.assertEqual([item.ref for item in state.stale], [latest])
    self.assertEqual(state.superseded, ())

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

  def test_deferred_restarts_only_after_current_generation_approval(self):
    self.host.deferred[OTHER]={
      "repository":"Org/Repo","guid":OTHER,"destination":"main",
      "prelim_sha":B,"lease_generation":1,
      "evidence_ref":"defer-proof","reason":"timeout"}
    self.host.lease["generation"]=2
    state=inventory_destination(self.host,"main")
    self.assertEqual([x.guid for x in state.deferred],[OTHER])
    self.host.approvals[OTHER]={
      "repository":"Org/Repo","guid":OTHER,"destination":"main",
      "prelim_sha":B,"expected_generation":2,
      "deferred_evidence_ref":"defer-proof",
      "evidence_ref":"approval-proof","approved":True}
    state=inventory_destination(self.host,"main")
    self.assertIn(OTHER,[x.guid for x in state.pending])
    self.host.lease["generation"]=4
    state=inventory_destination(self.host,"main")
    self.assertIn(OTHER,[x.guid for x in state.deferred])

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
