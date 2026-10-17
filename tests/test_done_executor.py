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
    self.attempt = CertifiedAttempt(A, INT, C, B, "evidence-1", "auth-1")
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

  def test_changed_prelim_source_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(attempt=replace(self.attempt, source_prelim_sha=D))
    self.assertEqual(self.calls, [])

  def test_uncertified_candidate_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(attempt=replace(self.attempt, evidence_ref=""))
    self.assertEqual(self.calls, [])

  def test_unknown_remote_response_cannot_be_success(self):
    with self.assertRaisesRegex(DoneExecutionError, "UNKNOWN"):
      self.execute(response=None)
    self.assertEqual(len(self.calls), 1)

  def test_planner_block_stops_before_mutation(self):
    with self.assertRaises(DoneExecutionError):
      self.execute(original=replace(self.plan, allowed=False))
    self.assertEqual(self.calls, [])


if __name__ == "__main__":
  unittest.main()
