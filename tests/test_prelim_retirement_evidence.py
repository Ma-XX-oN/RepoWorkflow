"""Provider readback before immutable PRELIM retirement."""
from dataclasses import replace
import unittest

from repo_workflow.prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from repo_workflow.prelim_retirement_evidence import verify_retirement_evidence

P = "refs/heads/PRELIM-issue-123/main-11111111-1111-4111-8111-111111111111"
I = "refs/heads/INT-ATTEMPT-issue-123/main-22222222-2222-4222-8222-222222222222"
D = "refs/heads/main"
S = "a"*40
A = "b"*40
L = "c"*40
T = "d"*40


class RetirementEvidenceTests(unittest.TestCase):
  def setUp(self):
    self.landed = LandedIntegration(
      P, S, I, A, D, L, "operation-1", "terminal-1")
    self.refs = {P: S, I: A, D: T}
    self.compare = {"base_sha": L, "head_sha": T,
                    "status": "ahead", "behind_by": 0}
    self.accepted_compare = {"base_sha": A, "head_sha": L,
                             "status": "ahead", "behind_by": 0}
    self.terminal = dict(
      status="integrated", prelim_ref=P, prelim_sha=S,
      int_attempt_ref=I, accepted_sha=A, destination_ref=D,
      landed_sha=L, integration_id="operation-1",
      terminal_evidence_ref="terminal-1")

  def check(self):
    return verify_retirement_evidence(
      self.landed,
      read_ref=lambda ref: self.refs.get(ref),
      compare_commits=lambda base, head: (
        self.accepted_compare if (base, head) == (A, L)
        else self.compare if (base, head) == (L, T) else None),
      read_terminal=lambda ref: self.terminal)

  def test_exact_provider_evidence_is_sufficient_for_preflight(self):
    result = self.check()
    self.assertTrue(result.eligible_for_ref_retirement)
    self.assertEqual(result.landed_sha, L)

  def test_retired_original_ref_requires_terminal_evidence(self):
    self.refs.pop(P)
    self.assertTrue(self.check().eligible_for_ref_retirement)

  def test_modified_prelim_is_rejected(self):
    self.refs[P] = "e"*40
    with self.assertRaisesRegex(PrelimRetirementError, "changed"):
      self.check()

  def test_destination_unavailable_is_rejected(self):
    self.refs.pop(D)
    with self.assertRaises(PrelimRetirementError):
      self.check()

  def test_stale_or_forged_compare_is_rejected(self):
    for change in ({"base_sha": A}, {"head_sha": S},
                   {"status": "diverged"}, {"behind_by": 1},
                   {"behind_by": True}):
      with self.subTest(change=change):
        before = self.compare.copy()
        self.compare.update(change)
        with self.assertRaises(PrelimRetirementError):
          self.check()
        self.compare = before

  def test_unrelated_accepted_candidate_cannot_retire(self):
    self.accepted_compare["status"] = "diverged"
    with self.assertRaisesRegex(PrelimRetirementError, "accepted candidate"):
      self.check()

  def test_accepted_sha_must_be_actual_comparison_base(self):
    self.accepted_compare["base_sha"] = S
    with self.assertRaisesRegex(PrelimRetirementError, "accepted candidate"):
      self.check()

  def test_int_attempt_changed_after_acceptance_is_rejected(self):
    self.refs[I] = S
    with self.assertRaisesRegex(PrelimRetirementError, "INT-ATTEMPT changed"):
      self.check()

  def test_retired_int_attempt_requires_terminal_proof(self):
    self.refs.pop(I)
    self.assertTrue(self.check().eligible_for_ref_retirement)
    self.terminal = None
    with self.assertRaises(PrelimRetirementError):
      self.check()

  def test_wrong_candidate_or_evidence_id_denied(self):
    for change in ({"accepted_sha": S},
                   {"terminal_evidence_ref": "other"},
                   {"status": "deferred-mit"},
                   {"integration_id": "different"}):
      with self.subTest(change=change):
        before = self.terminal.copy()
        self.terminal.update(change)
        with self.assertRaises(PrelimRetirementError):
          self.check()
        self.terminal = before

  def test_missing_terminal_denied(self):
    self.terminal = None
    with self.assertRaises(PrelimRetirementError):
      self.check()

  def test_provider_returning_unknown_status_denied(self):
    self.compare["status"] = "unknown"
    with self.assertRaises(PrelimRetirementError):
      self.check()

  def test_landed_record_must_match_provenance(self):
    self.landed = replace(self.landed, prelim_sha="e"*40)
    with self.assertRaises(PrelimRetirementError):
      self.check()


if __name__ == "__main__":
  unittest.main()
