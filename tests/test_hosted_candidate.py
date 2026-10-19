"""Exact candidate remains unchanged throughout hosted on-demand tests."""
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.test_hosted_candidate import hosted_candidate_bound
from repo_workflow.test_results_reader import TestCommandError


SHA = "a" * 40
BRANCH = "issue-683-prelim-ready-migration-v1"


class HostedCandidateTests(unittest.TestCase):
  def verify(self, env):
    with (
      patch.dict(os.environ, env, clear=True),
      patch("repo_workflow.test_hosted_candidate.current_branch",
            return_value=BRANCH),
      patch("repo_workflow.test_hosted_candidate.head_sha",
            return_value=SHA),
    ):
      return hosted_candidate_bound(Path("."))

  def test_local_run_still_prepares_version(self):
    self.assertFalse(self.verify({}))

  def test_hosted_on_demand_is_already_pinned(self):
    self.assertTrue(self.verify({
      "GITHUB_ACTIONS": "true",
      "GITHUB_WORKFLOW": "RepoWorkflow On-Demand CI",
      "GITHUB_REF_NAME": BRANCH,
    }))

  def test_unrelated_workflow_does_not_skip_preparation(self):
    self.assertFalse(self.verify({
      "GITHUB_ACTIONS": "true",
      "GITHUB_WORKFLOW": "RepoWorkflow Self CI",
      "GITHUB_REF_NAME": BRANCH,
    }))

  def test_wrong_issue_ref_does_not_skip_preparation(self):
    self.assertFalse(self.verify({
      "GITHUB_ACTIONS": "true",
      "GITHUB_WORKFLOW": "RepoWorkflow On-Demand CI",
      "GITHUB_REF_NAME": "issue-999-unrelated",
    }))

  def test_explicit_hosted_exact_candidate_must_match_head(self):
    with self.assertRaisesRegex(TestCommandError, "identity"):
      self.verify({
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF_NAME": BRANCH,
        "RWF_HOSTED_TEST_CANDIDATE": "b" * 40,
      })

  def test_explicit_correct_identity_passes(self):
    self.assertTrue(self.verify({
      "GITHUB_ACTIONS": "true",
      "GITHUB_REF_NAME": BRANCH,
      "RWF_HOSTED_TEST_CANDIDATE": SHA,
    }))


if __name__ == "__main__":
  unittest.main()
