"""Contract matrix for independent regression and PRELIM terminal identity."""
import unittest

from repo_workflow.phase_terminal import PhaseTransitionError, plan_phase


VERSION = "1.2.3-issue.571.2.7"


class PhaseTerminalTests(unittest.TestCase):
  def test_regression_pass_keeps_generation_and_iteration(self):
    result = plan_phase(VERSION, phase="regression", outcome="PASS")
    self.assertEqual(result.terminal_tag, "v" + VERSION)
    self.assertEqual(result.next_version, VERSION)
    self.assertIsNone(result.next_request)

  def test_regression_fail_advances_r_only_for_next_attempt(self):
    result = plan_phase(VERSION, phase="regression", outcome="FAIL")
    self.assertEqual(result.terminal_tag, "v" + VERSION + "-CI-FAIL")
    self.assertEqual(result.next_version, "1.2.3-issue.571.2.8")
    self.assertEqual(result.next_request, (
      "task", "--increment", "CI-iteration",
    ))

  def test_integration_pass_uses_distinct_prelim_without_r_increment(self):
    regression = plan_phase(VERSION, phase="regression", outcome="PASS")
    result = plan_phase(VERSION, phase="integration", outcome="PASS")
    self.assertEqual(result.terminal_tag, "v1.2.3-PRELIM-571.2.7")
    self.assertNotEqual(regression.terminal_tag, result.terminal_tag)
    self.assertEqual(result.next_version, VERSION)
    self.assertIsNone(result.next_request)

  def test_integration_failure_advances_q_and_resets_r_next_cycle(self):
    result = plan_phase(VERSION, phase="integration", outcome="FAIL")
    self.assertEqual(result.terminal_tag, "v1.2.3-PRELIM-571.2.7-CI-FAIL")
    self.assertEqual(result.next_version, "1.2.3-issue.571.3.1")
    self.assertEqual(result.next_request, (
      "task", "--increment", "merge-integration-failed",
    ))

  def test_incomplete_does_not_consume_version_or_tag(self):
    for phase in ("regression", "integration"):
      with self.subTest(phase=phase):
        result = plan_phase(VERSION, phase=phase, outcome="INCOMPLETE")
        self.assertIsNone(result.terminal_tag)
        self.assertIsNone(result.next_request)
        self.assertEqual(result.next_version, VERSION)

  def test_first_generation_and_large_values(self):
    initial = "0.0.0-issue.1.0.1"
    self.assertEqual(
      plan_phase(initial, phase="integration", outcome="PASS").terminal_tag,
      "v0.0.0-PRELIM-1.0.1",
    )
    large = "999.888.777-issue.123456.99.9999"
    self.assertEqual(
      plan_phase(large, phase="integration", outcome="FAIL").next_version,
      "999.888.777-issue.123456.100.1",
    )

  def test_repeated_calculation_is_idempotent_and_pure(self):
    first = plan_phase(VERSION, phase="regression", outcome="FAIL")
    self.assertEqual(first, plan_phase(VERSION, phase="regression", outcome="FAIL"))
    self.assertEqual(first.current_version, VERSION)

  def test_full_regression_integration_retry_lifecycle(self):
    first = plan_phase(VERSION, phase="regression", outcome="FAIL")
    self.assertEqual(first.terminal_tag, "v" + VERSION + "-CI-FAIL")
    second = plan_phase(first.next_version, phase="regression", outcome="PASS")
    self.assertEqual(second.next_version, "1.2.3-issue.571.2.8")
    third = plan_phase(second.next_version, phase="integration", outcome="FAIL")
    self.assertEqual(third.terminal_tag, "v1.2.3-PRELIM-571.2.8-CI-FAIL")
    self.assertEqual(third.next_version, "1.2.3-issue.571.3.1")
    fourth = plan_phase(third.next_version, phase="regression", outcome="PASS")
    fifth = plan_phase(fourth.next_version, phase="integration", outcome="PASS")
    self.assertEqual(fifth.terminal_tag, "v1.2.3-PRELIM-571.3.1")
    self.assertEqual(fifth.next_version, fourth.next_version)
    self.assertEqual(len({
      first.terminal_tag, second.terminal_tag,
      third.terminal_tag, fourth.terminal_tag, fifth.terminal_tag,
    }), 5)

  def test_immutable_terminal_repeat_and_opposite_outcome(self):
    for phase in ("regression", "integration"):
      for terminal in ("PASS", "FAIL"):
        with self.subTest(phase=phase, terminal=terminal):
          first = plan_phase(VERSION, phase=phase, outcome=terminal)
          repeat = plan_phase(
            VERSION, phase=phase, outcome=terminal, prior_terminal=terminal,
          )
          self.assertEqual(first, repeat)
          opposite = "FAIL" if terminal == "PASS" else "PASS"
          with self.assertRaisesRegex(PhaseTransitionError, "immutable"):
            plan_phase(
              VERSION, phase=phase, outcome=opposite, prior_terminal=terminal,
            )
          with self.assertRaisesRegex(PhaseTransitionError, "immutable"):
            plan_phase(
              VERSION, phase=phase, outcome="INCOMPLETE",
              prior_terminal=terminal,
            )

  def test_non_terminal_retry_can_complete_without_increment(self):
    for phase in ("regression", "integration"):
      first = plan_phase(VERSION, phase=phase, outcome="INCOMPLETE")
      terminal = plan_phase(
        first.next_version, phase=phase, outcome="PASS",
      )
      self.assertIsNone(first.terminal_tag)
      self.assertEqual(terminal.next_version, VERSION)
      with self.assertRaisesRegex(PhaseTransitionError, "prior"):
        plan_phase(
          VERSION, phase=phase, outcome="PASS",
          prior_terminal="INCOMPLETE",
        )

  def test_invalid_phase_outcome_and_version_fail(self):
    for phase in ("RED", "GREEN", "temporary", "results", ""):
      with self.subTest(phase=phase):
        with self.assertRaises(PhaseTransitionError):
          plan_phase(VERSION, phase=phase, outcome="PASS")
    for outcome in ("", "SKIPPED", "succeeded", "ERROR"):
      with self.subTest(outcome=outcome):
        with self.assertRaises(PhaseTransitionError):
          plan_phase(VERSION, phase="regression", outcome=outcome)
    for version in (
      "", "1.2.3", "1.2.3-issue.0.0.1",
      "1.2.3-issue.571.2.0", "1.2.3-issue.571.2.7-extra",
      "1.2.3-issue.571.2.-1",
      "01.2.3-issue.571.2.7", "1.02.3-issue.571.2.7",
      "1.2.3-issue.0571.2.7", "1.2.3-issue.571.02.7",
    ):
      with self.subTest(version=version):
        with self.assertRaises(PhaseTransitionError):
          plan_phase(version, phase="integration", outcome="PASS")


if __name__ == "__main__":
  unittest.main()
