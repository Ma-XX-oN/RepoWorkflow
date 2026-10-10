"""Specification tests for one-platform local integration observations."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.test_integration_engine import (
  _probe, run_local_integration,
)


class LocalIntegrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    subprocess.run(
      ["git", "init", "-qb", "issue-545-local-integration"],
      cwd=self.root, check=True, capture_output=True,
    )
    for key, value in (
      ("user.name", "Test"), ("user.email", "test@example.invalid"),
    ):
      subprocess.run(
        ["git", "config", key, value],
        cwd=self.root, check=True, capture_output=True,
      )
    (self.root / "source.txt").write_text("initial\n")
    subprocess.run(
      ["git", "add", "source.txt"],
      cwd=self.root, check=True, capture_output=True,
    )
    subprocess.run(
      ["git", "commit", "-qm", "initial"],
      cwd=self.root, check=True, capture_output=True,
    )
    self.sha = subprocess.check_output(
      ["git", "rev-parse", "HEAD"], cwd=self.root, text=True,
    ).strip()
    self.path = (
      self.root / ".repoworkflow/validation/testResults-545.jsonl"
    )

  def execute(self, regression="PASS", probes=None):
    if probes is None:
      probes = {}
    with (
      patch(
        "repo_workflow.test_integration_engine.self_regression",
        return_value=regression,
      ) as test_suite,
      patch(
        "repo_workflow.test_integration_engine._probe",
        side_effect=lambda _root, script: probes.get(script, 0),
      ) as probe,
    ):
      status = run_local_integration(self.root, engine_root=self.root)
    return status, json.loads(self.path.read_text().splitlines()[-1]), (
      test_suite.call_count, probe.call_count
    )

  def test_staged_rename_records_original_and_destination(self):
    subprocess.run(
      ["git", "mv", "source.txt", "renamed.txt"],
      cwd=self.root, check=True, capture_output=True,
    )
    status, record, _ = self.execute()
    self.assertEqual(status, 0)
    self.assertEqual(
      record["uncommittedChanges"], ["renamed.txt", "source.txt"],
    )
    self.assertFalse(record["reusable"])


  def test_clean_complete_current_platform_can_pass(self):
    status, record, calls = self.execute()
    self.assertEqual(status, 0)
    self.assertEqual(calls, (1, 3))
    self.assertEqual(record["result"], "succeeded")
    self.assertTrue(record["reusable"])
    self.assertEqual(record["testSHA"], self.sha)
    self.assertEqual(record["branch"], "issue-545-local-integration")
    self.assertTrue(all(record["platform"].get(k) for k in (
      "os", "architecture", "runtime",
    )))
    self.assertEqual(len(record["groups"]), 4)

  def test_regression_failure_never_runs_probes_or_passes(self):
    status, record, calls = self.execute(regression="FAIL")
    self.assertEqual(status, 1)
    self.assertEqual(calls, (1, 0))
    self.assertEqual(record["result"], "failed")
    self.assertFalse(record["reusable"])

  def test_incomplete_regression_is_not_a_pass(self):
    status, record, calls = self.execute(regression="INCOMPLETE")
    self.assertEqual(status, 2)
    self.assertEqual(calls, (1, 0))
    self.assertEqual(record["result"], "incomplete")
    self.assertFalse(record["reusable"])

  def test_failed_platform_probe_never_produces_a_pass(self):
    status, record, calls = self.execute(probes={"probe-argv-limits.py": 1})
    self.assertEqual(status, 1)
    self.assertEqual(calls, (1, 3))
    self.assertEqual(record["result"], "failed")
    self.assertFalse(record["reusable"])
    self.assertEqual(
      next(g["exit_code"] for g in record["groups"] if g["group"] == "argv-limits"),
      1,
    )

  def test_dirty_local_inputs_never_reusable(self):
    (self.root / "source.txt").write_text("dirty\n")
    status, record, _ = self.execute()
    self.assertEqual(status, 0)
    self.assertEqual(record["uncommittedChanges"], ["source.txt"])
    self.assertFalse(record["reusable"])

  def test_history_mutation_is_not_reusable(self):
    def advance(_root):
      (self.root / "source.txt").write_text("changed\n")
      subprocess.run(
        ["git", "add", "source.txt"], cwd=self.root, check=True,
        capture_output=True,
      )
      subprocess.run(
        ["git", "commit", "-qm", "test mutation"],
        cwd=self.root, check=True, capture_output=True,
      )
      return "PASS"

    with (
      patch(
        "repo_workflow.test_integration_engine.self_regression",
        side_effect=advance,
      ),
      patch(
        "repo_workflow.test_integration_engine._probe",
        return_value=0,
      ),
    ):
      status = run_local_integration(self.root, engine_root=self.root)
    record = json.loads(self.path.read_text().splitlines()[-1])
    self.assertEqual(status, 0)
    self.assertEqual(record["testSHA"], self.sha)
    self.assertTrue(record["headChangedDuringTest"])
    self.assertFalse(record["reusable"])

  def test_repeated_integration_observations_append(self):
    failed, _, _ = self.execute(regression="FAIL")
    passed, _, _ = self.execute(regression="PASS")
    records = [json.loads(x) for x in self.path.read_text().splitlines()]
    self.assertEqual((failed, passed), (1, 0))
    self.assertEqual([x["result"] for x in records], [
      "failed", "succeeded",
    ])
    self.assertEqual({x["testSHA"] for x in records}, {self.sha})

  def test_consumer_without_adapter_fails_before_pass(self):
    with self.assertRaisesRegex(ValueError, "environment adapter"):
      run_local_integration(self.root, engine_root=self.root.parent)
    self.assertFalse(self.path.exists())

  def test_probe_runs_real_external_program(self):
    scripts = self.root / "scripts"
    scripts.mkdir()
    (scripts / "test-probe.py").write_text("raise SystemExit(3)\n")
    self.assertEqual(_probe(self.root, "test-probe.py"), 3)


if __name__ == "__main__":
  unittest.main()
