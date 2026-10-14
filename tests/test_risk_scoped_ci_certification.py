from pathlib import Path
import unittest

from repo_workflow.self_ci import plan_self_ci
from tests.test_self_ci import assert_integration_probe, job_block
from repo_workflow.test_catalogue import load_test_catalogue


ROOT = Path(__file__).resolve().parents[1]


class RiskScopedCiCertificationTests(unittest.TestCase):
  def test_tdd_green_public_contract_remains_argumentless(self):
    text = (ROOT / "PUBLIC_WORKFLOW.md").read_text(encoding="utf-8")
    self.assertIn("GREEN [--remote]", text)
    self.assertNotIn("rwf tdd green --group", text)
    self.assertNotIn("rwf test GREEN --group", text)

  def test_catalogue_aliases_are_real_groups_and_self_ci_alias_is_targeted(self):
    catalogue = load_test_catalogue(ROOT)
    expanded = catalogue.expand_aliases(["self-ci"])
    self.assertIn("issue-476-staged-self-ci", expanded)
    self.assertIn("invariant-self-ci-contract", expanded)
    self.assertNotEqual(expanded, tuple(sorted(catalogue.groups)))

  def test_certification_issue_keeps_its_owned_group(self):
    plan = plan_self_ci(
      ROOT,
      event="pull_request",
      ref="refs/pull/1/merge",
      head_ref="issue-477-certify-risk-scoped-ci",
      classification="full",
    )
    self.assertEqual(plan.tier, "issue")
    self.assertIn("issue-477-risk-scoped-ci", plan.groups)
    self.assertIn("invariant-self-ci-contract", plan.groups)

  def test_dependency_complete_outcome_can_select_explicit_regression(self):
    plan = plan_self_ci(
      ROOT,
      event="workflow_dispatch",
      ref="refs/heads/issue-477-certify-risk-scoped-ci",
      head_ref="issue-477-certify-risk-scoped-ci",
      classification="full",
      requested_tier="regression",
    )
    self.assertEqual(plan.tier, "regression")
    self.assertIn("explicit regression", plan.reason)

  def test_integration_is_stronger_and_main_cannot_be_downgraded(self):
    plan = plan_self_ci(
      ROOT,
      event="push",
      ref="refs/heads/main",
      head_ref="",
      classification="full",
      requested_tier="regression",
    )
    self.assertEqual(plan.tier, "integration")
    self.assertIn("main integration candidate", plan.reason)

  def test_docs_fast_path_remains_distinct(self):
    plan = plan_self_ci(
      ROOT,
      event="pull_request",
      ref="refs/pull/1/merge",
      head_ref="issue-477-certify-risk-scoped-ci",
      classification="fast",
    )
    self.assertEqual(plan.tier, "docs")
    self.assertEqual(plan.groups, ())

  def test_workflow_keeps_platform_probes_integration_only(self):
    text = (
      ROOT / ".github" / "workflows" / "on-demand-ci.yml"
    ).read_text(encoding="utf-8")
    for name in ("argv-limits", "graph-renderer-platform", "ticket-merge-platform"):
      assert_integration_probe(self, text, name)
      section = job_block(text, name)
      self.assertNotIn("regression-testing", section)

  def test_release_cannot_use_issue_or_regression_evidence(self):
    text = (
      ROOT / ".github" / "workflows" / "on-demand-ci.yml"
    ).read_text(encoding="utf-8")
    self.assertFalse(
      (ROOT / ".github" / "workflows" / "self-ci.yml").exists()
    )
    self.assertNotIn("\n  release:", text)
    publish = job_block(text, "publish")
    self.assertIn("scripts/publish-hosted-result.py", publish)
    self.assertNotIn("git tag", publish)
    self.assertNotIn("refs/tags/", publish)
    self.assertIn("needs.validate.outputs.ready == 'true'", publish)


if __name__ == "__main__":
  unittest.main()
