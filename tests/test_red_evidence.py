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



  def test_change_selected_red_group_after_audit_without_committing_log(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-first",
    )
    catalogue = self.root / ".ci/tests.json"
    value = json.loads(catalogue.read_text())
    value["tests"][0]["issue-545-second"] = {
      "type": "regression", "name": "smoke_case",
    }
    catalogue.write_text(json.dumps(value))
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "register two RED groups")
    initial = self.cli("test", "RED", "issue-545-first")
    self.assertEqual(initial.returncode, 2, initial.stderr)
    audit = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertTrue(audit.exists())
    change = self.cli("test", "RED", "issue-545-second")
    self.assertEqual(change.returncode, 2, change.stderr)
    self.assertEqual(
      (self.root / ".ci/red-green.txt").read_text(),
      "issue-545-second\n",
    )
    self.assertEqual(
      self.git("show", "--format=", "--name-only", "HEAD"),
      ".ci/red-green.txt",
    )
    self.assertEqual(len(audit.read_text().splitlines()), 2)
    (self.root / "smoke_case.py").write_text("# uncommitted source edit\n")
    refused = self.cli("test", "RED", "issue-545-first")
    self.assertEqual(refused.returncode, 2)
    self.assertIn("commit or discard", refused.stderr)
    self.assertEqual(
      (self.root / ".ci/red-green.txt").read_text(),
      "issue-545-second\n",
    )

  def test_newer_green_failure_supersedes_earlier_pass(self):
    self._catalogue(
      self.root / ".ci/tests.json", issue_group="issue-545-green",
    )
    self.git("add", ".ci/tests.json", "smoke_case.py")
    self.git("commit", "-m", "fixture catalogue")
    self.cli("test", "RED", "issue-545-green")
    first = self.cli("test", "GREEN")
    self.assertEqual(first.returncode, 0, first.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    passed = json.loads(log.read_text().splitlines()[-1])
    failed = dict(passed)
    failed["result"] = "failed"
    failed["groups"] = [{
      "group": "issue-545-green", "exit_code": 1, "reused": False,
    }]
    with log.open("a") as handle:
      handle.write(json.dumps(failed) + "\n")
    retried = self.cli("test", "GREEN")
    self.assertEqual(retried.returncode, 0, retried.stderr)
    self.assertNotIn("Reusing valid PASS evidence", retried.stdout)
    actual = json.loads(log.read_text().splitlines()[-1])
    self.assertFalse(actual["groups"][0]["reused"])
    again = self.cli("test", "GREEN")
    self.assertEqual(again.returncode, 0, again.stderr)
    self.assertIn("Reusing valid PASS evidence", again.stdout)

