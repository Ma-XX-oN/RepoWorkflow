"""Provider-observed immutable release, integration, regression promotion."""
from dataclasses import replace
import unittest

from repo_workflow.done_evidence_provider import (
  VerifiedLanding, promote_from_provider,
)
from repo_workflow.done_evidence_promotion import (
  AuthenticatedStage, PromotionError,
)


A, B, C, D = ("a"*40,"b"*40,"c"*40,"d"*40)


class Provider:
  def __init__(self):
    self.landing=VerifiedLanding(
      "operation-1",A,B,C,D,A,A,"context-1",True,True)
    self.stages={name:AuthenticatedStage(
      name,A,"hosted-run-"+name,"artifact-"+name,
      "catalogue-1","config-1","inputs-1",
      "2027-04-01T00:00:00Z","PASS",True)
      for name in ("regression","integration","release")}
    self.persisted={}
    self.events=[]
    self.fail_publish=False
    self.corrupt_after_persist=False
    self.move_landing_after_persist=False

  def landing_reader(self,operation):
    self.events.append(("landing",operation))
    return self.landing

  def stage_reader(self,name,source):
    self.events.append(("stage",name,source))
    return self.stages.get(name)

  def persist(self,record):
    self.events.append(("persist",record.operation_id))
    self.persisted[record.operation_id]=record
    if self.corrupt_after_persist:
      self.stages["release"]=replace(
        self.stages["release"],artifact_digest="changed-artifact")
    if self.move_landing_after_persist:
      self.landing=replace(self.landing,landed_sha=B)
    if self.fail_publish:
      raise TimeoutError("ACK dropped after append")

  def readback(self,key):
    self.events.append(("readback",key))
    return self.persisted.get(key)

  def invoke(self,**overrides):
    kwargs={
      "operation_id":"operation-1",
      "tested_source_sha":A,
      "read_landing":self.landing_reader,
      "read_stage":self.stage_reader,
      "persist":self.persist,
      "readback":self.readback,
    }
    return promote_from_provider(**{**kwargs,**overrides})


class ProviderEvidenceTests(unittest.TestCase):
  def setUp(self):
    self.p=Provider()

  def test_independently_read_each_stage_and_promote_exact_source(self):
    record=self.p.invoke()
    self.assertEqual(record.tested_source_sha,A)
    self.assertEqual(record.accepted_candidate_sha,B)
    self.assertEqual(record.landed_sha,D)
    self.assertEqual(record.disposition,
                     "source-tested-accepted-at-destination")
    self.assertEqual(len([e for e in self.p.events
                          if e[0]=="stage"]),6)
    self.assertEqual(len([e for e in self.p.events
                          if e[0]=="persist"]),1)

  def test_missing_separate_release_stage_never_promoted(self):
    self.p.stages.pop("release")
    with self.assertRaisesRegex(PromotionError,"absent stage"):
      self.p.invoke()
    self.assertFalse(self.p.persisted)

  def test_independent_stage_must_be_authenticated(self):
    for name in ("regression","integration","release"):
      old=self.p.stages[name]
      self.p.stages[name]=replace(old,authenticated=False)
      with self.subTest(name=name):
        with self.assertRaisesRegex(PromotionError,"unauthenticated"):
          self.p.invoke()
      self.p.stages[name]=old
    self.assertFalse(self.p.persisted)

  def test_mixed_tested_sha_or_provider_operation_denied(self):
    self.p.landing=replace(self.p.landing,operation_id="other-op")
    with self.assertRaisesRegex(PromotionError,"differs"):
      self.p.invoke()
    self.p.landing=replace(self.p.landing,operation_id="operation-1")
    self.p.stages["integration"]=replace(
      self.p.stages["integration"],source_sha=C)
    with self.assertRaisesRegex(PromotionError,"foreign"):
      self.p.invoke()
    self.assertFalse(self.p.persisted)

  def test_changed_landed_tree_prevents_promotion(self):
    self.p.landing=replace(self.p.landing,landed_tree_sha=C)
    with self.assertRaisesRegex(PromotionError,"not equivalent"):
      self.p.invoke()
    self.assertFalse(self.p.persisted)

  def test_lost_ack_requires_exact_durable_readback(self):
    self.p.fail_publish=True
    self.assertEqual(self.p.invoke(),self.p.persisted["operation-1"])
    self.assertEqual([e[0] for e in self.p.events].count("persist"),1)

  def test_changed_evidence_after_append_cannot_be_certified(self):
    self.p.corrupt_after_persist=True
    with self.assertRaisesRegex(PromotionError,"changed during"):
      self.p.invoke()
    self.assertIn("operation-1",self.p.persisted)

  def test_changed_destination_after_promotion_fails_closed(self):
    self.p.move_landing_after_persist=True
    with self.assertRaisesRegex(PromotionError,"landing changed"):
      self.p.invoke()
    self.assertIn("operation-1",self.p.persisted)

  def test_missing_provider_oracle_denied(self):
    for callback in ("read_landing","read_stage","persist","readback"):
      with self.subTest(callback=callback):
        with self.assertRaisesRegex(PromotionError,"independent provider"):
          self.p.invoke(**{callback:None})
    self.assertFalse(self.p.persisted)

  def test_no_user_supplied_stage_boolean_can_substitute_for_oracle(self):
    with self.assertRaisesRegex(PromotionError,"independent provider"):
      self.p.invoke(read_stage=True)
    self.assertFalse(self.p.persisted)


if __name__=="__main__":
  unittest.main()
