from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OnDemandWorkflowContractTests(unittest.TestCase):
  def setUp(self):
    self.text = (
      ROOT / ".github" / "workflows" / "on-demand-ci.yml"
    ).read_text(encoding="utf-8")

  def test_only_marker_path_can_trigger_the_workflow(self):
    triggers = self.text.split("\npermissions:", 1)[0]
    self.assertIn("  push:", triggers)
    self.assertIn("    paths:\n      - '.ci/run'", triggers)
    self.assertNotIn("  pull_request:", triggers)
    self.assertNotIn("  workflow_dispatch:", triggers)

  def test_default_and_preliminary_main_are_excluded(self):
    self.assertIn("branches-ignore:", self.text)
    self.assertIn("      - main", self.text)
    self.assertIn("      - 'prelim-main-*'", self.text)

  def test_workflow_verifies_the_full_invocation_history(self):
    self.assertIn("fetch-depth: 0", self.text)
    self.assertIn("python scripts/on-demand-ci-plan.py", self.text)

  def test_regression_and_integration_select_distinct_platform_coverage(self):
    self.assertIn("needs.plan.outputs.stage == 'regression-testing'", self.text)
    self.assertIn("needs.plan.outputs.stage == 'integration-testing'", self.text)
    self.assertEqual(self.text.count(
      "if: needs.plan.outputs.stage == 'integration-testing'"
    ), 3)

  def test_unimplemented_stages_fail_closed(self):
    for stage in ("RED-testing", "temp-testing", "GREEN-testing"):
      self.assertIn(f"needs.plan.outputs.stage == '{stage}'", self.text)
    self.assertIn("exit 1", self.text)

  def test_no_release_job_is_started_by_selector_push(self):
    self.assertNotIn("\n  release:", self.text)


if __name__ == "__main__":
  unittest.main()
