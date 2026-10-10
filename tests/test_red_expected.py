"""Independent RED classification and hosted evidence contract tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from repo_workflow.red_expected import assertion_failure


ROOT = Path(__file__).resolve().parents[1]
COMMAND = (sys.executable, "-m", "unittest", "tests.any_test")


class RedExpectedFailureTests(unittest.TestCase):
  def test_single_or_multiple_assertion_failures_are_red(self):
    for count in (1, 2, 10):
      self.assertTrue(assertion_failure(
        COMMAND, 1, f"Ran {count} tests\nFAILED (failures={count})\n",
      ))

  def test_passing_or_infrastructure_failure_never_establishes_red(self):
    for code, output in (
      (0, "OK\n"),
      (1, "FAILED (errors=1)\n"),
      (1, "FAILED (failures=1, errors=1)\n"),
      (1, "FAILED (failures=1, unexpected successes=1)\n"),
      (1, "import failed"),
      (2, "FAILED (failures=1)\n"),
    ):
      with self.subTest(code=code, output=output):
        self.assertFalse(assertion_failure(COMMAND, code, output))

  def test_unrecognized_harness_and_fake_summary_fail_closed(self):
    self.assertFalse(assertion_failure(
      ("custom-test-runner", "suite"), 1, "FAILED (failures=1)\n",
    ))
    self.assertFalse(assertion_failure(
      COMMAND, 1, "FAILED (failures=1)\nFAILED (failures=1)\n",
    ))


class HostedRedEvidenceTests(unittest.TestCase):
  def setUp(self):
    module_spec = importlib.util.spec_from_file_location(
      "hosted_result_gate", ROOT / "scripts/validate-hosted-result.py",
    )
    self.assertIsNotNone(module_spec)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    self.validate_result = module.validate_result
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.root = Path(temporary.name)
    self.candidate = "a" * 40
    self.log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.log.parent.mkdir(parents=True)
    catalogue = self.root / ".ci/tests.json"
    catalogue.parent.mkdir(parents=True)
    catalogue.write_text(json.dumps({
      "test-harnesses": {
        "unittest": {"command": "python", "layout": []},
      },
      "tests": [
        {"test-harness": "unittest",
         "issue-545-negative": {"type": "regression"}},
      ],
      "aliases": {},
    }))
    (self.root / ".ci/red-green.txt").write_text("issue-545-negative\n")
    self.record = {
      "branch": "issue-545-probe", "testSHA": self.candidate,
      "kind": "RED", "result": "succeeded", "reusable": False,
      "expectedFailure": True,
      "reason": "expected-red-assertion-demonstrated",
      "catalogueSHA256": hashlib.sha256(catalogue.read_bytes()).hexdigest(),
      "headChangedDuringTest": False, "uncommittedChanges": [],
      "platform": {"os": "Linux", "architecture": "x86_64", "runtime": "3.13"},
      "groups": [{"group": "issue-545-negative", "exit_code": 1,
                  "reused": False}],
    }

  def verify(self):
    self.log.write_text(json.dumps(self.record) + "\n")
    self.validate_result(
      self.root, stage="RED-testing", candidate=self.candidate,
      branch="issue-545-probe",
    )

  def test_real_assertion_failure_is_accepted_as_red(self):
    self.verify()

  def test_success_evidence_cannot_hide_passing_or_unclassified_test(self):
    for field, value in (
      ("expectedFailure", False),
      ("reason", "failure-not-classified-as-expected-red"),
      ("reusable", True),
    ):
      with self.subTest(field=field):
        original = self.record[field]
        self.record[field] = value
        with self.assertRaises(ValueError):
          self.verify()
        self.record[field] = original
    self.record["groups"][0]["exit_code"] = 0
    with self.assertRaises(ValueError):
      self.verify()


if __name__ == "__main__":
  unittest.main()
