from pathlib import Path
import json
import tempfile
import unittest

from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.self_ci import (
  SelfCiError,
  group_command,
  issue_from_head_ref,
  issue_verification_groups,
  plan_self_ci,
)
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


class SelfCiTierTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.repo = Path(self.temp.name) / "repo"
    self.repo.mkdir()
    self.fx = RepoFixture(self.repo)
    self.writer = WriterIdentity("test", "session")
    (self.repo / ".ci" / "tests.json").write_text(json.dumps({
      "test-harnesses": {
        "unittest": {
          "command": "python",
          "layout": ["-m", "unittest", "$test"],
        },
      },
      "tests": [{
        "test-harness": "unittest",
        "issue-476-staged-self-ci": {
          "type": "regression",
          "name": "tests.test_self_ci_tiers",
        },
        "issue-456-command-grammar": {
          "type": "regression",
          "name": "tests.test_quantified_grammar",
        },
        "invariant-self-ci-contract": {
          "type": "invariant",
          "name": "tests.test_self_ci",
        },
      }],
      "aliases": {
        "command-grammar": ["issue-456-command-grammar"],
      },
    }), encoding="utf-8")

    relationship = RelationshipStore(self.repo).create(
      RelationshipGraph(issues={
        "476": IssueRelationships("Stage Self CI", ()),
      }),
      self.writer,
    )
    self.lifecycle = LifecycleStore(self.repo).transition(
      476,
      "start",
      "candidate",
      relationship.revision,
      self.writer,
      None,
    )

  def tearDown(self):
    self.temp.cleanup()

  def test_docs_classification_always_selects_docs_fast_path(self):
    plan = plan_self_ci(
      self.repo,
      event="pull_request",
      ref="refs/pull/1/merge",
      head_ref="issue-476-staged-self-ci",
      classification="fast",
    )
    self.assertEqual(plan.tier, "docs")
    self.assertEqual(plan.groups, ())

  def test_main_push_is_always_integration(self):
    plan = plan_self_ci(
      self.repo,
      event="push",
      ref="refs/heads/main",
      head_ref="",
      classification="full",
      requested_tier="regression",
    )
    self.assertEqual(plan.tier, "integration")
    self.assertIn("main integration candidate", plan.reason)

  def test_issue_pr_selects_owned_group_and_cheap_invariants(self):
    plan = plan_self_ci(
      self.repo,
      event="pull_request",
      ref="refs/pull/1/merge",
      head_ref="issue-476-staged-self-ci",
      classification="full",
    )
    self.assertEqual(plan.tier, "issue")
    self.assertEqual(plan.issue, "476")
    self.assertEqual(
      plan.groups,
      ("invariant-self-ci-contract", "issue-476-staged-self-ci"),
    )

  def test_high_risk_alias_adds_groups_without_replacing_owned_group(self):
    lifecycle = LifecycleStore(self.repo).set_high_risk_aliases(
      476,
      ["command-grammar"],
      self.writer,
      self.lifecycle.revision,
    )
    self.assertEqual(lifecycle.lifecycle.high_risk_aliases, ("command-grammar",))
    groups = issue_verification_groups(self.repo, "476")
    self.assertEqual(
      groups,
      (
        "invariant-self-ci-contract",
        "issue-456-command-grammar",
        "issue-476-staged-self-ci",
      ),
    )

  def test_explicit_stronger_tier_is_not_downgraded_by_docs_classification(self):
    plan = plan_self_ci(
      self.repo,
      event="workflow_dispatch",
      ref="refs/heads/issue-476-staged-self-ci",
      head_ref="issue-476-staged-self-ci",
      classification="fast",
      requested_tier="integration",
    )
    self.assertEqual(plan.tier, "integration")

  def test_explicit_regression_and_integration_tiers_are_distinct(self):
    regression = plan_self_ci(
      self.repo,
      event="workflow_dispatch",
      ref="refs/heads/issue-476-staged-self-ci",
      head_ref="issue-476-staged-self-ci",
      classification="full",
      requested_tier="regression",
    )
    integration = plan_self_ci(
      self.repo,
      event="workflow_dispatch",
      ref="refs/heads/issue-476-staged-self-ci",
      head_ref="issue-476-staged-self-ci",
      classification="full",
      requested_tier="integration",
    )
    self.assertEqual(regression.tier, "regression")
    self.assertEqual(integration.tier, "integration")

  def test_unknown_branch_issue_shape_fails_closed(self):
    with self.assertRaisesRegex(SelfCiError, "issue-<N>"):
      issue_from_head_ref("feature/no-issue")

  def test_issue_without_owned_group_fails_closed(self):
    with self.assertRaisesRegex(SelfCiError, "no verification group"):
      issue_verification_groups(self.repo, "999")

  def test_group_command_comes_from_authoritative_catalogue(self):
    command = group_command(self.repo, "issue-476-staged-self-ci")
    self.assertEqual(command[1:], (
      "-m",
      "unittest",
      "tests.test_self_ci_tiers",
    ))


if __name__ == "__main__":
  unittest.main()
