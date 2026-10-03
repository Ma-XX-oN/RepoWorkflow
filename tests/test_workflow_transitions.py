from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.workflow_state import discover_facts, save_local_state
from repo_workflow.workflow_transitions import validate_integration, validate_regression
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTransitionTests(unittest.TestCase):
  def test_regression_failure_advances_only_ci_iteration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      failed_candidate = fx.head()

      with patch(
        "repo_workflow.workflow_transitions.verify_local",
        return_value="FAIL",
      ) as verify:
        outcome = validate_regression(root, engine_root=ROOT)

      verify.assert_called_once_with(root, engine_root=ROOT, push=False)
      self.assertEqual(outcome, "FAIL")
      self.assertEqual(
        (root / "VERSION").read_text().strip(),
        "1.0.0-issue.1.3.8",
      )
      self.assertNotEqual(fx.head(), failed_candidate)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")
      self.assertEqual(discover_facts(root).regression, "missing")

  def test_regression_pass_does_not_advance_version(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")

      with patch(
        "repo_workflow.workflow_transitions.verify_local",
        return_value="PASS",
      ):
        outcome = validate_regression(root, engine_root=ROOT)

      self.assertEqual(outcome, "PASS")
      self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
      self.assertEqual(discover_facts(root).regression, "PASS")

  def test_regression_incomplete_does_not_advance_version(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")

      with patch(
        "repo_workflow.workflow_transitions.verify_local",
        return_value="INCOMPLETE",
      ):
        outcome = validate_regression(root, engine_root=ROOT)

      self.assertEqual(outcome, "INCOMPLETE")
      self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
      self.assertEqual(discover_facts(root).regression, "INCOMPLETE")

  def test_integration_failure_advances_generation_and_resets_iteration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      validate_integration(root, "failed")

      self.assertEqual(
        (root / "VERSION").read_text().strip(),
        "1.0.0-issue.1.4.1",
      )
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")
      facts = discover_facts(root)
      self.assertEqual(facts.regression, "missing")
      self.assertEqual(facts.integration_result, "failed")

  def test_integration_success_keeps_version_and_records_result(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      candidate = validate_integration(root, "succeeded")

      self.assertEqual(candidate, fx.head())
      self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
      self.assertEqual(discover_facts(root).integration_result, "succeeded")

  def test_integration_result_without_regression_pass_is_atomic(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, version="1.0.0-issue.1.3.7")
      before = fx.head()
      with self.assertRaisesRegex(ValueError, "requires regression PASS"):
        validate_integration(root, "failed")
      self.assertEqual(fx.head(), before)
      self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")


if __name__ == "__main__":
  unittest.main()
