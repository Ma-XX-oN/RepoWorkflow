"""Regression stage distinguishes engine self-checkout from consumer mounting."""

import json
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.test_cli import run_test
from tests import test_test_cli as fixture


class EngineRegressionTests(unittest.TestCase):
  setUp = fixture.TestCliContract.setUp
  tearDown = fixture.TestCliContract.tearDown
  git = fixture.TestCliContract.git

  def _script(self, exit_code):
    script = self.root / "scripts" / "validate.py"
    script.parent.mkdir()
    script.write_text(
      "import os, sys\n"
      "assert os.environ.get('PYTHONPYCACHEPREFIX')\n"
      "print('self-regression executed')\n"
      f"sys.exit({exit_code})\n"
    )

  def test_consumer_verified_preparation_records_exact_candidate(self):
    source_sha = self.git("rev-parse", "HEAD")
    observed_sha = []

    def verified_preparation(*args, **kwargs):
      (self.root / "prepared.txt").write_text("validated candidate\n")
      self.git("add", "prepared.txt")
      self.git("commit", "-qm", "prepare trusted candidate")
      candidate = self.git("rev-parse", "HEAD")
      kwargs["candidate_observer"](candidate)
      observed_sha.append(candidate)
      return "PASS"

    with patch(
      "repo_workflow.test_cli.verify_local",
      side_effect=verified_preparation,
    ):
      result = run_test(
        self.root, "regression", remote=False,
        engine_root=self.root.parent / "consumer-engine",
      )
    self.assertEqual(result, 0)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    record = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(record["testSHA"], observed_sha[0])
    self.assertEqual(record["sourceSHA"], source_sha)
    self.assertFalse(record["headChangedDuringTest"])
    self.assertTrue(record["reusable"])

  def test_engine_checkout_runs_self_suite_and_records_exact_sha(self):
    self._script(0)
    before = self.git("rev-parse", "HEAD")
    with patch("repo_workflow.test_cli.verify_local") as consumer:
      result = run_test(
        self.root, "regression", remote=False, engine_root=self.root,
      )
    self.assertEqual(result, 0)
    consumer.assert_not_called()
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    entry = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(entry["testSHA"], before)
    self.assertEqual(entry["result"], "succeeded")
    self.assertFalse(entry["reusable"])

  def test_engine_failure_never_issues_pass(self):
    self._script(1)
    with patch("repo_workflow.test_cli.verify_local") as consumer:
      result = run_test(
        self.root, "regression", remote=False, engine_root=self.root,
      )
    self.assertEqual(result, 1)
    consumer.assert_not_called()
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    entry = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(entry["result"], "failed")
    self.assertFalse(entry["reusable"])

  def test_engine_infrastructure_incomplete_is_not_failure(self):
    self._script(2)
    before = self.git("rev-parse", "HEAD")
    result = run_test(
      self.root, "regression", remote=False, engine_root=self.root,
    )
    self.assertEqual(result, 2)
    self.assertEqual(self.git("rev-parse", "HEAD"), before)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    entry = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(entry["testSHA"], before)
    self.assertEqual(entry["result"], "incomplete")
    self.assertFalse(entry["reusable"])

  def test_other_nonzero_exit_is_genuine_failure(self):
    self._script(3)
    result = run_test(
      self.root, "regression", remote=False, engine_root=self.root,
    )
    self.assertEqual(result, 1)
    log = self.root / ".repoworkflow/validation/testResults-545.jsonl"
    entry = json.loads(log.read_text().splitlines()[-1])
    self.assertEqual(entry["result"], "failed")



if __name__ == "__main__":
  unittest.main()
