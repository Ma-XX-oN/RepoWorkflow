"""Distinct ART/AIT hosted receipts and independent release/MIT oracles."""
from dataclasses import replace
import unittest

from repo_workflow.done_hosted_stage_pipeline import certify_provider_stages
from repo_workflow.done_stage_hosted import HostedStageBinding
from repo_workflow.done_stage_certification import (
  CertifiedStages,VerifiedMitPolicy,VerifiedStage,StageCertificationError,
  StageFailed,MitTimedOut,
)


SOURCE="a"*40
PARENT="b"*40
EXPIRY="2027-01-01T00:00:00Z"
HOSTED={"ART":("regression-testing",101),"AIT":("integration-testing",102)}


class IssuerTests(unittest.TestCase):
  def setUp(self):
    self.required=False
    self.records=[]
    self.bindings=[]
    self.verifications=[]
    self.release_reads=[]
    self.mit_reads=[]

  def record(self,stage,source,parent):
    self.records.append((stage,source,parent))
    name,run=HOSTED[stage]
    return {"testSHA":source,"providerCandidateSHA":source,
            "providerStage":name,"providerRunId":run}

  def binding(self,stage,source,parent):
    self.bindings.append((stage,source,parent))
    return HostedStageBinding(
      stage,source,parent,HOSTED[stage][1],
      "artifact-sha256","catalogue","config","inputs",
      "provider-"+stage,EXPIRY,True)

  def verify(self,record,*,repo,stage):
    self.verifications.append((repo,stage))
    return (repo=="Org/Repo"
            and record.get("providerStage")==stage)

  def stage(self,name,source,parent,status="PASS"):
    return VerifiedStage(
      name,source,parent,status,"stage-"+name,
      "provider-evidence-"+name,"catalogue","config","inputs",
      EXPIRY,True)

  def release(self,source,parent):
    self.release_reads.append((source,parent))
    return self.stage("release",source,parent)

  def mit(self,source,parent):
    self.mit_reads.append((source,parent))
    return self.stage("MIT",source,parent)

  def policy(self,source,parent):
    return VerifiedMitPolicy(
      source,parent,self.required,"mit-policy-provider-proof",True)

  def invoke(self,**changes):
    args={
      "repository":"Org/Repo",
      "source_sha":SOURCE,"parent_sha":PARENT,
      "read_hosted_record":self.record,
      "read_hosted_binding":self.binding,
      "verify_hosted_artifact":self.verify,
      "read_release_stage":self.release,
      "read_mit_stage":self.mit,
      "read_mit_policy":self.policy,
    }
    return certify_provider_stages(**{**args,**changes})

  def test_art_ait_release_are_three_distinct_authenticated_stages(self):
    result=self.invoke()
    self.assertIsInstance(result,CertifiedStages)
    self.assertEqual([x.stage for x in result.stages],
                     ["ART","AIT","release"])
    self.assertEqual([x[0] for x in self.records],["ART","AIT"])
    self.assertEqual(len(self.bindings),4)
    self.assertEqual(len(self.verifications),2)
    self.assertEqual(self.release_reads,[(SOURCE,PARENT)])
    self.assertEqual(self.mit_reads,[])

  def test_required_mit_uses_separate_authenticated_issuer(self):
    self.required=True
    result=self.invoke()
    self.assertEqual([x.stage for x in result.stages],
                     ["ART","AIT","release","MIT"])
    self.assertEqual(self.mit_reads,[(SOURCE,PARENT)])

  def test_missing_release_authority_never_reuses_art_receipt(self):
    with self.assertRaisesRegex(StageCertificationError,"authorities"):
      self.invoke(read_release_stage=None)
    self.assertEqual(self.records,[])

  def test_missing_mit_receipt_never_defaults_to_pass(self):
    self.required=True
    with self.assertRaisesRegex(StageCertificationError,"MIT provider"):
      self.invoke(read_mit_stage=lambda *args:None)

  def test_failed_release_is_not_a_valid_integration(self):
    def failed(source,parent):
      return self.stage("release",source,parent,"FAIL")
    with self.assertRaises(StageFailed) as context:
      self.invoke(read_release_stage=failed)
    self.assertEqual(context.exception.stage,"release")

  def test_mit_timeout_is_distinct_from_real_failure(self):
    self.required=True
    def timeout(source,parent):
      return self.stage("MIT",source,parent,"TIMEOUT")
    with self.assertRaises(MitTimedOut) as context:
      self.invoke(read_mit_stage=timeout)
    self.assertEqual(context.exception.evidence_ref,"provider-evidence-MIT")

  def test_unverified_hosted_artifact_cannot_authorize_cas(self):
    with self.assertRaisesRegex(StageCertificationError,"ART provider"):
      self.invoke(verify_hosted_artifact=lambda *a,**k:False)
    self.assertEqual(self.release_reads,[])

  def test_hosted_binding_change_between_reads_fails_closed(self):
    reads=[]
    def changed(stage,source,parent):
      observed=self.binding(stage,source,parent)
      reads.append(stage)
      if len(reads)==2:
        return replace(observed,evidence_ref="changed-provider-proof")
      return observed
    with self.assertRaisesRegex(StageCertificationError,"ART provider"):
      self.invoke(read_hosted_binding=changed)
    self.assertEqual(self.release_reads,[])

  def test_release_input_digest_cannot_differ_from_art_ait(self):
    def different(source,parent):
      return replace(self.stage("release",source,parent),
                     inputs_digest="different-material-input")
    with self.assertRaisesRegex(StageCertificationError,"material test"):
      self.invoke(read_release_stage=different)

  def test_unverified_mit_policy_rejected_before_stage_issuance(self):
    def untrusted(source,parent):
      return replace(self.policy(source,parent),
                     independently_authenticated=False)
    with self.assertRaisesRegex(StageCertificationError,"MIT requirement"):
      self.invoke(read_mit_policy=untrusted)
    self.assertEqual(self.records,[])

  def test_invalid_source_sha_cannot_query_any_provider(self):
    with self.assertRaisesRegex(StageCertificationError,"invalid exact source"):
      self.invoke(source_sha="not-sha")
    self.assertEqual(self.records,[])


if __name__=="__main__":
  unittest.main()
