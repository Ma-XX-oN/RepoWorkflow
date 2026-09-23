from pathlib import Path
import json
import sys
import tempfile
import unittest

from repo_workflow.config import load_config
from repo_workflow.results import ResultError, evaluate_results, run_environment
from tests.support import RepoFixture


class ResultTests(unittest.TestCase):
  def make(self, **kwargs):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "repo"
    root.mkdir()
    fixture = RepoFixture(root, **kwargs)
    return td, root, fixture

  def test_validation_pass_writes_pass_result(self):
    td, root, fx = self.make(validation_body="raise SystemExit(0)\n")
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 0)
      value = json.loads(result_path.read_text())
      self.assertEqual(value["status"], "PASS")
      self.assertEqual(value["commit"], fx.head())

  def test_validation_failure_writes_fail_result(self):
    td, root, _ = self.make(validation_body="raise SystemExit(7)\n")
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 1)
      self.assertEqual(json.loads(result_path.read_text())["status"], "FAIL")

  def test_exit_two_is_incomplete(self):
    td, root, _ = self.make(validation_body="raise SystemExit(2)\n")
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 2)
      self.assertEqual(json.loads(result_path.read_text())["status"], "INCOMPLETE")

  def test_platform_mismatch_is_incomplete_without_running_validation(self):
    mismatch = "windows" if not sys.platform.startswith("win") else "linux"
    td, root, _ = self.make(
      validation_body="raise RuntimeError('must not run')\n", platform=mismatch
    )
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 2)
      self.assertEqual(json.loads(result_path.read_text())["status"], "INCOMPLETE")

  def test_validation_worktree_mutation_is_failure(self):
    body = (
      "from pathlib import Path\n"
      "Path('unexpected.txt').write_text('x')\n"
      "raise SystemExit(0)\n"
    )
    td, root, fx = self.make(validation_body=body)
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 1)
      self.assertIn("modified repository state", json.loads(result_path.read_text())["message"])
      self.assertFalse((root / "unexpected.txt").exists())
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_validation_local_ref_mutation_is_failure(self):
    body = (
      "import subprocess\n"
      "subprocess.run(['git','tag','validation-side-effect'], check=True)\n"
      "raise SystemExit(0)\n"
    )
    td, root, fx = self.make(validation_body=body)
    with td:
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 1)
      self.assertIn(
        "local Git refs",
        json.loads(result_path.read_text())["message"],
      )
      self.assertEqual(fx._run("tag", "--list", "validation-side-effect").stdout, "")

  def test_validation_head_reference_change_is_failure_and_restored(self):
    body = (
      "import subprocess\n"
      "subprocess.run(['git','switch','side'], check=True)\n"
      "raise SystemExit(0)\n"
    )
    td, root, fx = self.make(validation_body=body)
    with td:
      fx._run("branch", "side")
      original_branch = fx._run("branch", "--show-current").stdout.strip()
      result_path = root.parent / "result.json"
      rc = run_environment(root, load_config(root), "local", result_path)
      self.assertEqual(rc, 1)
      self.assertIn("HEAD reference", json.loads(result_path.read_text())["message"])
      self.assertEqual(
        fx._run("branch", "--show-current").stdout.strip(), original_branch
      )

  def test_missing_required_result_is_incomplete(self):
    config = {"environments": [{"id": "one", "required": True}]}
    outcome, tag, warnings = evaluate_results(config, [], "1.0.0-issue.1.1", "a")
    self.assertEqual(outcome, "INCOMPLETE")
    self.assertIsNone(tag)
    self.assertTrue(warnings)

  def test_required_failure_maps_to_ci_fail_tag(self):
    config = {"environments": [{"id": "one", "required": True}]}
    result = {
      "environment": "one", "version": "1.0.0-issue.1.1",
      "commit": "a", "status": "FAIL"
    }
    outcome, tag, _ = evaluate_results(config, [result], result["version"], "a")
    self.assertEqual((outcome, tag), ("FAIL", "v1.0.0-issue.1.1-CI-FAIL"))

  def test_optional_failure_does_not_fail_complete_required_matrix(self):
    config = {"environments": [
      {"id": "required", "required": True},
      {"id": "optional", "required": False},
    ]}
    results = [
      {"environment": "required", "version": "1.0.0-issue.1.1", "commit": "a", "status": "PASS"},
      {"environment": "optional", "version": "1.0.0-issue.1.1", "commit": "a", "status": "FAIL"},
    ]
    outcome, tag, _ = evaluate_results(config, results, "1.0.0-issue.1.1", "a")
    self.assertEqual((outcome, tag), ("PASS", "v1.0.0-issue.1.1"))

  def test_missing_artifact_gate_result_is_incomplete_when_artifacts_declared(self):
    config = {
      "environments": [{"id": "one", "required": True}],
      "artifacts": [{"id": "bundle"}],
    }
    env = {
      "environment": "one", "version": "1.0.0-issue.1.1",
      "commit": "a", "status": "PASS",
    }
    outcome, tag, warnings = evaluate_results(
      config, [env], env["version"], "a"
    )
    self.assertEqual(outcome, "INCOMPLETE")
    self.assertIsNone(tag)
    self.assertTrue(any("artifact" in warning for warning in warnings))

  def test_artifact_gate_failure_maps_to_ci_fail_tag(self):
    config = {
      "environments": [{"id": "one", "required": True}],
      "artifacts": [{"id": "bundle"}],
    }
    version = "1.0.0-issue.1.1"
    results = [
      {"environment": "one", "version": version, "commit": "a", "status": "PASS"},
      {
        "environment": "__repoworkflow_artifacts__",
        "version": version, "commit": "a", "status": "FAIL",
      },
    ]
    outcome, tag, _ = evaluate_results(config, results, version, "a")
    self.assertEqual((outcome, tag), ("FAIL", f"v{version}-CI-FAIL"))

  def test_artifact_incomplete_prevents_fail_tag_even_if_environment_failed(self):
    config = {
      "environments": [{"id": "one", "required": True}],
      "artifacts": [{"id": "bundle"}],
    }
    version = "1.0.0-issue.1.1"
    results = [
      {"environment": "one", "version": version, "commit": "a", "status": "FAIL"},
      {
        "environment": "__repoworkflow_artifacts__",
        "version": version, "commit": "a", "status": "INCOMPLETE",
      },
    ]
    outcome, tag, _ = evaluate_results(config, results, version, "a")
    self.assertEqual(outcome, "INCOMPLETE")
    self.assertIsNone(tag)

  def test_duplicate_environment_result_is_rejected(self):
    config = {"environments": [{"id": "one", "required": True}]}
    result = {"environment": "one", "version": "v", "commit": "a", "status": "PASS"}
    with self.assertRaises(ResultError):
      evaluate_results(config, [result, dict(result)], "v", "a")


if __name__ == "__main__":
  unittest.main()
