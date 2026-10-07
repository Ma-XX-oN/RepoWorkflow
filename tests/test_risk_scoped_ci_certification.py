from pathlib import Path
import unittest

from repo_workflow.self_ci import plan_self_ci
from repo_workflow.test_catalogue import load_test_catalogue


ROOT = Path(__file__).resolve().parents[1]


class RiskScopedCiCertificationTests(unittest.TestCase):
  def test_tdd_green_public_contract_remains_argumentless(self):
    text = (ROOT / "PUBLIC_WORKFLOW.md").read_text(encoding="utf-8")
    self.assertIn("rwf tdd green", text)
    self.assertNotIn("rwf tdd green --group", text)
    self.assertNotIn("rwf tdd green group", text)

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
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    self.assertEqual(
      text.count("if: needs.plan.outputs.tier == 'integration'"),
      3,
    )
    self.assertIn(
      "needs.plan.outputs.tier == 'regression' || "
      "needs.plan.outputs.tier == 'integration'",
      text,
    )

  def test_release_cannot_use_issue_or_regression_evidence(self):
    text = (ROOT / ".github" / "workflows" / "self-ci.yml").read_text(
      encoding="utf-8"
    )
    release = text[text.index("  release:"):]
    self.assertIn("needs.plan.outputs.tier == 'integration'", release)
    self.assertNotIn("needs.plan.outputs.tier == 'issue'", release)
    self.assertNotIn("needs.plan.outputs.tier == 'regression'", release)


if __name__ == "__main__":
  unittest.main()
