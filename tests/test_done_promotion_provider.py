"""Provider create-once promotion attestation, no synthetic hosted PASS."""
from dataclasses import replace
import hashlib
import unittest

from adapters.repo_host_github_done_promotion import (
  DonePromotionProviderError, read_done_promotion,record_done_promotion,_ref,
)
from repo_workflow.done_evidence_promotion import (
  AuthenticatedStage, Promotion,
)

A,B,C=("a"*40,"b"*40,"c"*40)
TREE="d"*40


class NotFound(Exception):
  code="not_found"


class Backend:
  repository="Org/Repo"
  def __init__(self):
    self.refs={"refs/heads/main":B}
    self.commits={
      B:{"tree":{"sha":TREE},"message":"landed","parents":[]},
      A:{"tree":{"sha":TREE},"message":"tested","parents":[]},
    }
    self.posts=[]
    self.lost_tag_ack=False
  def get(self,route):
    if route.startswith("git/ref/"):
      ref="refs/"+route.removeprefix("git/ref/")
      if ref not in self.refs:
        raise NotFound()
      return {"ref":ref,"object":{"sha":self.refs[ref]}}
    if route.startswith("git/commits/"):
      return self.commits[route.removeprefix("git/commits/")]
    raise AssertionError(route)
  def post(self,route,record):
    self.posts.append((route,record))
    if route=="git/commits":
      digest=hashlib.sha1(record["message"].encode()).hexdigest()
      self.commits[digest]={
        "tree":{"sha":record["tree"]},"message":record["message"],
        "parents":[{"sha":p} for p in record["parents"]]}
      return {"sha":digest}
    if route=="git/refs":
      if record["ref"] in self.refs:
        raise RuntimeError("already exists")
      self.refs[record["ref"]]=record["sha"]
      if self.lost_tag_ack:
        raise TimeoutError("commit persisted, ACK dropped")
      return {"ref":record["ref"],"object":{"sha":record["sha"]}}
    raise AssertionError(route)


def promotion():
  return Promotion(
    "operation-1",A,A,C,B,TREE,TREE,"context",tuple(
      AuthenticatedStage(
        name,A,"run-"+name,"artifact-"+name,"catalogue",
        "config","inputs","2027-01-01T00:00:00Z","PASS",True)
      for name in ("regression","integration","release")))


class ProviderPromotionTests(unittest.TestCase):
  def setUp(self):
    self.b=Backend()
    self.proof=promotion()
    self.evidence_calls=0
    self.landing_calls=0
  def landing(self,proof,destination):
    self.landing_calls += 1
    return proof==self.proof and destination=="main"
  def evidence(self,proof):
    self.evidence_calls += 1
    return proof==self.proof
  def publish(self,**changes):
    args={
      "verify_landing":self.landing,
      "verify_stages":self.evidence,
    }
    return record_done_promotion(
      self.b,"main",self.proof,**{**args,**changes})

  def test_append_only_promotion_readback_preserves_main_and_source(self):
    result=self.publish()
    self.assertEqual(result,self.proof)
    self.assertEqual(self.b.refs["refs/heads/main"],B)
    self.assertEqual(read_done_promotion(
      self.b,"main","operation-1"),self.proof)
    self.assertEqual(result.tested_source_sha,A)
    self.assertNotEqual(result.tested_source_sha,result.landed_sha)
    self.assertEqual([r for r,_ in self.b.posts],
                     ["git/commits","git/refs"])

  def test_identical_retry_is_one_immutable_ref(self):
    self.publish()
    self.publish()
    self.assertEqual(len(self.b.posts),2)
    self.assertEqual(self.b.refs["refs/heads/main"],B)

  def test_lost_reply_reconciles_exact_tag_without_second_write(self):
    self.b.lost_tag_ack=True
    self.assertEqual(self.publish(),self.proof)
    self.assertEqual(len(self.b.posts),2)

  def test_forged_release_and_wrong_tree_refuse_to_publish(self):
    bad=replace(self.proof,stages=tuple(
      replace(s,authenticated=False) if s.stage=="release" else s
      for s in self.proof.stages))
    with self.assertRaises(DonePromotionProviderError):
      record_done_promotion(self.b,"main",bad,
        verify_landing=lambda *_:True,verify_stages=lambda *_:True)
    with self.assertRaises(DonePromotionProviderError):
      record_done_promotion(self.b,"main",replace(
        self.proof,landed_tree_sha=A,source_tree_sha=A),
        verify_landing=lambda *_:True,verify_stages=lambda *_:True)
    self.assertEqual(self.b.posts,[])

  def test_target_changed_blocks_before_append(self):
    self.b.refs["refs/heads/main"]=A
    with self.assertRaisesRegex(
        DonePromotionProviderError,"no longer current"):
      self.publish()
    self.assertEqual(self.b.posts,[])

  def test_denied_independent_hosted_evidence_never_appended(self):
    with self.assertRaisesRegex(
        DonePromotionProviderError,"not independently"):
      self.publish(verify_stages=lambda *_:False)
    self.assertEqual(self.b.posts,[])

  def test_missing_verifier_is_not_authorization(self):
    with self.assertRaisesRegex(
        DonePromotionProviderError,"verifiers required"):
      self.publish(verify_landing=None)
    self.assertEqual(self.b.posts,[])

  def test_prior_operation_mismatched_evidence_is_rejected(self):
    self.publish()
    other=replace(self.proof,context_digest="different")
    with self.assertRaisesRegex(
        DonePromotionProviderError,"foreign record"):
      record_done_promotion(self.b,"main",other,
        verify_landing=lambda *_:True,verify_stages=lambda *_:True)
    self.assertEqual(len(self.b.posts),2)

  def test_tag_pointing_to_wrong_parent_is_not_canonical_promotion(self):
    self.publish()
    ref=_ref(self.b.repository,"main","operation-1")
    sha=self.b.refs[ref]
    self.b.commits[sha]["parents"]=[{"sha":A}]
    with self.assertRaisesRegex(
        DonePromotionProviderError,"ancestry"):
      read_done_promotion(self.b,"main","operation-1")

  def test_tag_tree_mismatch_fails_closed(self):
    self.publish()
    ref=_ref(self.b.repository,"main","operation-1")
    self.b.commits[self.b.refs[ref]]["tree"]={"sha":A}
    with self.assertRaisesRegex(
        DonePromotionProviderError,"ancestry or tree"):
      read_done_promotion(self.b,"main","operation-1")

  def test_tested_candidate_tree_changed_prevents_append(self):
    self.b.commits[A]["tree"]={"sha":A}
    with self.assertRaisesRegex(
        DonePromotionProviderError,"original tested"):
      self.publish()
    self.assertEqual(self.b.posts,[])

  def test_lost_ack_with_advanced_destination_does_not_claim_promotion(self):
    original=self.b.post
    def racing(route,record):
      if route=="git/refs":
        self.b.lost_tag_ack=True
        self.b.refs["refs/heads/main"]=C
      return original(route,record)
    self.b.post=racing
    with self.assertRaisesRegex(
        DonePromotionProviderError,"destination advanced"):
      self.publish()
    self.assertEqual(self.b.refs["refs/heads/main"],C)

  def test_corrupted_existing_provider_tag_cannot_count_as_success(self):
    self.publish()
    ref=_ref(self.b.repository,"main","operation-1")
    self.b.refs[ref]=B
    with self.assertRaises(DonePromotionProviderError):
      self.publish()


if __name__=="__main__":
  unittest.main()
