"""End-to-end local v2 transport simulation for a single READY attempt.

This is not authenticated provider certification or #103 ref cleanup.
"""
import unittest

from repo_workflow.done_executor import CertifiedAttempt, DoneExecutionError
from repo_workflow.done_planner import DonePlan
from repo_workflow.done_stage_certification import MitTimedOut
from repo_workflow.done_provider_pipeline import DeferredProviderAttempt
from repo_workflow.done_provider_acceptance import DestinationAcceptanceFacts
from repo_workflow.done_provider_pipeline import accept_one_ready_submission
from repo_workflow.done_stage_certification import (
  CertifiedStages, VerifiedMitPolicy, VerifiedStage, MitTimedOut,
)
from repo_workflow.integration_admission import AdmissionDecision
from repo_workflow.prelim_queue import parse_ready_prelim


G = "11111111-1111-4111-8111-111111111111"
P = f"refs/heads/PRELIM-issue-123/main-{G}"
I = P.replace("PRELIM-", "INT-ATTEMPT-")
A, B, C, D = ("a"*40, "b"*40, "c"*40, "d"*40)


class Provider:
  repository = "Org/Repo"
  def __init__(self):
    self.main = B
    self.int_sha = None
    self.terminal = None
    self.deferred = None
    self.lease = {"destination":"main","generation":0,
                  "holder":None,"guid":None}
    self.calls = []
    self.fail = None
    self.policy_present = False
    self.policy_text = None
    self.policy_reads = 0
  def request(self, operation, key, p):
    self.calls.append(operation)
    if operation == self.fail:
      raise ConnectionError("UNKNOWN")
    if operation == "refs.list":
      return {"refs":{P:A}}
    if operation == "lease.read":
      return dict(self.lease)
    if operation == "lease.cas":
      if (self.lease["generation"] != p["expected_generation"]
          or self.lease["guid"] != p["expected_guid"]
          or self.lease["holder"] != p["expected_holder"]):
        raise ValueError("stale lease")
      self.lease = {"destination":"main",
                    "generation":p["expected_generation"]+1,
                    "holder":p["holder"],"guid":p["guid"]}
      return dict(self.lease)
    if operation == "attempt.read":
      return {"guid":G,"record":self.terminal}
    if operation == "mit.deferred.record":
      self.deferred = dict(p["event"])
      return dict(p)
    if operation in ("mit.deferred.read","mit.resume.read"):
      return {"guid":G,"destination":"main",
              "event" if operation=="mit.deferred.read"
              else "authorization":self.deferred if operation=="mit.deferred.read"
              else None}
    if operation == "destination.read":
      self.policy_reads += 1
      return {"destination":"main","ref":"refs/heads/main",
              "sha":self.main,"policy_present":self.policy_present,
              "policy_text":self.policy_text}
    if operation == "ref.create":
      self.int_sha = p["sha"]
      return {"ref":p["ref"],"sha":self.int_sha}
    if operation == "ref.cas":
      assert p["expected_sha"] == self.int_sha
      self.int_sha = p["sha"]
      return {"ref":p["ref"],"sha":self.int_sha}
    if operation == "destination.accept":
      assert p["record"]["accepted_sha"] == self.int_sha
      assert p["record"]["expected_destination_sha"] == self.main
      self.main = p["record"]["proposed_sha"]
      return {"destination":"main","expected_sha":B,
              "landed_sha":D,"operation_id":"op-1"}
    if operation == "attempt.record":
      self.terminal = p["record"]
      return {"guid":G,"record":self.terminal}
    raise AssertionError(operation)


class PipelineTests(unittest.TestCase):
  def setUp(self):
    self.host = Provider()
    self.ready = parse_ready_prelim(P,A)
    self.plan = DonePlan(
      "123","patch","main",A,B,"ALLOWED",True,False,None,(),())
    self.calls = {"prepare":0}
  def invoke(self, **overrides):
    def prepare(plan):
      self.calls["prepare"] += 1
      return CertifiedAttempt(A,I,C,B,"tests-1","auth-1",
                              "op-1",P)
    args = {
      "host":self.host,"ready":self.ready,"holder":"worker-A",
      "original_plan":self.plan,"refresh_plan":lambda:self.plan,
      "prepare_and_certify":prepare,
      "admission_check":lambda p:AdmissionDecision(
        123,"main",B,True,"admitted"),
      "provider_facts":DestinationAcceptanceFacts(
        "Org/Repo",123,"main",G,1,"worker-A",D),
      "verify_provider_result":lambda *a:True,
      "immediate_parent_oracle":lambda issue,target: (
        issue=="123" and target=="main"),
      "stage_certify":lambda source,parent:CertifiedStages(
        source,parent,tuple(VerifiedStage(
          name,source,parent,"PASS","run-"+name,"proof-"+name,
          "catalogue","config","inputs","2027-01-01T00:00:00Z",True)
          for name in ("ART","AIT","release")),
        VerifiedMitPolicy(source,parent,False,"policy-ref",True)),
      "create_id":"create-1","update_id":"update-1",
      "integration_id":"integration-1",
      "terminal_evidence_ref":"terminal-proof-1",
      "terminal_request_id":"terminal-1",
    }
    return accept_one_ready_submission(**{**args,**overrides})

  def test_mit_timeout_persists_deferral_and_releases_lease(self):
    def timeout(plan):
      raise MitTimedOut("independent-mit-timeout-1")
    result=self.invoke(
      prepare_and_certify=timeout,
      mit_event_request_id="mit-defer-1",
      mit_read_request_id="mit-read-1")
    self.assertIsInstance(result,DeferredProviderAttempt)
    self.assertEqual(result.released_generation,2)
    self.assertEqual(self.host.deferred["reason"],"timeout")
    self.assertEqual(self.host.main,B)
    self.assertIsNone(self.host.terminal)
    self.assertEqual(self.host.lease["holder"],None)

  def test_mit_timeout_missing_event_ids_does_not_release(self):
    def timeout(plan):
      raise MitTimedOut("independent-mit-timeout-2")
    with self.assertRaisesRegex(DoneExecutionError,"event IDs"):
      self.invoke(prepare_and_certify=timeout)
    self.assertIsNone(self.host.deferred)
    self.assertEqual(self.host.lease["generation"],1)
    self.assertEqual(self.host.main,B)

  def test_one_ready_end_to_end_local_provider_simulation(self):
    result=self.invoke()
    self.assertEqual(result.accepted.landed_sha,D)
    self.assertEqual(result.terminal.accepted_sha,C)
    self.assertEqual(self.host.terminal["status"],"integrated")
    self.assertEqual(self.host.main,D)
    self.assertEqual(self.host.lease["generation"],2)
    self.assertIsNone(self.host.lease["holder"])
    self.assertEqual(self.calls["prepare"],1)

  def test_no_authenticated_stage_oracle_cannot_mutate_int(self):
    with self.assertRaisesRegex(DoneExecutionError,"mandatory"):
      self.invoke(stage_certify=None)
    self.assertIsNone(self.host.int_sha)
    self.assertEqual(self.host.main,B)

  def test_foreign_stage_identity_cannot_mutate_int(self):
    bad=lambda source,parent:CertifiedStages(
      B,parent,(),VerifiedMitPolicy(B,parent,False,"policy-ref",True))
    with self.assertRaisesRegex(DoneExecutionError,"stage identity"):
      self.invoke(stage_certify=bad)
    self.assertIsNone(self.host.int_sha)

  def test_empty_current_policy_denies_before_int(self):
    self.host.policy_present=True
    self.host.policy_text=""
    with self.assertRaisesRegex(DoneExecutionError,"policy denied"):
      self.invoke()
    self.assertIsNone(self.host.int_sha)
    self.assertEqual(self.host.main,B)

  def test_current_policy_change_refuses_landing(self):
    original=self.host.request
    def change_policy(op,key,params):
      if op=="destination.read" and self.host.policy_reads>=2:
        self.host.policy_present=True
        self.host.policy_text="456"
      return original(op,key,params)
    self.host.request=change_policy
    with self.assertRaisesRegex(DoneExecutionError,"policy denied"):
      self.invoke()
    self.assertEqual(self.host.main,B)

  def test_immediate_child_verdict_is_mandatory(self):
    with self.assertRaisesRegex(DoneExecutionError,"parent oracle"):
      self.invoke(immediate_parent_oracle=None)
    self.assertIsNone(self.host.int_sha)

  def test_missing_current_ready_prevents_claim(self):
    original=self.host.request
    def missing(op,key,params):
      if op=="refs.list":
        return {"refs":{}}
      return original(op,key,params)
    self.host.request=missing
    with self.assertRaisesRegex(DoneExecutionError,"READY physical"):
      self.invoke()
    self.assertEqual(self.host.lease["generation"],0)

  def test_failing_terminal_leaves_lease_for_recovery(self):
    self.host.fail="attempt.record"
    with self.assertRaises(Exception):
      self.invoke()
    self.assertEqual(self.host.main,D)
    self.assertEqual(self.host.lease["holder"],"worker-A")

  def test_foreign_authority_denied_without_acquiring_lease(self):
    variations = (
      DestinationAcceptanceFacts(
        "Other/Repo",123,"main",G,1,"worker-A",D),
      DestinationAcceptanceFacts(
        "Org/Repo",124,"main",G,1,"worker-A",D),
      DestinationAcceptanceFacts(
        "Org/Repo",123,"other",G,1,"worker-A",D),
      DestinationAcceptanceFacts(
        "Org/Repo",123,"main",G,1,"worker-Z",D),
    )
    for facts in variations:
      with self.subTest(facts=facts):
        with self.assertRaisesRegex(
            DoneExecutionError,"before lease claim"):
          self.invoke(provider_facts=facts)
    self.assertEqual(self.host.lease["generation"],0)
    self.assertEqual(self.host.main,B)

  def test_cross_submission_plan_denied_before_lease(self):
    other = DonePlan(
      "124","patch","main",A,B,"ALLOWED",True,False,None,(),())
    with self.assertRaisesRegex(
        DoneExecutionError, "before lease claim"):
      self.invoke(original_plan=other)
    self.assertEqual(self.host.lease["generation"],0)

  def test_wrong_lease_generation_rejected_without_destination_mutation(self):
    wrong=DestinationAcceptanceFacts(
      "Org/Repo",123,"main",G,9,"worker-A",D)
    with self.assertRaisesRegex(DoneExecutionError,"lease"):
      self.invoke(provider_facts=wrong)
    self.assertEqual(self.host.main,B)


if __name__=="__main__":
  unittest.main()
