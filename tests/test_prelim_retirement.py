import unittest
from repo_workflow.prelim_retirement import LandedIntegration, plan_retirement, PrelimRetirementError, verify_attempt_scope
P='refs/heads/PRELIM-issue-123/main-11111111-1111-4111-8111-111111111111'
I='refs/heads/INT-ATTEMPT-issue-123/main-22222222-2222-4222-8222-222222222222'
D='refs/heads/main'
class RetirementTests(unittest.TestCase):
  def test_accepted_and_durable(self):
    proof=LandedIntegration(P,'a'*40,I,'b'*40,D,'c'*40,'merge-1','evidence-1')
    result=plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='a'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=True)
    self.assertTrue(result.eligible_for_ref_retirement)
  def test_missing_terminal_rejected(self):
    proof=LandedIntegration(P,'a'*40,I,'b'*40,D,'c'*40,'merge-1','evidence-1')
    with self.assertRaises(PrelimRetirementError):
      plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='a'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=False)
  def test_cross_umbrella_ref_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P,I.replace('issue-123','issue-999'),D)
  def test_cross_destination_ref_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P,I.replace('main-','release-'),D)
  def test_landed_destination_mismatch_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P,I,'refs/heads/release')
  def test_malformed_guid_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P.replace('11111111-1111-4111-8111-111111111111','invalid'),I,D)
  def test_changed_prelim_rejected(self):
    proof=LandedIntegration(P,'a'*40,I,'b'*40,D,'c'*40,'merge-1','evidence-1')
    with self.assertRaises(PrelimRetirementError):
      plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='e'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=True)

if __name__=='__main__': unittest.main()