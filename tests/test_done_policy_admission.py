"""Current destination policy and immediate-child admission contract."""
import unittest

from repo_workflow.done_policy_admission import (
  DestinationPolicyError, current_destination_admission,
)
from repo_workflow.done_planner import DonePlan

A="a"*40
B="b"*40


class Host:
  def __init__(self):
    self.calls=[]
    self.observation={
      "destination":"main","ref":"refs/heads/main",
      "sha":A,"policy_present":False,"policy_text":None}
  def request(self,op,key,params):
    self.calls.append((op,key,params))
    return dict(self.observation)


class PolicyTests(unittest.TestCase):
  def setUp(self):
    self.host=Host()
    self.plan=DonePlan(
      "123","patch","main",B,A,"ALLOWED",True,False,None,(),())
    self.relationship_calls=[]
  def invoke(self,parent=True):
    def relationship(issue,target):
      self.relationship_calls.append((issue,target))
      return parent
    return current_destination_admission(
      self.host,self.plan,relationship)

  def test_absent_policy_allows_verified_immediate_child(self):
    self.assertTrue(self.invoke().allowed)
    self.assertEqual(self.relationship_calls,[("123","main")])

  def test_empty_policy_does_not_mean_absent(self):
    self.host.observation.update(policy_present=True,policy_text="")
    self.assertFalse(self.invoke().allowed)
    self.assertEqual(self.relationship_calls,[])

  def test_present_list_requires_explicit_immediate_child(self):
    self.host.observation.update(
      policy_present=True,policy_text="123\n456\n")
    self.assertTrue(self.invoke().allowed)
    self.assertFalse(self.invoke(parent=False).allowed)
    self.host.observation["policy_text"]="456\n"
    self.assertFalse(self.invoke().allowed)

  def test_policy_checked_afresh_at_each_acceptance(self):
    self.assertTrue(self.invoke().allowed)
    self.host.observation.update(
      policy_present=True,policy_text="456\n")
    self.assertFalse(self.invoke().allowed)
    self.assertEqual(len(self.host.calls),2)

  def test_provider_read_memoization_cannot_hide_policy_revocation(self):
    seen={}
    original=self.host.request

    def memoized(op,key,params):
      if key not in seen:
        seen[key]=original(op,key,params)
      return dict(seen[key])

    self.host.request=memoized
    self.assertTrue(self.invoke().allowed)
    self.host.observation.update(
      policy_present=True,policy_text="")
    self.assertFalse(self.invoke().allowed)
    self.assertEqual(len(seen),2)
    self.assertEqual(len({key for op,key,args in self.host.calls}),2)

  def test_changed_parent_never_admitted(self):
    self.host.observation["sha"]=B
    self.assertFalse(self.invoke().allowed)
    self.assertEqual(self.relationship_calls,[])

  def test_malformed_present_lists_are_rejected(self):
    for value in ("123 # comment","0123","123\n123","\n123",
                  "123\nfoo"," 123","123\n\n456"):
      self.host.observation.update(
        policy_present=True,policy_text=value)
      with self.subTest(value=value):
        with self.assertRaises(DestinationPolicyError):
          self.invoke()

  def test_foreign_or_malformed_provider_observation_denied(self):
    for field,value in (("destination","other"),
                        ("ref","refs/heads/other"),
                        ("policy_present",1),("policy_text","forged")):
      prior=dict(self.host.observation)
      self.host.observation[field]=value
      with self.subTest(field=field):
        with self.assertRaises(DestinationPolicyError):
          self.invoke()
      self.host.observation=prior

  def test_graph_oracle_must_be_verified_boolean(self):
    with self.assertRaisesRegex(DestinationPolicyError,"verdict"):
      current_destination_admission(
        self.host,self.plan,lambda issue,target:None)


if __name__=="__main__":
  unittest.main()
