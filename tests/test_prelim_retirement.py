import unittest
from repo_workflow.prelim_retirement import LandedIntegration, plan_retirement, PrelimRetirementError, verify_attempt_scope
P='refs/heads/PRELIM-issue-123.0.1'
I=P
D='refs/heads/main'
class RetirementTests(unittest.TestCase):
  def test_accepted_and_durable(self):
    proof=LandedIntegration(P,'a'*40,I,'a'*40,D,'c'*40,'merge-1','evidence-1')
    result=plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='a'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=True)
    self.assertTrue(result.eligible_for_ref_retirement)
  def test_missing_terminal_rejected(self):
    proof=LandedIntegration(P,'a'*40,I,'a'*40,D,'c'*40,'merge-1','evidence-1')
    with self.assertRaises(PrelimRetirementError):
      plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='a'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=False)
  def test_generic_non_issue_submission_is_rejected(self):
    p=P.replace('issue-123','team-X')
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(p,p,D)
  def test_different_version_cannot_retire_other_attempt(self):
    other=I.replace('.0.1','.0.2')
    with self.assertRaisesRegex(PrelimRetirementError,'one PRELIM'):
      verify_attempt_scope(P,other,D)
  def test_cross_umbrella_ref_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P,I.replace('issue-123','issue-999'),D)
  def test_legacy_destination_in_name_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      verify_attempt_scope(P,I.replace('.0.1','/release-invalid'),D)
  def test_landed_destination_mismatch_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      proof=LandedIntegration(P,'a'*40,I,'a'*40,D,'c'*40,'merge-1','evidence-1')
      plan_retirement(P,'a'*40,I,'refs/heads/release',proof,observed_prelim_sha='a'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=True)
  def test_malformed_version_is_rejected(self):
    with self.assertRaises(PrelimRetirementError):
      malformed=P.replace('.0.1','.invalid')
      verify_attempt_scope(malformed,malformed,D)
  def test_changed_prelim_rejected(self):
    proof=LandedIntegration(P,'a'*40,I,'a'*40,D,'c'*40,'merge-1','evidence-1')
    with self.assertRaises(PrelimRetirementError):
      plan_retirement(P,'a'*40,I,D,proof,observed_prelim_sha='e'*40,current_destination_sha='c'*40,landed_is_ancestor=True,terminal_record_readback=True)

if __name__=='__main__': unittest.main()
