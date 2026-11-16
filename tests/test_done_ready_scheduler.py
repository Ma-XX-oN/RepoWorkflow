"""Destination inventory and exact coordinator scheduling negative cases."""
import unittest

from repo_workflow.done_ready_scheduler import (
  DestinationInventory, ReadySelectionError, select_ready_for_destination,
)
from repo_workflow.prelim_queue import parse_ready_prelim
from tests.test_done_queue_scheduler import QueueHost


A="a"*40
B="b"*40
ONE="refs/heads/PRELIM-issue-123.0.1"
TWO="refs/heads/PRELIM-issue-456.0.1"


class Host(QueueHost):
  repository="Org/Repo"

  def __init__(self):
    super().__init__()
    self.refs={ONE:A,TWO:B}
    self.submissions={parse_ready_prelim(ref,sha).guid:self.receipt(ref,sha)
                      for ref,sha in self.refs.items()}
    self.calls=[]

  def request(self,op,key,args):
    self.calls.append(op)
    return super().request(op,key,args)


class ScheduleTests(unittest.TestCase):
  def setUp(self):
    self.host=Host()

  def choose(self,selection,host=None,destination="main"):
    return select_ready_for_destination(
      host=self.host if host is None else host,
      destination=destination,select_authorized=selection)

  def test_two_umbrellas_contend_on_same_destination(self):
    seen=[]
    def selector(destination,ready):
      seen.extend(ready)
      return next(x for x in ready if x.umbrella=="issue-456")
    result=self.choose(selector)
    self.assertEqual(len(seen),2)
    self.assertEqual(result.selected.umbrella,"issue-456")
    self.assertEqual(result.destination,"main")
    self.assertEqual(self.host.calls.count("refs.list"),2)
    self.assertEqual(set(self.host.calls),{"refs.list","submission.read"})

  def test_no_implicit_guid_priority(self):
    with self.assertRaisesRegex(ReadySelectionError,"unverified"):
      self.choose(lambda d,x:None)

  def test_empty_destination_returns_no_work(self):
    result=self.choose(lambda d,x:None,destination="issue-999")
    self.assertEqual(result,DestinationInventory("issue-999",(),None))

  def test_other_destination_candidate_refused(self):
    alien=parse_ready_prelim(
      ONE,A,destination="issue-999")
    with self.assertRaisesRegex(ReadySelectionError,"unverified"):
      self.choose(lambda d,x:alien)

  def test_ref_sha_moved_after_selection_fails_closed(self):
    def select(d,ready):
      self.host.refs[ONE]=B
      return next(x for x in ready if x.ref==ONE)
    with self.assertRaisesRegex(ReadySelectionError,"changed"):
      self.choose(select)

  def test_provider_selector_failure_is_not_automatic_reorder(self):
    def fail(d,ready):raise ConnectionError("no authority")
    with self.assertRaisesRegex(ReadySelectionError,"UNKNOWN"):
      self.choose(fail)

  def test_multiple_destinations_do_not_share_claim_set(self):
    ref="refs/heads/PRELIM-issue-555.0.1"
    self.host.refs[ref]=B
    receipt=self.host.receipt(ref,B)
    receipt["destination"]="issue-999"
    self.host.submissions[receipt["guid"]]=receipt
    del self.host.refs[TWO]
    selection=self.choose(lambda d,r:r[0])
    self.assertEqual(len(selection.ready),1)
    self.assertEqual(selection.selected.ref,ONE)


if __name__=="__main__":
  unittest.main()
