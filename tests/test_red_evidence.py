"""RED evidence contract black-box tests using the shipped CLI."""
import json
import unittest

from tests import test_test_cli as fixture


class RedEvidenceTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def test_red_records_observation_without_claiming_red_pass(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-red",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    first = self.cli("test", "RED", "issue-545-red")
    self.assertEqual(first.returncode, 2, first.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    successful_test = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(successful_test["kind"], "RED")
    self.assertEqual(successful_test["result"], "incomplete")
    self.assertEqual(successful_test["groups"][0]["exit_code"], 0)
    self.assertFalse(successful_test["reusable"])
    self.assertEqual(successful_test["reason"], "expected-red-failure-not-demonstrated")
    source = self.root / "smoke_case.py"
    source.write_text(source.read_text().replace(
      "self.assertTrue(True)", "self.assertTrue(False)",
    ))
    failure = self.cli("test", "RED")
    self.assertEqual(failure.returncode, 2, failure.stderr)
    recorded = json.loads(audit.read_text().splitlines()[-1])
    self.assertEqual(recorded["result"], "incomplete")
    self.assertNotEqual(recorded["groups"][0]["exit_code"], 0)
    self.assertEqual(recorded["reason"], "failure-not-classified-as-expected-red")
    self.assertIn("smoke_case.py", recorded["uncommittedChanges"])
    self.assertFalse(recorded["reusable"])


