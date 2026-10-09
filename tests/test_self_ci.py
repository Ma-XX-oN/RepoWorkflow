from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SelfCiTests(unittest.TestCase):
  def workflow_text(self):
    return (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )

  def release_text(self):
    return (ROOT / ".github" / "workflows" / "stable-release.yml").read_text(
      encoding="utf-8"
    )

  def test_self_ci_does_not_own_stable_release(self):
    text = self.workflow_text()
    self.assertNotIn("  release:", text)
    self.assertNotIn("contents: write", text)
    self.assertNotIn("git push origin", text)

  def test_release_uses_successful_main_push_self_ci(self):
    text = self.release_text()
    self.assertIn("workflow_run:", text)
    self.assertIn("RepoWorkflow Self CI", text)
    self.assertIn("types:", text)
    self.assertIn("- completed", text)
    self.assertIn("workflow_run.conclusion == 'success'", text)
    self.assertIn("workflow_run.event == 'push'", text)
    self.assertIn("workflow_run.head_branch == 'main'", text)
    self.assertIn("workflow_run.head_repository.full_name == github.repository", text)
    self.assertIn("github.event.workflow_run.head_sha", text)
    self.assertIn("persist-credentials: false", text)
    self.assertIn("cancel-in-progress: false", text)

  def test_release_requires_full_integration_matrix(self):
    text = self.release_text()
    self.assertIn("python scripts/release-gate.py", text)
    gate = (ROOT / "scripts" / "release-gate.py").read_text(encoding="utf-8")
    for name in ("Probe argv limits", "Probe graph renderer", "Probe ticket merge"):
      self.assertIn(name, gate)
    self.assertIn('VERIFIED_RUN_ID', text)
    self.assertIn("VERIFIED_RUN_ATTEMPT", text)
    self.assertIn("actions: read", text)

  def test_release_preserves_exact_candidate_and_immutable_tag_contract(self):
    text = self.release_text()
    self.assertIn(r"^[0-9]+\.[0-9]+\.[0-9]+$", text)
    self.assertIn('if [ "$head_sha" != "$VERIFIED_SHA" ]', text)
    self.assertIn('if [ -z "$remote_head" ] || [ "$remote_head" != "$head_sha" ]', text)
    self.assertIn("git ls-remote --tags origin", text)
    self.assertIn("git tag -a", text)
    self.assertIn('push origin "refs/tags/$tag"', text)
    self.assertEqual(text.count("contents: write"), 1)

  def test_docs_only_changes_select_docs_tier_without_code_jobs(self):
    text = self.workflow_text()
    self.assertIn("python repo_workflow.py classify --base", text)
    self.assertIn("python scripts/self-ci-plan.py", text)
    self.assertIn("classification", text)

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

  def test_issue_validation_evidence_reports_resolved_groups(self):
    text = (ROOT / "scripts" / "validate-issue.py").read_text(
      encoding="utf-8"
    )
    self.assertEqual(text.count('"groups": groups'), 2)
    self.assertNotIn('"groups": args.groups', text)



if __name__ == "__main__":
  unittest.main()
