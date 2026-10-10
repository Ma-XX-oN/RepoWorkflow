"""Black-box candidate gate acceptance and invalidation tests."""
import unittest
from dataclasses import replace
from repo_workflow.candidate_eligibility import Facts, decide


class CandidateEligibilityTests(unittest.TestCase):
  def setUp(self):
    self.facts = Facts("a"*40, "a"*40, "a"*40, "b"*40, "b"*40,
                       True, True, True, True, True, True, True, True)

  def test_exact_authenticated_complete_pass(self):
    self.assertEqual(decide(self.facts), (True, ()))

  def test_invalidations_are_deterministic(self):
    for field, value, expected in (
      ("tested", "c"*40, "tested-candidate-mismatch"),
      ("head", "c"*40, "head-changed"),
      ("current_base", "c"*40, "stale-base"),
      ("authenticated", False, "missing-authenticated"),
      ("complete", False, "missing-complete"),
      ("passed", False, "missing-passed"),
      ("inputs_current", False, "missing-inputs_current"),
      ("required_checks_complete", False, "missing-required_checks_complete"),
      ("applicable", False, "missing-applicable"),
      ("candidate_exists", False, "missing-candidate_exists"),
      ("base_is_ancestor", False, "missing-base_is_ancestor"),
    ):
      with self.subTest(field=field):
        ok, reasons = decide(replace(self.facts, **{field: value}))
        self.assertFalse(ok)
        self.assertIn(expected, reasons)

  def test_missing_invalid_and_multiple_defects(self):
    self.assertEqual(decide(None), (False, ("invalid-facts",)))
    bad = replace(self.facts, candidate="bad", current_base="", passed=False)
    self.assertEqual(decide(bad), (False, ("invalid-candidate", "invalid-current_base")))
    changed = replace(self.facts, head="c"*40, current_base="d"*40,
                      complete=False)
    self.assertEqual(decide(changed), (False, (
      "head-changed", "stale-base", "missing-complete")))


if __name__ == "__main__":
  unittest.main()
