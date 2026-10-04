from pathlib import Path
from unittest import mock
import tempfile
import unittest

from repo_workflow.issue_test_contract import IssueTest, IssueTestContract
from repo_workflow.issue_test_runner import (
  IssueTestRunnerError,
  run_issue_tests,
)


class IssueTestRunnerTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)

  def tearDown(self):
    self.temp.cleanup()

  def contract(self, tests, trust="repository"):
    return IssueTestContract(issue=254, tests=tuple(tests), trust=trust)

  def test_python_green_and_red_results(self):
    results = run_issue_tests(
      self.root,
      self.contract((
        IssueTest("python", "assert 1 + 1 == 2\n"),
        IssueTest("python", "raise SystemExit(3)\n"),
      )),
    )

    self.assertEqual([result.status for result in results], ["green", "red"])
    self.assertEqual(results[0].exit_code, 0)
    self.assertEqual(results[1].exit_code, 3)

  def test_command_runs_from_repository_root_and_captures_output(self):
    marker = self.root / "marker.txt"
    result, = run_issue_tests(
      self.root,
      self.contract((
        IssueTest(
          "python",
          "from pathlib import Path\n"
          "print(Path.cwd())\n"
          "Path('marker.txt').write_text('ran')\n",
        ),
      )),
    )

    self.assertEqual(result.status, "green")
    self.assertEqual(Path(result.stdout.strip()), self.root.resolve())
    self.assertEqual(marker.read_text(), "ran")

  def test_ticket_proposed_contract_is_refused_before_subprocess(self):
    with mock.patch(
      "repo_workflow.issue_test_runner.subprocess.run",
      side_effect=AssertionError("untrusted test executed"),
    ):
      with self.assertRaisesRegex(IssueTestRunnerError, "not admitted"):
        run_issue_tests(
          self.root,
          self.contract(
            (IssueTest("python", "assert True\n"),),
            trust="ticket-proposed",
          ),
        )

  def test_admitted_ticket_contract_can_execute(self):
    result, = run_issue_tests(
      self.root,
      self.contract(
        (IssueTest("python", "assert True\n"),),
        trust="admitted",
      ),
    )
    self.assertEqual(result.status, "green")

  def test_missing_evaluator_is_distinct_error(self):
    with mock.patch(
      "repo_workflow.issue_test_runner.shutil.which",
      return_value=None,
    ):
      result, = run_issue_tests(
        self.root,
        self.contract((IssueTest("bash", "exit 0\n"),)),
      )
    self.assertEqual(result.status, "error")
    self.assertIsNone(result.exit_code)
    self.assertIn("evaluator unavailable", result.stderr)

  def test_timeout_is_distinct_error(self):
    result, = run_issue_tests(
      self.root,
      self.contract((
        IssueTest("python", "import time; time.sleep(1)\n"),
      )),
      timeout_seconds=0.01,
    )
    self.assertEqual(result.status, "error")
    self.assertIsNone(result.exit_code)

  def test_tests_execute_in_declared_order(self):
    result = run_issue_tests(
      self.root,
      self.contract((
        IssueTest("python", "open('order', 'w').write('1')\n"),
        IssueTest("python", "open('order', 'a').write('2')\n"),
      )),
    )
    self.assertEqual([item.index for item in result], [1, 2])
    self.assertEqual((self.root / "order").read_text(), "12")


if __name__ == "__main__":
  unittest.main()
