"""Current destination policy readback on preflight and acceptance."""
import unittest

from repo_workflow.done_current_policy import (
  CurrentPolicyError, bind_current_policy,
)
from repo_workflow.done_planner import DonePlan
from repo_workflow.prelim_queue import parse_ready_prelim


G = "11111111-1111-4111-8111-111111111111"
REF = f"refs/heads/PRELIM-issue-123/main-{G}"
A, B = ("a"*40, "b"*40)


class Host:
  def __init__(self):
    self.policy_present = False
    self.policy = None
    self.tip = B
    self.calls = []

  def request(self, op, req, args):
    self.calls.append((op, req, args))
    return {"destination":"main","ref":"refs/heads/main",
            "sha":self.tip,"policy_present":self.policy_present,
            "policy_text":self.policy}


class PolicyTests(unittest.TestCase):
  def setUp(self):
    self.host=Host()
    self.ready=parse_ready_prelim(REF,A)
    self.plan=DonePlan(
      "123","patch","main",A,B,"ALLOWED",True,False,None,(),())

  def admit(self,parent="main"):
    return bind_current_policy(
      self.host,self.ready,lambda issue:parent)

  def test_absent_list_allows_immediate_child_only(self):
    self.assertTrue(self.admit()(self.plan).allowed)
    self.assertFalse(self.admit("issue-999")(self.plan).allowed)

  def test_present_empty_list_denies(self):
    self.host.policy_present=True
    self.host.policy=""
    self.assertFalse(self.admit()(self.plan).allowed)

  def test_specific_ticket_admitted_without_descendant_expansion(self):
    self.host.policy_present=True
    self.host.policy="123\n"
    self.assertTrue(self.admit()(self.plan).allowed)
    self.host.policy="124\n"
    self.assertFalse(self.admit()(self.plan).allowed)

  def test_policy_changed_between_preflight_and_acceptance(self):
    admit=self.admit()
    self.assertTrue(admit(self.plan).allowed)
    self.host.policy_present=True
    self.host.policy=""
    self.assertFalse(admit(self.plan).allowed)
    self.assertEqual(len(set(x[1] for x in self.host.calls)),2)

  def test_stale_destination_rejected(self):
    self.host.tip=A
    with self.assertRaisesRegex(CurrentPolicyError,"advanced"):
      self.admit()(self.plan)

  def test_invalid_policy_is_never_implicit_permission(self):
    self.host.policy_present=True
    self.host.policy="123 124"
    with self.assertRaises(CurrentPolicyError):
      self.admit()(self.plan)

  def test_non_authoritative_parent_rejected(self):
    with self.assertRaises(CurrentPolicyError):
      bind_current_policy(self.host,self.ready,None)

  def test_provider_read_exception_denied(self):
    def reject(*args):
      raise TimeoutError("provider unavailable")
    self.host.request=reject
    with self.assertRaisesRegex(CurrentPolicyError,"UNKNOWN"):
      self.admit()(self.plan)


if __name__=="__main__":
  unittest.main()
