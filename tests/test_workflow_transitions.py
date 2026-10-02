from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.workflow_state import discover_facts, save_local_state
from repo_workflow.workflow_transitions import validate_integration, validate_regression
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTransitionTests(unittest.TestCase):
  def test_regression_failure_automatically_advances_iteration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
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
        "1.0.0-issue.1.0.2",
      )
      self.assertNotEqual(fx.head(), failed_candidate)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")
      self.assertEqual(discover_facts(root).regression, "missing")

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

  def test_integration_result_before_regression_pass_is_rejected_without_mutation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      before = fx.head()

      with self.assertRaisesRegex(ValueError, "validate integration succeeded is blocked"):
        validate_integration(root, "succeeded")

      self.assertEqual(fx.head(), before)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_repeated_integration_result_is_rejected_without_mutation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)
      validate_integration(root, "succeeded")
      before = fx.head()

      with self.assertRaisesRegex(ValueError, "validate integration failed is blocked"):
        validate_integration(root, "failed")

      self.assertEqual(fx.head(), before)
      self.assertEqual((root / "VERSION").read_text().strip(), fx.version)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")

  def test_regression_rerun_after_pass_is_rejected_before_validation(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root)
      save_local_state(root, fx.head(), regression="PASS", integrationResult=None)

      with patch(
        "repo_workflow.workflow_transitions.verify_local",
        return_value="PASS",
      ) as verify:
        with self.assertRaisesRegex(ValueError, "validate regression is blocked"):
          validate_regression(root, engine_root=ROOT)

      verify.assert_not_called()


if __name__ == "__main__":
  unittest.main()
