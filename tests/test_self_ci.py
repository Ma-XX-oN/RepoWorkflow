from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SelfCiTests(unittest.TestCase):
  def workflow_text(self):
    return (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )

  def test_main_green_bootstrap_publishes_exact_stable_tag(self):
    text = self.workflow_text()
    self.assertIn("github.ref == 'refs/heads/main'", text)
    self.assertEqual(text.count("contents: write"), 1)
    self.assertIn("version=\"$(tr -d '\\r\\n' < VERSION)\"", text)
    self.assertIn("refs/heads/main", text)
    self.assertIn("git ls-remote --heads origin", text)
    self.assertIn("git ls-remote --tags origin", text)
    self.assertIn("github-actions[bot]", text)
    self.assertIn("git tag -a", text)
    self.assertIn("git push origin", text)

  def test_bootstrap_release_requires_plain_semver(self):
    text = self.workflow_text()
    self.assertIn("^[0-9]+\\.[0-9]+\\.[0-9]+$", text)

  def test_docs_only_changes_select_docs_tier_without_code_jobs(self):
    text = self.workflow_text()
    self.assertIn("python repo_workflow.py classify --base", text)
    self.assertIn("python scripts/self-ci-plan.py", text)
    self.assertIn("classification", text)
    self.assertIn("needs.plan.outputs.tier == 'docs'", text)

  def test_issue_tier_runs_only_issue_validation_job(self):
    text = self.workflow_text()
    self.assertIn("  issue-validate:", text)
    self.assertIn("needs.plan.outputs.tier == 'issue'", text)
    self.assertIn("python scripts/validate-issue.py --groups-json", text)

  def test_regression_and_integration_share_broad_validation(self):
    text = self.workflow_text()
    self.assertIn(
      "needs.plan.outputs.tier == 'regression' || "
      "needs.plan.outputs.tier == 'integration'",
      text,
    )
    self.assertIn("run: python scripts/validate.py", text)

  def test_platform_matrices_are_integration_only(self):
    text = self.workflow_text()
    for job in (
      "argv-limits",
      "graph-renderer-platform",
      "ticket-merge-platform",
    ):
      self.assertIn(
        (
          f"  {job}:\n"
          "    needs: [classify, plan]\n"
          "    if: needs.plan.outputs.tier == 'integration'\n"
        ),
        text,
      )

  def test_workflow_dispatch_can_explicitly_request_regression(self):
    text = self.workflow_text()
    self.assertIn("validation_tier:", text)
    self.assertIn("- regression", text)
    self.assertIn("- integration", text)

  def test_release_requires_docs_or_successful_integration(self):
    text = self.workflow_text()
    start = text.index("  release:")
    block = text[start:]
    self.assertIn("needs.plan.outputs.tier == 'docs'", block)
    self.assertIn("needs.plan.outputs.tier == 'integration'", block)
    self.assertIn("needs.validate.result == 'success'", block)
    self.assertNotIn("needs.issue-validate.result == 'success'", block)


if __name__ == "__main__":
  unittest.main()
