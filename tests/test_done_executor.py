"""Exact-candidate mutation guard tests for #109's first executor boundary."""
from dataclasses import replace
import unittest

from repo_workflow.done_planner import DonePlan
from repo_workflow.integration_admission import AdmissionDecision
from repo_workflow.done_executor import (
  AcceptedIntegration, CertifiedAttempt, DoneExecutionError,
  execute_certified_done,
)


A = "a" * 40
B = "b" * 40
C = "c" * 40
D = "d" * 40
INT = "refs/heads/INT-ATTEMPT-issue-123/main-11111111-1111-4111-8111-111111111111"


class ExecutionGuardTests(unittest.TestCase):
  def setUp(self):
    self.plan = DonePlan(
      "123", "patch", "main", A, B, "ALLOWED",
      True, False, None, (), (),
    )
    self.attempt = CertifiedAttempt(
      A, INT, C, B, "evidence-1", "auth-1", "operation-1")
    self.calls = []

  def execute(self, **changes):
    original = changes.get("original", self.plan)
    refresh = changes.get("fresh", self.plan)
    attempt = changes.get("attempt", self.attempt)
    admission = changes.get("admission", AdmissionDecision(
      123, "main", B, True, "ticket explicitly admitted",
    ))
    response = changes.get(
      "response", AcceptedIntegration(D, True, "operation-1"),
    )
    def integrate(*args):
      self.calls.append(args)
      return response
    return execute_certified_done(
      original,
      lambda: refresh,
      lambda p: attempt,
      lambda p: admission,
      integrate,
      lambda p, a, result: True,
    )

  def test_accepted_attempt_carries_expected_old_parent(self):
    accepted = self.execute()
    self.assertEqual(accepted.landed_sha, D)
    self.assertEqual(self.calls[0][3], B)
    self.assertEqual(self.calls[0][1], C)

  def test_policy_denied_after_candidate_preparation(self):
    calls={"read":0,"prepare":0}
    good=AdmissionDecision(123,"main",B,True,"allowed at queue time")
    denied=AdmissionDecision(123,"main",B,False,"removed while queued")
    def check(plan):
      calls["read"]+=1
      return good if calls["read"]==1 else denied
    def prepare(plan):
      calls["prepare"]+=1
      return self.attempt
    with self.assertRaisesRegex(DoneExecutionError,"admission changed"):
      execute_certified_done(
        self.plan,lambda:self.plan,prepare,check,
        lambda *args:self.fail("must not integrate"),
        lambda *args:self.fail("must not verify"))
    self.assertEqual(calls,{"read":2,"prepare":1})

  def test_parent_advances_during_certification(self):
    count={"read":0}
    def refresh():
      count["read"]+=1
      if count["read"]==1:
        return self.plan
      return replace(self.plan,expected_parent_sha=D)
    with self.assertRaisesRegex(DoneExecutionError,"during certification"):
      execute_certified_done(
        self.plan,refresh,lambda p:self.attempt,
        lambda p:AdmissionDecision(123,"main",B,True,"initially allowed"),
        lambda *args:self.fail("must not integrate"),
        lambda *args:self.fail("must not verify"))
    self.assertEqual(count["read"],2)

  def test_post_preparation_admission_uses_new_provider_read(self):
    calls={"read":0}
    def check(plan):
      calls["read"]+=1
      return AdmissionDecision(123,"main",B,True,"current")
    result=execute_certified_done(
      self.plan,lambda:self.plan,lambda p:self.attempt,check,
      lambda *args:AcceptedIntegration(D,True,"operation-1"),
      lambda *args:True)
    self.assertEqual(result.landed_sha,D)
    self.assertEqual(calls["read"],2)

  def test_stale_destination_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(fresh=replace(self.plan, expected_parent_sha=D))
    self.assertEqual(self.calls, [])

  def test_denied_admission_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(admission=AdmissionDecision(
        123, "main", B, False, "ticket not allow-listed",
      ))
    self.assertEqual(self.calls, [])

  def test_bare_true_admission_is_not_authoritative(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(admission=True)
    self.assertEqual(self.calls, [])

  def test_stale_admission_revision_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(admission=AdmissionDecision(
        123, "main", D, True, "stale",
      ))
    self.assertEqual(self.calls, [])

  def test_wrong_ticket_admission_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(admission=AdmissionDecision(
        124, "main", B, True, "wrong child",
      ))
    self.assertEqual(self.calls, [])

  def test_foreign_int_attempt_ticket_is_rejected(self):
    foreign=replace(self.attempt,int_attempt_ref=INT.replace(
      "issue-123/", "issue-124/"))
    with self.assertRaisesRegex(DoneExecutionError,"certification provenance"):
      self.execute(attempt=foreign)
    self.assertEqual(self.calls, [])

  def test_foreign_int_attempt_destination_is_rejected(self):
    foreign=replace(self.attempt,int_attempt_ref=INT.replace(
      "/main-", "/issue-456-"))
    with self.assertRaisesRegex(DoneExecutionError,"certification provenance"):
      self.execute(attempt=foreign)
    self.assertEqual(self.calls, [])

  def test_invalid_int_attempt_guid_is_rejected(self):
    foreign=replace(self.attempt,int_attempt_ref=INT[:-36]+"malformed")
    with self.assertRaisesRegex(DoneExecutionError,"certification provenance"):
      self.execute(attempt=foreign)
    self.assertEqual(self.calls, [])

  def test_changed_prelim_source_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(attempt=replace(self.attempt, source_prelim_sha=D))
    self.assertEqual(self.calls, [])

  def test_uncertified_candidate_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(attempt=replace(self.attempt, evidence_ref=""))
    self.assertEqual(self.calls, [])

  def test_missing_operation_id_stops_before_provider_mutation(self):
    with self.assertRaisesRegex(DoneExecutionError,"certification provenance"):
      self.execute(attempt=replace(self.attempt,operation_id=None))
    self.assertEqual(self.calls, [])

  def test_foreign_provider_operation_cannot_be_accepted(self):
    with self.assertRaisesRegex(DoneExecutionError,"operation identity UNKNOWN"):
      self.execute(response=AcceptedIntegration(D,True,"foreign-operation"))
    self.assertEqual(len(self.calls),1)

  def test_provider_receives_pinned_operation_identity(self):
    self.execute()
    self.assertEqual(self.calls[0][-1],"operation-1")

  def test_unknown_remote_response_cannot_be_success(self):
    with self.assertRaisesRegex(DoneExecutionError, "UNKNOWN"):
      self.execute(response=None)
    self.assertEqual(len(self.calls), 1)

  def test_unknown_provider_response_recovers_only_exact_operation(self):
    pinned=replace(self.attempt,operation_id="operation-1")
    calls={"merge":0,"reconcile":0,"readback":0}
    def merge(*args):
      calls["merge"]+=1
      return None
    def reconcile(plan,attempt):
      calls["reconcile"]+=1
      self.assertEqual(attempt.operation_id,"operation-1")
      return AcceptedIntegration(D,True,"operation-1")
    def verify(*args):
      calls["readback"]+=1
      return True
    result=execute_certified_done(
      self.plan,lambda:self.plan,lambda p:pinned,
      lambda p:AdmissionDecision(123,"main",B,True,"current"),
      merge,verify,reconcile_unknown=reconcile)
    self.assertEqual(result.landed_sha,D)
    self.assertEqual(calls,{"merge":1,"reconcile":1,"readback":1})

  def test_unknown_provider_reconciliation_cannot_adopt_other_operation(self):
    pinned=replace(self.attempt,operation_id="operation-1")
    with self.assertRaisesRegex(DoneExecutionError,"operation identity UNKNOWN"):
      execute_certified_done(
        self.plan,lambda:self.plan,lambda p:pinned,
        lambda p:AdmissionDecision(123,"main",B,True,"current"),
        lambda *args:None,lambda *args:True,
        reconcile_unknown=lambda p,a:AcceptedIntegration(D,True,"foreign-op"))

  def test_exception_response_is_not_blindly_retried(self):
    pinned=replace(self.attempt,operation_id="operation-1")
    calls={"count":0}
    def fail(*args):
      calls["count"]+=1
      raise TimeoutError("lost provider ACK")
    with self.assertRaisesRegex(DoneExecutionError,"UNKNOWN"):
      execute_certified_done(
        self.plan,lambda:self.plan,lambda p:pinned,
        lambda p:AdmissionDecision(123,"main",B,True,"current"),
        fail,lambda *args:True,
        reconcile_unknown=lambda p,a:None)
    self.assertEqual(calls["count"],1)

  def test_unknown_recovery_refuses_absent_operation_id(self):
    recovered=[]
    with self.assertRaisesRegex(DoneExecutionError,"UNKNOWN"):
      execute_certified_done(
        self.plan,lambda:self.plan,lambda p:replace(self.attempt,operation_id=None),
        lambda p:AdmissionDecision(123,"main",B,True,"current"),
        lambda *args:None,lambda *args:True,
        reconcile_unknown=lambda p,a:recovered.append(a))
    self.assertEqual(recovered,[])

  def test_planner_block_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(original=replace(self.plan, allowed=False))
    self.assertEqual(self.calls, [])


if __name__ == "__main__":
  unittest.main()
