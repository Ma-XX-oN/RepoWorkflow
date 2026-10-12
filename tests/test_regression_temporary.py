"""Temporary fidelity groups must gate local regression."""
import json
import unittest
from unittest.mock import patch

from repo_workflow.test_cli import run_test

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
    with patch("repo_workflow.test_cli.verify_local", return_value="PASS") as verify:
      result = run_test(self.root, "regression", remote=False, engine_root=self.root / "engine")
    self.assertEqual(result, 1)
    verify.assert_called_once()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    observations = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual(len(observations), 2)
    self.assertEqual(observations[0]["kind"], "temporary")
    self.assertEqual(observations[-1]["kind"], "regression")
    self.assertEqual(observations[-1]["result"], "failed")
    self.assertFalse(observations[-1]["reusable"])
    self.assertIn("smoke_case.py", observations[-1]["uncommittedChanges"])
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
    with patch("repo_workflow.test_cli.verify_local", return_value="PASS"):
      result = run_test(self.root, "regression", remote=False, engine_root=self.root / "engine")
    self.assertEqual(result, 1)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(log.read_text().splitlines()[0])
    groups = {entry["group"]: entry["exit_code"] for entry in record["groups"]}
    self.assertEqual(set(groups), {"issue-545-working", "issue-545-failing"})
    self.assertEqual(groups["issue-545-working"], 0)
    self.assertNotEqual(groups["issue-545-failing"], 0)

  def test_successful_temporary_suite_and_permanent_pass_complete(self):
    self._catalogue(
      self.root / ".ci/temp-tests.json",
      issue_group="issue-545-fidelity",
    )
    with patch("repo_workflow.test_cli.verify_local", return_value="PASS") as verify:
      rc = run_test(self.root, "regression", remote=False, engine_root=self.root / "engine")
    self.assertEqual(rc, 0)
    verify.assert_called_once()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    self.assertEqual([x["kind"] for x in records], ["temporary", "regression"])
    self.assertEqual([x["result"] for x in records], ["succeeded", "succeeded"])
    self.assertFalse(records[-1]["reusable"])
    self.assertIn(".ci/temp-tests.json", records[-1]["uncommittedChanges"])

  def test_invalid_temporary_harness_fails_before_permanent_verifier(self):
    path = self.root / ".ci/temp-tests.json"
    self._catalogue(path, issue_group="issue-545-fidelity")
    data = json.loads(path.read_text())
    data["tests"][0]["issue-545-fidelity"]["name"] = ""
    path.write_text(json.dumps(data))
    with patch("repo_workflow.test_cli.verify_local", return_value="PASS") as verify:
      with self.assertRaisesRegex(Exception, "native test name"):
        run_test(self.root, "regression", remote=False, engine_root=self.root / "engine")
    verify.assert_not_called()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertFalse(log.exists())

  def test_malformed_temporary_manifest_fails_before_regression(self):
    path = self.root / ".ci/temp-tests.json"
    path.parent.mkdir(parents=True)
    path.write_text("{invalid")
    with patch("repo_workflow.test_cli.verify_local", return_value="PASS") as verify:
      with self.assertRaisesRegex(Exception, "invalid JSON"):
        run_test(self.root, "regression", remote=False, engine_root=self.root / "engine")
    verify.assert_not_called()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    self.assertFalse(log.exists())


if __name__ == "__main__":
  unittest.main()
