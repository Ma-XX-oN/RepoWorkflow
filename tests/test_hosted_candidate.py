"""Hosted result evidence never changes source or reuses a different run."""
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.test_hosted_candidate import (
  hosted_candidate_bound, publish_if_local,
)
from repo_workflow.test_results_reader import TestCommandError


SHA = "a" * 40
INV = "b" * 40
BRANCH = "issue-683-prelim-ready-migration-v1"
HOSTED = {
  "GITHUB_ACTIONS": "true",
  "GITHUB_WORKFLOW": "RepoWorkflow On-Demand CI",
  "GITHUB_REF_NAME": BRANCH,
  "GITHUB_SHA": INV,
  "GITHUB_WORKSPACE": str(Path(".").resolve()),
}


class HostedCandidateTests(unittest.TestCase):
  def verify(self, env, invoke=None):
    def git(root, *args):
      if args[0] == "show":
        return "regression-testing " + SHA
      if args[0] == "rev-list":
        return INV + " " + SHA
      if args[0] == "diff-tree":
        return ".ci/run"
      raise AssertionError("unexpected command")
    with (
      patch.dict(os.environ, env, clear=True),
      patch("repo_workflow.test_hosted_candidate.current_branch",
            return_value=BRANCH),
      patch("repo_workflow.test_hosted_candidate.head_sha",
            return_value=SHA),
      patch("repo_workflow.test_hosted_candidate._git",
            side_effect=invoke or git),
    ):
      return hosted_candidate_bound(Path("."))

  def test_local_run_does_not_claim_hosted_authority(self):
    self.assertFalse(self.verify({}))

  def test_exact_dedicated_invocation_is_bound(self):
    self.assertTrue(self.verify(HOSTED))

  def test_different_workflow_does_not_skip_local_preparation(self):
    self.assertFalse(self.verify({
      **HOSTED, "GITHUB_WORKFLOW": "RepoWorkflow Self CI",
    }))

  def test_mismatched_branch_denied(self):
    with self.assertRaises(TestCommandError):
      self.verify({**HOSTED, "GITHUB_REF_NAME": "issue-999"})

  def test_missing_invocation_id_denied(self):
    with self.assertRaises(TestCommandError):
      self.verify({key: value for key, value in HOSTED.items()
                   if key != "GITHUB_SHA"})

  def test_noncanonical_invocation_denied(self):
    def forged(root, *args):
      return ".ci/run" if args[0] == "diff-tree" else (
        INV + " " + "c"*40 if args[0] == "rev-list"
        else "regression-testing " + SHA)
    with self.assertRaisesRegex(TestCommandError, "exact-source"):
      self.verify(HOSTED, forged)

  def test_chained_invocation_uses_authenticated_original_candidate(self):
    # A chained integration/regression marker has an intermediate invocation
    # parent; the physical checkout remains the original exact candidate.
    def chained(root, *args):
      if args[0] == "show":
        return "regression-testing " + "c" * 40
      if args[0] == "rev-list":
        return INV + " " + "c" * 40
      if args[0] == "diff-tree":
        return ".ci/run"
      raise AssertionError("unexpected command")
    with patch(
      "repo_workflow.test_hosted_candidate.resolve_invocation",
      return_value={"candidate_sha": SHA},
    ) as resolver:
      self.assertTrue(self.verify(HOSTED, chained))
    resolver.assert_called_once()

  def test_chained_invocation_wrong_source_rejected(self):
    def chained(root, *args):
      return (INV + " " + "c" * 40 if args[0] == "rev-list"
              else "regression-testing " + "c" * 40
              if args[0] == "show" else ".ci/run")
    with patch(
      "repo_workflow.test_hosted_candidate.resolve_invocation",
      return_value={"candidate_sha": "d" * 40},
    ):
      with self.assertRaisesRegex(TestCommandError, "identity changed"):
        self.verify(HOSTED, chained)

  def test_nested_consumer_repository_retains_local_semantics(self):
    with patch.dict(os.environ, HOSTED, clear=True):
      self.assertFalse(hosted_candidate_bound(Path(".") / "consumer"))

  def test_other_source_sha_denied(self):
    def forged(root, *args):
      return (INV + " " + SHA if args[0] == "rev-list"
              else "regression-testing " + "c"*40
              if args[0] == "show" else ".ci/run")
    with self.assertRaises(TestCommandError):
      self.verify(HOSTED, forged)

  def test_explicit_hosted_candidate_must_match(self):
    with self.assertRaisesRegex(TestCommandError, "identity"):
      self.verify({**HOSTED, "RWF_HOSTED_TEST_CANDIDATE": "c" * 40})
    self.assertTrue(self.verify({
      **HOSTED, "RWF_HOSTED_TEST_CANDIDATE": SHA,
    }))

  def test_local_terminal_call_and_hosted_omission(self):
    with patch("repo_workflow.local_terminal.publish_local_terminal") as write:
      with patch("repo_workflow.test_hosted_candidate.hosted_candidate_bound",
                 return_value=False):
        publish_if_local(Path("."), stage="regression")
      write.assert_called_once_with(Path("."), stage="regression")
      with patch("repo_workflow.test_hosted_candidate.hosted_candidate_bound",
                 return_value=True):
        publish_if_local(Path("."), stage="integration")
      write.assert_called_once()


if __name__ == "__main__":
  unittest.main()
