from pathlib import Path
import tempfile
import unittest

from repo_workflow.workflow_state import discover_facts, save_local_state
from repo_workflow.workflow_transitions import validate_integration, validate_regression
from tests.support import RepoFixture


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTransitionTests(unittest.TestCase):
  def test_regression_failure_automatically_advances_iteration(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td) / "repo"
      root.mkdir()
      fx = RepoFixture(root, validation_body="raise SystemExit(1)\n")
      failed_version = fx.version
      failed_candidate = fx.head()

      outcome = validate_regression(root, engine_root=ROOT)

      self.assertEqual(outcome, "FAIL")
      self.assertEqual(
        (root / "VERSION").read_text().strip(),
        "1.0.0-issue.1.0.2",
      )
      self.assertNotEqual(fx.head(), failed_candidate)
      self.assertEqual(fx._run("status", "--porcelain").stdout, "")
      tag_target = fx._run(
        "rev-parse", f"v{failed_version}-CI-FAIL^{{}}"
      ).stdout.strip()
      self.assertEqual(tag_target, failed_candidate)
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


if __name__ == "__main__":
  unittest.main()
