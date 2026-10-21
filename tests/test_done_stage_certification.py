"""Exact-source ART/AIT/MIT provider decision tests."""
from dataclasses import replace
import unittest

from repo_workflow.done_stage_certification import (
  MitTimedOut, StageCertificationError, StageFailed,
  VerifiedMitPolicy, VerifiedStage, certify_stages,
)

A="a"*40
B="b"*40


class Stages(unittest.TestCase):
  def setUp(self):
    self.policy=VerifiedMitPolicy(A,B,True,"mit-policy",True)
    self.stage={name:VerifiedStage(
      name,A,B,"PASS","run-"+name,"proof-"+name,
      "cat","config","inputs","2027-01-01T00:00:00Z",True)
      for name in ("ART","AIT","release","MIT")}

  def certify(self):
    return certify_stages(
      source_sha=A,parent_sha=B,
      read_stage=lambda n,s,p:self.stage.get(n),
      read_mit_policy=lambda s,p:self.policy)

  def test_all_authenticated_stages_pass(self):
    self.assertEqual(len(self.certify().stages),4)

  def test_mit_not_required_never_forges_pass(self):
    self.policy=replace(self.policy,required=False)
    del self.stage["MIT"]
    self.assertEqual(len(self.certify().stages),3)

  def test_required_mit_timeout_distinct_from_failure(self):
    self.stage["MIT"]=replace(self.stage["MIT"],status="TIMEOUT")
    with self.assertRaises(MitTimedOut):
      self.certify()
    self.stage["MIT"]=replace(self.stage["MIT"],status="FAIL")
    with self.assertRaises(StageFailed):
      self.certify()

  def test_missing_independent_release_proof_denied(self):
    del self.stage["release"]
    with self.assertRaises(StageCertificationError):
      self.certify()

  def test_stale_candidate_or_unsigned_stage_denied(self):
    self.stage["AIT"]=replace(self.stage["AIT"],source_sha=B)
    with self.assertRaises(StageCertificationError):
      self.certify()
    self.stage["AIT"]=replace(
      self.stage["AIT"],source_sha=A,independently_authenticated=False)
    with self.assertRaises(StageCertificationError):
      self.certify()

  def test_unverified_policy_cannot_skip_mit(self):
    self.policy=replace(self.policy,required=False,
                        independently_authenticated=False)
    with self.assertRaises(StageCertificationError):
      self.certify()

  def test_changed_inputs_denied(self):
    self.stage["release"]=replace(
      self.stage["release"],inputs_digest="other")
    with self.assertRaises(StageCertificationError):
      self.certify()


if __name__=="__main__":
  unittest.main()
