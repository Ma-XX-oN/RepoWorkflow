"""Consumer integration adapter safety/acceptance fixture tests."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.test_consumer_integration import run_consumer_integration
from repo_workflow.test_results_reader import TestCommandError


SHA = "a" * 40


class ConsumerIntegrationTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / ".ci").mkdir()
    (self.root / ".ci/repoworkflow.json").write_text("{}")
    (self.root / ".repoworkflow/validation").mkdir(parents=True)
    self.catalogue = {
      "test-harnesses": {"unittest": {"command": "python", "layout": [
        "-m", "unittest", "$test",
      ]}},
      "tests": [
        {"test-harness": "unittest", "issue-1-regression": {
          "name": "tests.regression", "type": "regression",
        }},
        {"test-harness": "unittest", "issue-1-integration": {
          "name": "tests.integration", "type": "integration",
        }},
      ],
      "aliases": {},
    }
    self._catalogue()
    self.calls = []
    self.verify_result = "PASS"
    self.group_result = 0
    self.reusable = True

  def _catalogue(self):
    (self.root / ".ci/tests.json").write_text(json.dumps(self.catalogue))

  def verify(self, root, engine, prepared, verifier):
    self.calls.append("verify")
    return self.verify_result

  def groups(self, root, stage, selected):
    self.calls.append("groups")
    if self.group_result == 0:
      record = {
        "kind": "integration", "testSHA": SHA,
        "result": "succeeded", "reusable": self.reusable,
        "groups": [{"group": name, "exit_code": 0} for name in selected],
      }
      (root / ".repoworkflow/validation/testResults-1.jsonl").write_text(
        json.dumps(record) + "\n"
      )
    return self.group_result

  def manual(self, root):
    self.calls.append("manual")
    return 0

  def publish(self, root, *, stage):
    self.calls.append("publish")
    self.assertEqual(stage, "integration")

  def execute_adapter(self):
    with (
      patch("repo_workflow.test_consumer_integration.head_sha", return_value=SHA),
      patch("repo_workflow.git.current_branch", return_value="issue-1-feature"),
    ):
      return run_consumer_integration(
        self.root, engine_root=self.root / "RepoWorkflow",
        run_groups=self.groups, verify=self.verify,
        verifier=lambda *_: None, manual_check=self.manual,
        publish=self.publish,
        get_version=lambda root: '1.2.3-issue.1.0.1',
      )

  def test_real_authority_and_both_retained_groups_required(self):
    self.assertEqual(self.execute_adapter(), 0)
    self.assertEqual(self.calls, ["verify", "groups", "manual", "publish"])
    rows = (self.root / '.repoworkflow/validation/testResults-1.jsonl').read_text().splitlines()
    self.assertEqual(len(rows), 2)
    self.assertEqual(json.loads(rows[-1])['testVersion'], '1.2.3-issue.1.0.1')

  def test_environment_fail_never_executes_groups(self):
    self.verify_result = "FAIL"
    self.assertEqual(self.execute_adapter(), 1)
    self.assertEqual(self.calls, ["verify"])

  def test_environment_incomplete_never_executes_groups(self):
    self.verify_result = "INCOMPLETE"
    self.assertEqual(self.execute_adapter(), 2)
    self.assertEqual(self.calls, ["verify"])

  def test_integration_group_failure_never_publishes(self):
    self.group_result = 1
    self.assertEqual(self.execute_adapter(), 1)
    self.assertEqual(self.calls, ["verify", "groups"])

  def test_nonreusable_evidence_fails_closed(self):
    self.reusable = False
    with self.assertRaisesRegex(TestCommandError, "not reusable"):
      self.execute_adapter()
    self.assertEqual(self.calls, ["verify", "groups"])

  def test_missing_environment_adapter_fails_closed(self):
    (self.root / ".ci/repoworkflow.json").unlink()
    with self.assertRaisesRegex(TestCommandError, "environment adapter"):
      self.execute_adapter()
    self.assertEqual(self.calls, [])

  def test_no_integration_tests_rejected_before_environment(self):
    self.catalogue["tests"].pop()
    self._catalogue()
    with self.assertRaisesRegex(TestCommandError, "registered integration tests"):
      self.execute_adapter()
    self.assertEqual(self.calls, [])

  def test_red_only_integration_group_does_not_satisfy_stage(self):
    self.catalogue["tests"][-1]["issue-1-integration"]["lifecycle"] = "RED"
    self._catalogue()
    with self.assertRaisesRegex(TestCommandError, "registered integration tests"):
      self.execute_adapter()
    self.assertEqual(self.calls, [])

  def test_missing_manual_approval_does_not_publish(self):
    self.manual = lambda root: 2
    self.assertEqual(self.execute_adapter(), 2)
    self.assertEqual(self.calls, ["verify", "groups"])

  def test_engine_route_is_not_consumer_adapter(self):
    with self.assertRaisesRegex(AssertionError, "must not replace"):
      run_consumer_integration(
        self.root, engine_root=self.root,
        run_groups=self.groups, verify=self.verify,
        verifier=lambda *_: None, manual_check=self.manual,
        publish=self.publish,
        get_version=lambda root: '1.2.3-issue.1.0.1',
      )


if __name__ == "__main__":
  unittest.main()
