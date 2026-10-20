"""Qualified PRELIM acceptance uses the exact #102 hosted terminal boundary."""
from pathlib import Path
from unittest.mock import patch
import unittest

from repo_workflow.git import git
from repo_workflow.prelim_validation import PrelimValidationError
from repo_workflow.prelim_ready_v2_prepare import prepare_destination_prelim
from repo_workflow.prelim_ready_v2_validation import validate_destination_prelim
from tests.test_prelim_attempt import PrelimAttemptTests


G = "11111111-1111-4111-8111-111111111111"


class DestinationValidationTests(unittest.TestCase):
  setUp = PrelimAttemptTests.setUp

  def prepare(self):
    return prepare_destination_prelim(
      self.root, "7", "refs/heads/issue-7", "main", self.config,
      guid=G, resolve_parent=lambda _: "main",
    )

  def validate(self, *, reject=None, tag_target=None, bad_tag=None,
               bad_version=None):
    candidate = self.prepare()
    def observation(stage, sha, evidence):
      self.assertEqual(sha, candidate.candidate_sha)
      expected = {
        "regression": "v1.2.4-issue.7.0.1",
        "integration": "v1.2.4-PRELIM-7.0.1",
      }[stage]
      return {"outcome": "FAIL" if reject == stage else "PASS",
              "version": bad_version or "1.2.4-issue.7.0.1",
              "tag": bad_tag if stage == "integration" and bad_tag else expected}
    self.provider_writes = []
    def publish(*args):
      self.provider_writes.append(args)
    with (
      patch("repo_workflow.prelim_ready_v2_validation._observation",
            side_effect=observation),
      patch("repo_workflow.prelim_ready_v2_validation._remote_target",
            return_value=tag_target or candidate.candidate_sha),
      patch("repo_workflow.prelim_ready_v2_validation._restore"),
      patch("repo_workflow.prelim_ready_v2_validation._publish",
            side_effect=publish),
    ):
      result = validate_destination_prelim(
        self.root, G, self.config, regression=object(),
        integration=object(),
      )
    return candidate, result

  def test_real_local_candidate_accepts_exact_two_pass_results(self):
    candidate, record = self.validate()
    self.assertEqual(record["value"]["candidate_sha"], candidate.candidate_sha)
    self.assertEqual(record["value"]["outcome"], "PASS")
    self.assertEqual(record["value"]["destination"], "main")
    self.assertEqual(len(self.provider_writes), 1)
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/PRELIM-*").stdout.strip(), "")

  def test_failed_hosted_stage_cannot_create_pass_identity(self):
    for rejected in ("regression", "integration"):
      with self.subTest(stage=rejected):
        with self.assertRaisesRegex(PrelimValidationError, "PASS"):
          self.validate(reject=rejected)
        self.assertEqual(self.provider_writes, [])

  def test_invalid_provider_tag_refuses_validation(self):
    with self.assertRaisesRegex(PrelimValidationError, "tag"):
      self.validate(tag_target="f"*40)
    self.assertEqual(self.provider_writes, [])

  def test_wrong_terminal_phase_tag_is_rejected(self):
    with self.assertRaisesRegex(PrelimValidationError, "wrong phase"):
      self.validate(bad_tag="v1.2.4-issue.7.0.1")
    self.assertEqual(self.provider_writes, [])

  def test_wrong_ticket_terminal_version_is_rejected(self):
    with self.assertRaisesRegex(PrelimValidationError, "version invalid"):
      self.validate(bad_version="1.2.4-issue.8.0.1")
    self.assertEqual(self.provider_writes, [])

  def test_historical_base_can_advance_before_validation(self):
    candidate = self.prepare()
    git(self.root, "checkout", "main")
    (self.root / "advanced.txt").write_text("later\n")
    git(self.root, "add", "--", "advanced.txt")
    git(self.root, "commit", "-m", "parent advances")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-7")
    again, evidence = self.validate()
    self.assertEqual(candidate.candidate_sha, again.candidate_sha)
    self.assertEqual(evidence["value"]["base_sha"], candidate.base_sha)


if __name__ == "__main__":
  unittest.main()
