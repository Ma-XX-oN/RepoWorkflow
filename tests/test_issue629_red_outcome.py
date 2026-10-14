"""Black-box RED/NOT_RED/FAIL/INCOMPLETE acceptance table."""

import unittest

try:
  from repo_workflow.test_red_classification import (
    RedExpectation, RedObservation, classify_red,
  )
except ImportError:
  RedExpectation = RedObservation = classify_red = None


class RedOutcomeAcceptanceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    if classify_red is None:
      raise unittest.SkipTest("PENDING #545: RED classification not assembled")

  def setUp(self):
    self.declared = RedExpectation(3, "specific behavioural sentinel 629")

  def result(self, code, stdout="", stderr="", executed=True, expected=None):
    if expected is None:
      expected = self.declared
    return classify_red(
      expected, RedObservation(code, stdout, stderr, executed),
    ).status

  def test_expected_exit_and_stderr_or_stdout_signature_is_red(self):
    self.assertEqual(
      self.result(3, stderr="specific behavioural sentinel 629"), "RED")
    self.assertEqual(
      self.result(3, stdout="specific behavioural sentinel 629"), "RED")

  def test_zero_exit_is_not_red_even_if_signature_exists(self):
    self.assertEqual(
      self.result(0, stdout="specific behavioural sentinel 629"), "NOT_RED")

  def test_unexpected_exit_or_signature_is_fail(self):
    self.assertEqual(
      self.result(1, stdout="specific behavioural sentinel 629"), "FAIL")
    self.assertEqual(self.result(3, stderr="other behavioural error"), "FAIL")
    self.assertEqual(self.result(3, stderr="FAILED"), "FAIL")

  def test_unlaunched_signal_or_missing_exit_is_incomplete(self):
    self.assertEqual(self.result(None, executed=False), "INCOMPLETE")
    self.assertEqual(self.result(None), "INCOMPLETE")
    self.assertEqual(self.result(-9), "INCOMPLETE")
    self.assertEqual(self.result(3, executed=False), "INCOMPLETE")

  def test_no_authoritative_declaration_is_incomplete(self):
    decision = classify_red(
      None, RedObservation(3, "", "specific behavioural sentinel 629", True),
    )
    self.assertEqual(decision.status, "INCOMPLETE")

  def test_invalid_declarations_and_observations_fail_closed(self):
    for invalid in (RedExpectation(0, "sentinel"),
                    RedExpectation(True, "sentinel"),
                    RedExpectation(-1, "sentinel"),
                    RedExpectation(1, "")):
      with self.subTest(invalid=invalid):
        self.assertEqual(
          classify_red(invalid, RedObservation(1, "sentinel", "", True)).status,
          "INCOMPLETE",
        )
    self.assertEqual(
      classify_red(self.declared, RedObservation(True, "", "", True)).status,
      "INCOMPLETE",
    )


if __name__ == "__main__":
  unittest.main()
