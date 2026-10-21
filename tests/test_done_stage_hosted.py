"""Provider-authenticated hosted ART/AIT stage evidence bridge."""
from dataclasses import replace
import unittest

from repo_workflow.done_stage_hosted import (
  HostedStageBinding,HostedStageError,verified_hosted_automatic_stage,
)

A,B=("a"*40,"b"*40)


class HostedTests(unittest.TestCase):
  def setUp(self):
    self.stage="ART"
    self.proof={
      "testSHA":A,"providerCandidateSHA":A,
      "providerStage":"regression-testing","providerRunId":123,
      "runner":"github-actions","result":"succeeded"}
    self.bound=HostedStageBinding(
      "ART",A,B,123,"artifact-123","catalogue","config",
      "inputs","provider-evidence","2027-12-01T00:00:00Z",True)
    self.events=[]
    self.change_binding=False

  def read_record(self,stage,source,parent):
    self.events.append("record")
    return self.proof

  def read_binding(self,stage,source,parent):
    self.events.append("binding")
    if self.change_binding and self.events.count("binding")>=2:
      return replace(self.bound,inputs_digest="changed-inputs")
    return self.bound

  def verifier(self,record,*,repo,stage):
    self.events.append("artifact")
    return (repo=="Org/Repo" and stage=="regression-testing"
            and record==self.proof)

  def run(self,**changes):
    params={
      "repository":"Org/Repo","stage":"ART",
      "tested_sha":A,"expected_parent_sha":B,
      "read_record":self.read_record,
      "read_binding":self.read_binding,
      "verify_artifact":self.verifier,
    }
    return verified_hosted_automatic_stage(**{**params,**changes})

  def test_exact_artifact_and_parent_provider_observations(self):
    result=self.run()
    self.assertEqual(result.status,"PASS")
    self.assertEqual(result.source_sha,A)
    self.assertEqual(result.parent_sha,B)
    self.assertEqual(result.provider_run_id,"123")
    self.assertEqual(self.events,["record","binding","artifact","binding"])

  def test_mit_and_release_are_not_auto_certified_from_regression(self):
    for stage in ("MIT","release","GREEN"):
      with self.subTest(stage=stage):
        with self.assertRaisesRegex(HostedStageError,"exact hosted"):
          self.run(stage=stage)
    self.assertEqual(self.events,[])

  def test_foreign_candidate_or_source_never_passes(self):
    self.proof["providerCandidateSHA"]=B
    with self.assertRaisesRegex(HostedStageError,"foreign"):
      self.run()
    self.assertNotIn("artifact",self.events)

  def test_foreign_parent_binding_never_passes(self):
    self.bound=replace(self.bound,expected_parent_sha=A)
    with self.assertRaisesRegex(HostedStageError,"foreign"):
      self.run()
    self.assertNotIn("artifact",self.events)

  def test_actual_artifact_fails_even_if_provider_run_claims_pass(self):
    with self.assertRaisesRegex(HostedStageError,"not independently PASS"):
      self.run(verify_artifact=lambda *a,**k:False)

  def test_missing_or_unsigned_binding_refused(self):
    self.bound=replace(self.bound,independently_authenticated=False)
    with self.assertRaisesRegex(HostedStageError,"unverified"):
      self.run()

  def test_changed_binding_during_remote_artifact_verification_refused(self):
    self.change_binding=True
    with self.assertRaisesRegex(HostedStageError,"changed"):
      self.run()

  def test_provider_or_verifier_exception_is_unknown_not_pass(self):
    with self.assertRaisesRegex(HostedStageError,"UNKNOWN"):
      self.run(read_record=lambda *x:(_ for _ in ()).throw(
        ConnectionError("unavailable")))
    with self.assertRaisesRegex(HostedStageError,"UNKNOWN"):
      self.run(verify_artifact=lambda *a,**k:(_ for _ in ()).throw(
        TimeoutError("artifact unavailable")))


if __name__=="__main__":
  unittest.main()
