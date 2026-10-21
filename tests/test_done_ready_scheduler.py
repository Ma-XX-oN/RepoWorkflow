"""Destination inventory and exact coordinator scheduling negative cases."""
import unittest

from repo_workflow.done_ready_scheduler import (
  DestinationInventory, ReadySelectionError, select_ready_for_destination,
)
from repo_workflow.prelim_queue import parse_ready_prelim


A="a"*40
B="b"*40
G1="11111111-1111-4111-8111-111111111111"
G2="22222222-2222-4222-8222-222222222222"
ONE=f"refs/heads/PRELIM-issue-123/main-{G1}"
TWO=f"refs/heads/PRELIM-issue-456/main-{G2}"


class Host:
  repository="Org/Repo"

  def __init__(self):
    self.refs={ONE:A,TWO:B}
    self.calls=[]

  def request(self,op,key,args):
    self.calls.append(op)
    if op != "refs.list": raise AssertionError(op)
    return {"refs":dict(self.refs)}


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
    self.assertEqual(self.host.calls,["refs.list","refs.list"])

  def test_no_implicit_guid_priority(self):
    with self.assertRaisesRegex(ReadySelectionError,"unverified"):
      self.choose(lambda d,x:None)

  def test_empty_destination_returns_no_work(self):
    result=self.choose(lambda d,x:None,destination="issue-999")
    self.assertEqual(result,DestinationInventory("issue-999",(),None))

  def test_other_destination_candidate_refused(self):
    alien=parse_ready_prelim(
      f"refs/heads/PRELIM-issue-123/issue-999-{G1}",A)
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
    self.host.refs[
      f"refs/heads/PRELIM-issue-555/issue-999-{G2}"]=B
    del self.host.refs[TWO]
    selection=self.choose(lambda d,r:r[0])
    self.assertEqual(len(selection.ready),1)
    self.assertEqual(selection.selected.ref,ONE)


if __name__=="__main__":
  unittest.main()
