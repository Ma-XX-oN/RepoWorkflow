"""Temporary fidelity groups must gate local regression."""
import json
import unittest

from tests import test_test_cli as fixture


class RegressionTemporaryTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git
  cli = fixture.TestCliContract.cli
  _catalogue = fixture.TestCliContract._catalogue

  def test_failure_blocks_regression_and_records_failed_group(self):
    self._catalogue(
      self.root / ".ci/temp-tests.json",
      issue_group="issue-545-fidelity",
    )
    source = self.root / "smoke_case.py"
    source.write_text(source.read_text().replace(
      "self.assertTrue(True)", "self.assertTrue(False)",
    ))
    result = self.cli("test", "regression")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("required temporary fidelity tests failed", result.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    observations = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual(len(observations), 1)
    self.assertEqual(observations[0]["kind"], "temporary")
    self.assertEqual(observations[0]["result"], "failed")
    self.assertFalse(observations[0]["reusable"])

  def test_multiple_groups_run_and_failure_is_not_hidden(self):
    manifest = self.root / ".ci/temp-tests.json"
    self._catalogue(manifest, issue_group="issue-545-working")
    (self.root / "fidelity_fail.py").write_text(
      "import unittest\n"
      "class Fidelity(unittest.TestCase):\n"
      "  def test_mismatch(self): self.fail('changed behaviour')\n"
    )
    value = json.loads(manifest.read_text())
    value["tests"][0]["issue-545-failing"] = {
      "type": "regression", "name": "fidelity_fail",
    }
    manifest.write_text(json.dumps(value))
    result = self.cli("test", "regression")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("required temporary fidelity tests failed", result.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(log.read_text().splitlines()[-1])
    groups = {entry["group"]: entry["exit_code"] for entry in record["groups"]}
    self.assertEqual(set(groups), {"issue-545-working", "issue-545-failing"})
    self.assertEqual(groups["issue-545-working"], 0)
    self.assertNotEqual(groups["issue-545-failing"], 0)

  def test_malformed_temporary_manifest_fails_before_regression(self):
    path = self.root / ".ci/temp-tests.json"
    path.parent.mkdir(parents=True)
    path.write_text("{invalid")
    result = self.cli("test", "regression")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("invalid JSON", result.stderr)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertFalse(log.exists())


if __name__ == "__main__":
  unittest.main()
