"""Black-box decision-table coverage for predeclared RED expectations."""
import unittest

from repo_workflow.test_red_classification import (
  RedExpectation, RedObservation, classify_red,
)


class RedClassificationContract(unittest.TestCase):
  def decide(self, expected, code, stdout="", stderr="", executed=True):
    return classify_red(
      expected, RedObservation(code, stdout, stderr, executed),
    )

  def test_intended_behavioural_failure_is_red(self):
    result = self.decide(
      RedExpectation(1, "AssertionError: intended invariant"),
      1, stderr="AssertionError: intended invariant",
    )
    self.assertEqual(result.status, "RED")

  def test_unexpected_pass_is_not_red(self):
    result = self.decide(RedExpectation(1, "AssertionError"), 0)
    self.assertEqual(result.status, "NOT_RED")

  def test_missing_declaration_is_incomplete_even_with_failure(self):
    result = self.decide(None, 1, stderr="AssertionError")
    self.assertEqual(result.status, "INCOMPLETE")

  def test_invalid_declarations_fail_closed(self):
    for declaration in (
      RedExpectation(0, "AssertionError"),
      RedExpectation(-1, "AssertionError"),
      RedExpectation(True, "AssertionError"),
      RedExpectation(1, ""),
    ):
      with self.subTest(declaration=declaration):
        self.assertEqual(
          self.decide(declaration, 1, stderr="AssertionError").status,
          "INCOMPLETE",
        )

  def test_unavailable_execution_is_incomplete(self):
    expected = RedExpectation(1, "AssertionError")
    for code, executed in ((None, False), (1, False), (None, True)):
      with self.subTest(code=code, executed=executed):
        self.assertEqual(
          self.decide(expected, code, executed=executed).status,
          "INCOMPLETE",
        )

  def test_unexpected_nonzero_exit_is_failure(self):
    expected = RedExpectation(1, "AssertionError: expected")
    for code, output in (
      (2, "AssertionError: expected"),
      (1, "ModuleNotFoundError: missing module"),
      (127, "command not found"),
    ):
      with self.subTest(code=code, output=output):
        self.assertEqual(
          self.decide(expected, code, stderr=output).status, "FAIL",
        )

  def test_terminated_process_is_incomplete(self):
    self.assertEqual(
      self.decide(RedExpectation(1, "expected"), -9).status,
      "INCOMPLETE",
    )

  def test_signature_can_be_in_stdout(self):
    self.assertEqual(
      self.decide(RedExpectation(3, "expected violation"), 3,
                  stdout="expected violation").status,
      "RED",
    )


if __name__ == "__main__":
  unittest.main()
