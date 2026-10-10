"""RED execution adapter tests; declaration storage is intentionally separate."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.test_red_classification import RedExpectation
from repo_workflow.test_red_runner import record_red
from repo_workflow.test_results_reader import TestCommandError

from tests import test_test_cli as fixture


class RedRunnerContract(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git

  def run_group(self, command, expectation):
    path = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    failure = None
    try:
      status = record_red(
        self.root, "issue-545-explicit", tuple(command),
        path, "a" * 64, dirty_inputs=lambda *_: [],
        expectation=expectation,
      )
    except TestCommandError as error:
      failure = str(error)
      status = 2
    record = (
      json.loads(path.read_text().splitlines()[-1])
      if path.exists() else None
    )
    return status, record, failure

  def test_predeclared_behavioural_failure_yields_red(self):
    status, evidence, failure = self.run_group(
      [sys.executable, "-c",
       "import sys;sys.stderr.write('invariant 545');sys.exit(3)"],
      RedExpectation(3, "invariant 545"),
    )
    self.assertEqual(status, 0, failure)
    self.assertEqual(evidence["result"], "succeeded")
    self.assertEqual(evidence["redStatus"], "RED")
    self.assertEqual(evidence["groups"][0]["exit_code"], 3)
    self.assertFalse(evidence["reusable"])

  def test_unexpected_success_is_not_red(self):
    status, evidence, _ = self.run_group(
      [sys.executable, "-c", "pass"],
      RedExpectation(3, "invariant 545"),
    )
    self.assertEqual(status, 2)
    self.assertEqual(evidence["result"], "failed")
    self.assertEqual(evidence["redStatus"], "NOT_RED")

  def test_unexpected_failure_is_fail_not_red(self):
    status, evidence, _ = self.run_group(
      [sys.executable, "-c", "import sys;sys.exit(4)"],
      RedExpectation(3, "invariant 545"),
    )
    self.assertEqual(status, 2)
    self.assertEqual(evidence["result"], "failed")
    self.assertEqual(evidence["redStatus"], "FAIL")

  def test_missing_executable_is_incomplete(self):
    status, evidence, _ = self.run_group(
      ["rwf-unavailable-bin-545"], RedExpectation(3, "invariant 545"),
    )
    self.assertEqual(status, 2)
    self.assertEqual(evidence["redStatus"], "INCOMPLETE")
    self.assertEqual(evidence["result"], "incomplete")
    self.assertIsNone(evidence["groups"][0]["exit_code"])

  def test_invalid_expectation_prevents_execution_and_audit(self):
    marker = self.root / "should-not-exist"
    status, record, _ = self.run_group(
      [sys.executable, "-c",
       "from pathlib import Path;Path(" + repr(str(marker)) + ").touch()"],
      RedExpectation(0, "invalid"),
    )
    self.assertEqual(status, 2)
    self.assertIsNone(record)
    self.assertFalse(marker.exists())


if __name__ == "__main__":
  unittest.main()
