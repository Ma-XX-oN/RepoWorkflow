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

  def test_every_execution_job_checks_out_verified_candidate_sha(self):
    self.assertIn(
      "tested_sha: ${{ steps.select.outputs.tested_sha }}", self.text,
    )
    self.assertIn(
      'echo "tested_sha=$tested_sha" >> "$GITHUB_OUTPUT"', self.text,
    )
    expected = "ref: ${{ needs.plan.outputs.tested_sha }}"
    self.assertEqual(self.text.count(expected), 4)
    for name in (
      "validate", "argv-limits", "graph-renderer-platform",
      "ticket-merge-platform",
    ):
      section = self.text.split("\n  " + name + ":\n", 1)[1]
      checkout = section.split("      - uses: actions/checkout@v4", 1)[1]
      self.assertIn(expected, checkout.split("      - uses:", 1)[0])

  def test_checkout_steps_have_one_with_mapping(self):
    for block in self.text.split("      - uses: actions/checkout@v4")[1:]:
      step = block.split("\n      - ", 1)[0]
      self.assertEqual(
        step.count("\n        with:"), 1,
        "checkout step must contain exactly one with mapping",
      )

  def test_hosted_regression_and_integration_use_public_test_entrypoint(self):
    self.assertIn("needs.plan.outputs.stage", self.text)
    self.assertIn("./rwf test regression", self.text)
    self.assertIn("./rwf test integration", self.text)
    self.assertNotIn("python scripts/validate.py", self.text)

  def test_public_runner_restores_issue_branch_after_sha_checkout(self):
    section = self.text.split(
      "      - name: Restore issue branch identity at verified candidate", 1,
    )[1].split("      - name: Run selected stage", 1)[0]
    self.assertIn('git switch -c "$GITHUB_REF_NAME"', section)
    self.assertIn("hosted testing requires an issue branch", section)

  def test_hosted_runner_allows_only_canonical_evidence_side_effect(self):
    self.assertIn("Verify only canonical test-results log changed", self.text)
    self.assertIn(
      '".repoworkflow/validation/testResults-" + match.group(1) + ".jsonl"',
      self.text,
    )
    self.assertIn("unexpected hosted test side effect", self.text)
    self.assertNotIn("Verify validation did not change checkout", self.text)

  def test_side_effect_check_runs_after_test_failure(self):
    section = self.text.split(
      "      - name: Verify only canonical test-results log changed", 1,
    )[1].split("\n  argv-limits:", 1)[0]
    self.assertIn("if: ${{ always() }}", section)

  def test_unimplemented_stages_fail_closed(self):
    for stage in ("RED-testing", "temp-testing", "GREEN-testing"):
      self.assertIn(f"needs.plan.outputs.stage == '{stage}'", self.text)
    self.assertIn("exit 1", self.text)

  def test_no_release_job_is_started_by_selector_push(self):
    self.assertNotIn("\n  release:", self.text)


if __name__ == "__main__":
  unittest.main()
