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
    self.assertEqual(
      decide(bad), (False, ("invalid-candidate", "invalid-current_base")),
    )
    changed = replace(self.facts, head="c"*40, current_base="d"*40,
                      complete=False)
    self.assertEqual(decide(changed), (False, (
      "head-changed", "stale-base", "missing-complete")))


  def test_uniform_sha256_identity_is_valid(self):
    sha = "a" * 64
    base = "b" * 64
    facts = replace(
      self.facts, candidate=sha, tested=sha, head=sha,
      recorded_base=base, current_base=base,
    )
    self.assertEqual(decide(facts), (True, ()))

  def test_mixed_sha1_sha256_identity_is_denied(self):
    facts = replace(self.facts, current_base="b" * 64)
    self.assertEqual(decide(facts), (
      False, ("mixed-hash-length", "stale-base"),
    ))

  def test_untrusted_success_flags_never_qualify(self):
    for flag in (
      "authenticated", "complete", "passed", "inputs_current",
      "required_checks_complete", "applicable",
      "candidate_exists", "base_is_ancestor",
    ):
      with self.subTest(flag=flag):
        for value in (False, None, 0, 1, "true"):
          result = decide(replace(self.facts, **{flag: value}))
          self.assertFalse(result[0])
          self.assertIn("missing-" + flag, result[1])


  def test_repeated_reassessment_invalidates_prior_allow(self):
    original = self.facts
    self.assertEqual(decide(original), (True, ()))
    for field, changed in (
      ("candidate", "c" * 40),
      ("head", "c" * 40),
      ("tested", "c" * 40),
      ("current_base", "c" * 40),
      ("recorded_base", "c" * 40),
    ):
      with self.subTest(field=field):
        self.assertFalse(decide(replace(original, **{field: changed}))[0])
        self.assertEqual(decide(original), (True, ()))

  def test_complete_success_requires_every_independent_authority_flag(self):
    flags = (
      "authenticated", "complete", "passed", "inputs_current",
      "required_checks_complete", "applicable", "candidate_exists",
      "base_is_ancestor",
    )
    for flag in flags:
      with self.subTest(flag=flag):
        deny = replace(self.facts, **{flag: False})
        self.assertEqual(decide(deny), (False, ("missing-" + flag,)))
        self.assertEqual(decide(self.facts), (True, ()))


if __name__ == "__main__":
  unittest.main()
